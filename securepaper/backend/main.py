"""SecurePaper MCQ demo API. Adapted from the uploaded FastAPI + SQLite prototype.

Question text and answers are imported, never generated. Admin answer keys are
private; student endpoints emit only one correct and three shuffled distractors
(without indicating which is correct until the exam is submitted).
"""
from __future__ import annotations

import json
import os
import secrets
import sqlite3
import uuid
from collections import Counter
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from . import selector

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv('SECUREPAPER_DATA_DIR', str(ROOT / 'data'))).resolve()
DB_PATH = DATA_DIR / 'securepaper.db'
SEED_PATH = ROOT / 'seed' / 'seed_questions.json'
ADMIN_KEY = os.getenv('SECUREPAPER_ADMIN_KEY', 'demo1234')
UTC = timezone.utc


def iso_now():
    return datetime.now(UTC).isoformat()


@contextmanager
def database():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=20, isolation_level=None)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    c.execute('PRAGMA busy_timeout=20000')
    try:
        yield c
    finally:
        c.close()


def normalize_options(correct: str, wrong: list[str]):
    correct = correct.strip()
    wrong = [w.strip() for w in wrong]
    if not correct or len(wrong) < 3 or len(wrong) > 30 or any(not w for w in wrong):
        raise ValueError('Supply one correct option and 3–30 nonempty incorrect options.')
    if len({x.casefold() for x in [correct, *wrong]}) != len(wrong) + 1:
        raise ValueError('Correct and incorrect option texts must be distinct.')
    return correct, wrong


def insert_question(c: sqlite3.Connection, q: dict):
    correct, wrong = normalize_options(q['correct_option'], q['wrong_options'])
    subject = q['subject'].strip()
    topic = q['topic'].strip()
    content = q['text'].strip()
    if not (subject and topic and content):
        raise ValueError('Subject, topic and question text are required.')
    if q['difficulty'] not in selector.DIFFICULTIES:
        raise ValueError('Difficulty must be easy, medium or hard.')
    if q['question_type'] not in ('conceptual', 'numerical', 'application', 'reasoning'):
        raise ValueError('Unknown question type.')
    if c.execute('SELECT 1 FROM questions WHERE subject=? AND lower(trim(text))=lower(?)', (subject, content)).fetchone():
        raise ValueError(f'Duplicate question in {subject}: {content[:65]}')
    qid = uuid.uuid4().hex
    c.execute('INSERT INTO questions (id,subject,topic,difficulty,question_type,text,created_at) VALUES (?,?,?,?,?,?,?)',
              (qid, subject, topic, q['difficulty'], q['question_type'], content, iso_now()))
    for value, is_correct in [(correct, 1), *[(w, 0) for w in wrong]]:
        c.execute('INSERT INTO question_options (id,question_id,text,is_correct) VALUES (?,?,?,?)',
                  (uuid.uuid4().hex, qid, value, is_correct))
    return qid


def init_db():
    with database() as c:
        c.executescript((ROOT / 'backend' / 'schema.sql').read_text(encoding='utf8'))
        if c.execute('SELECT COUNT(*) FROM questions').fetchone()[0] == 0:
            dataset = json.loads(SEED_PATH.read_text(encoding='utf8'))
            c.execute('BEGIN IMMEDIATE')
            try:
                for q in dataset:
                    insert_question(c, q)
                c.commit()
            except Exception:
                c.rollback()
                raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title='SecurePaper MCQ Demo', version='2.0.0', lifespan=lifespan)
allowed_origins = [x.strip() for x in os.getenv('SECUREPAPER_CORS_ORIGINS','').split(',') if x.strip()]
if allowed_origins:
    app.add_middleware(CORSMiddleware, allow_origins=allowed_origins,
                       allow_methods=['GET','POST','PATCH','OPTIONS'],
                       allow_headers=['Content-Type','X-Admin-Key'])


@app.middleware('http')
async def demo_headers(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'same-origin'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; base-uri 'self'; frame-ancestors 'none'"
    return response


def require_admin(key: Annotated[str | None, Header(alias='X-Admin-Key')] = None):
    if not key or not secrets.compare_digest(key, ADMIN_KEY):
        raise HTTPException(status_code=401, detail='Invalid admin key.')
    return True


class QuestionCreate(BaseModel):
    subject: str = Field(min_length=1, max_length=60)
    topic: str = Field(min_length=1, max_length=80)
    difficulty: Literal['easy','medium','hard']
    question_type: Literal['conceptual','numerical','application','reasoning']
    text: str = Field(min_length=6, max_length=1000)
    correct_option: str = Field(min_length=1, max_length=300)
    wrong_options: list[str] = Field(min_length=3, max_length=30)

    @field_validator('wrong_options')
    @classmethod
    def wrong_text_valid(cls, values: list[str]):
        if any(not isinstance(v, str) or not v.strip() or len(v) > 300 for v in values):
            raise ValueError('Wrong options must be nonempty strings under 300 characters.')
        return values


class ExamRequest(BaseModel):
    student_name: str = Field(min_length=2, max_length=80)
    student_code: str = Field(default='', max_length=40)
    goal: Literal['practice', 'class_test', 'competitive', 'revision'] = 'class_test'
    subjects: list[str] = Field(min_length=1, max_length=10)
    question_types: list[str] = Field(default_factory=list, max_length=4)
    question_count: int = Field(default=10, ge=1, le=40)
    duration_minutes: int = Field(default=20, ge=1, le=180)

    @field_validator('subjects')
    @classmethod
    def valid_subjects(cls, values: list[str]):
        if len(values) != len(set(values)) or any(not x.strip() for x in values):
            raise ValueError('Select distinct, nonempty subjects.')
        return values

    @field_validator('question_types')
    @classmethod
    def valid_types(cls, values: list[str]):
        allowed = {'conceptual', 'numerical', 'application', 'reasoning'}
        if any(v not in allowed for v in values) or len(values) != len(set(values)):
            raise ValueError('Invalid question types.')
        return values


class AnswerSave(BaseModel):
    question_id: str
    option_id: str


def eligible_questions(c: sqlite3.Connection, req: ExamRequest):
    subj = ','.join('?' for _ in req.subjects)
    types = req.question_types or ['conceptual','numerical','application','reasoning']
    typ = ','.join('?' for _ in types)
    sql = f"""SELECT q.id,q.subject,q.topic,q.difficulty,q.question_type,q.text
            FROM questions q
            WHERE q.active=1 AND q.subject IN ({subj}) AND q.question_type IN ({typ})
            AND (SELECT COUNT(*) FROM question_options o WHERE o.question_id=q.id AND o.is_correct=1)=1
            AND (SELECT COUNT(*) FROM question_options o WHERE o.question_id=q.id AND o.is_correct=0)>=3"""
    return [dict(row) for row in c.execute(sql, [*req.subjects, *types])]


def candidate_blueprint(c: sqlite3.Connection, req: ExamRequest):
    pool = eligible_questions(c, req)
    try:
        plan = selector.blueprint(pool, req.goal, req.subjects, req.question_count)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return pool, plan


@app.get('/api/health')
def health():
    return {'status': 'ok', 'database': 'sqlite', 'mode': 'database-only-mcq'}


@app.get('/api/meta')
def meta():
    with database() as c:
        subjects = [{'name': r['subject'], 'count': r['count']} for r in c.execute('SELECT subject, COUNT(*) as count FROM questions WHERE active=1 GROUP BY subject ORDER BY subject')]
        types = [{'name': r['question_type'], 'count': r['count']} for r in c.execute('SELECT question_type, COUNT(*) as count FROM questions WHERE active=1 GROUP BY question_type ORDER BY question_type')]
        difficulty = dict(c.execute('SELECT difficulty, COUNT(*) FROM questions WHERE active=1 GROUP BY difficulty').fetchall())
        sessions = c.execute('SELECT COUNT(*) FROM exam_sessions').fetchone()[0]
    return {
        'subjects': subjects, 'question_types': types,
        'difficulty': difficulty, 'question_count': sum(x['count'] for x in subjects),
        'session_count': sessions,
        'goals': [{ 'id': k, 'label': v['label'], 'description': v['description'], 'weights': v['weights'] } for k,v in selector.GOALS.items()],
        'selection_method': 'Offline constraint-aware, rules-based selector (not an LLM)',
    }


@app.post('/api/blueprint')
def show_blueprint(req: ExamRequest):
    with database() as c:
        _pool, plan = candidate_blueprint(c, req)
    return plan


def result_summary(c, sid):
    rows = c.execute('''SELECT q.subject,q.difficulty,q.question_type,
                CASE WHEN o.is_correct=1 THEN 1 ELSE 0 END AS correct
            FROM exam_items e
            JOIN questions q ON q.id=e.question_id
            LEFT JOIN session_answers a ON a.session_id=e.session_id AND a.question_id=e.question_id
            LEFT JOIN question_options o ON o.id=a.option_id
            WHERE e.session_id=?''', (sid,)).fetchall()
    return sum(r['correct'] for r in rows), len(rows)


def finalize(c, sid):
    row = c.execute('SELECT status FROM exam_sessions WHERE id=?', (sid,)).fetchone()
    if not row:
        raise HTTPException(404, 'Exam session not found.')
    if row['status'] == 'submitted':
        return
    correct, _ = result_summary(c, sid)
    c.execute('UPDATE exam_sessions SET status=?,submitted_at=?,score=? WHERE id=? AND status=?',
              ('submitted', iso_now(), correct, sid, 'active'))


def session_view(c, sid):
    s = c.execute('SELECT * FROM exam_sessions WHERE id=?', (sid,)).fetchone()
    if not s:
        raise HTTPException(404, 'Exam session not found.')
    if s['status'] == 'active' and datetime.fromisoformat(s['ends_at']) <= datetime.now(UTC):
        c.execute('BEGIN IMMEDIATE')
        try:
            finalize(c, sid)
            c.commit()
        except Exception:
            c.rollback()
            raise
        s = c.execute('SELECT * FROM exam_sessions WHERE id=?', (sid,)).fetchone()
    items = []
    for q in c.execute('''SELECT q.id,q.text,q.subject,q.topic,q.difficulty,q.question_type,e.position,
                    a.option_id AS selected_option
            FROM exam_items e JOIN questions q ON q.id=e.question_id
            LEFT JOIN session_answers a ON a.session_id=e.session_id AND a.question_id=e.question_id
            WHERE e.session_id=? ORDER BY e.position''', (sid,)):
        opts = [dict(r) for r in c.execute('''SELECT o.id,o.text,so.position
                    FROM session_options so JOIN question_options o ON o.id=so.option_id
                    WHERE so.session_id=? AND so.question_id=? ORDER BY so.position''', (sid,q['id']))]
        items.append({
            'id': q['id'], 'text': q['text'], 'subject': q['subject'], 'topic': q['topic'],
            'difficulty': q['difficulty'], 'question_type': q['question_type'],
            'position': q['position'], 'selected_option': q['selected_option'],
            'options': [{'id': o['id'], 'text': o['text']} for o in opts],
        })
    view = {
        'id': s['id'], 'student_name': s['student_name'], 'student_code': s['student_code'],
        'goal': s['exam_goal'], 'requirements': json.loads(s['requirements_json']),
        'blueprint': json.loads(s['blueprint_json']),
        'created_at': s['created_at'], 'ends_at': s['ends_at'],
        'status': s['status'], 'submitted_at': s['submitted_at'],
        'score': s['score'], 'questions': items,
    }
    if s['status'] == 'submitted':
        view['review'] = exam_review(c,sid)
    return view


def exam_review(c,sid):
    rows = c.execute('''SELECT q.id,q.subject,q.text,e.position,
                correct.text AS correct_text, correct.id AS correct_option_id,
                chosen.text AS selected_text, chosen.id AS selected_option_id
            FROM exam_items e JOIN questions q ON q.id=e.question_id
            JOIN question_options correct ON correct.question_id=q.id AND correct.is_correct=1
            LEFT JOIN session_answers a ON a.session_id=e.session_id AND a.question_id=e.question_id
            LEFT JOIN question_options chosen ON chosen.id=a.option_id
            WHERE e.session_id=? ORDER BY e.position''', (sid,)).fetchall()
    return [{
        'question_id': r['id'], 'subject': r['subject'], 'text': r['text'],
        'correct_text': r['correct_text'], 'correct_option_id': r['correct_option_id'],
        'selected_text': r['selected_text'], 'selected_option_id': r['selected_option_id'],
        'is_correct': r['selected_option_id'] == r['correct_option_id'],
    } for r in rows]


@app.post('/api/sessions', status_code=201)
def create_session(req: ExamRequest):
    with database() as c:
        c.execute('BEGIN IMMEDIATE')
        try:
            pool, plan = candidate_blueprint(c, req)
            student_code = req.student_code.strip()
            old = {r[0] for r in c.execute('''SELECT DISTINCT e.question_id FROM exam_items e JOIN exam_sessions s ON s.id=e.session_id
                      WHERE s.student_code=? AND s.student_code<>'' ''', (student_code,))} if student_code else set()
            exposure = Counter({r[0]: r[1] for r in c.execute('SELECT question_id,COUNT(*) FROM exam_items GROUP BY question_id')})
            previous = {r[0] for r in c.execute('SELECT fingerprint FROM exam_sessions')}
            chosen = selector.select_questions(pool, plan, old, exposure, previous)
            actual = {
                'subjects': dict(Counter(q['subject'] for q in chosen)),
                'difficulty': dict(Counter(q['difficulty'] for q in chosen)),
                'question_types': dict(Counter(q['question_type'] for q in chosen)),
            }
            plan['actual'] = actual
            sid = secrets.token_urlsafe(27)
            created = datetime.now(UTC)
            ends = created + timedelta(minutes=req.duration_minutes)
            c.execute('''INSERT INTO exam_sessions
                     (id,student_name,student_code,exam_goal,requirements_json,blueprint_json,fingerprint,created_at,ends_at)
                     VALUES (?,?,?,?,?,?,?,?,?)''',
                      (sid, req.student_name.strip(), student_code, req.goal,
                       req.model_dump_json(), json.dumps(plan), selector.fingerprint(chosen),
                       created.isoformat(), ends.isoformat()))
            rng = secrets.SystemRandom()
            for index, q in enumerate(chosen):
                c.execute('INSERT INTO exam_items (session_id,question_id,position) VALUES (?,?,?)', (sid, q['id'], index))
                options = [dict(r) for r in c.execute('SELECT id,text,is_correct FROM question_options WHERE question_id=?', (q['id'],))]
                right = [o for o in options if o['is_correct']]
                wrong = [o for o in options if not o['is_correct']]
                if len(right) != 1 or len(wrong) < 3:
                    raise ValueError('A bank question has invalid answer markers.')
                four = right + rng.sample(wrong, 3)
                rng.shuffle(four)
                for oi, o in enumerate(four):
                    c.execute('INSERT INTO session_options (session_id,question_id,option_id,position) VALUES (?,?,?,?)',
                              (sid, q['id'], o['id'], oi))
            c.commit()
        except ValueError as e:
            c.rollback()
            raise HTTPException(422, str(e)) from e
        except Exception:
            c.rollback()
            raise
        return session_view(c, sid)


@app.get('/api/sessions/{sid}')
def get_session(sid: str):
    with database() as c:
        return session_view(c,sid)


@app.post('/api/sessions/{sid}/answer')
def save_answer(sid: str, answer: AnswerSave):
    with database() as c:
        c.execute('BEGIN IMMEDIATE')
        try:
            s = c.execute('SELECT status,ends_at FROM exam_sessions WHERE id=?', (sid,)).fetchone()
            if not s:
                raise HTTPException(404, 'Exam session not found.')
            if s['status'] != 'active' or datetime.fromisoformat(s['ends_at']) <= datetime.now(UTC):
                finalize(c,sid)
                c.commit()
                raise HTTPException(409, 'The exam is closed. Answers cannot be changed.')
            valid = c.execute('SELECT 1 FROM session_options WHERE session_id=? AND question_id=? AND option_id=?',
                              (sid, answer.question_id, answer.option_id)).fetchone()
            if not valid:
                raise HTTPException(422, 'That answer option is not part of this paper.')
            c.execute('''INSERT INTO session_answers (session_id,question_id,option_id,answered_at) VALUES(?,?,?,?)
                      ON CONFLICT(session_id,question_id) DO UPDATE SET option_id=excluded.option_id,answered_at=excluded.answered_at''',
                      (sid,answer.question_id,answer.option_id,iso_now()))
            c.commit()
        except HTTPException:
            c.rollback()
            raise
        except Exception:
            c.rollback()
            raise
    return {'saved': True, 'question_id':answer.question_id}


@app.post('/api/sessions/{sid}/submit')
def submit_session(sid: str):
    with database() as c:
        c.execute('BEGIN IMMEDIATE')
        try:
            finalize(c,sid)
            c.commit()
        except Exception:
            c.rollback()
            raise
        return session_view(c,sid)


@app.get('/api/admin/questions', dependencies=[Depends(require_admin)])
def admin_questions(subject: str = '', difficulty: str = '', search: str = '', limit: int = Query(250, ge=1, le=1000)):
    where = ['1=1']
    params = []
    if subject:
        where.append('subject=?'); params.append(subject)
    if difficulty:
        where.append('difficulty=?'); params.append(difficulty)
    if search:
        where.append('(text LIKE ? OR topic LIKE ?)'); params.extend(['%'+search+'%']*2)
    with database() as c:
        rows = [dict(r) for r in c.execute('SELECT * FROM questions WHERE '+' AND '.join(where)+' ORDER BY subject,difficulty,topic,text LIMIT ?', [*params,limit])]
        for q in rows:
            q['options'] = [dict(o) for o in c.execute('SELECT id,text,is_correct FROM question_options WHERE question_id=? ORDER BY is_correct DESC,text', (q['id'],))]
    return rows


@app.post('/api/admin/questions', dependencies=[Depends(require_admin)], status_code=201)
def admin_question_add(q: QuestionCreate):
    with database() as c:
        c.execute('BEGIN IMMEDIATE')
        try:
            qid = insert_question(c, q.model_dump())
            c.commit()
        except ValueError as e:
            c.rollback(); raise HTTPException(422,str(e)) from e
        except Exception:
            c.rollback(); raise
    return {'id':qid,'created':True}


@app.post('/api/admin/questions/import', dependencies=[Depends(require_admin)])
def admin_import(questions: list[QuestionCreate]):
    if not 1 <= len(questions) <= 500:
        raise HTTPException(422, 'Supply 1–500 questions in a JSON array.')
    with database() as c:
        c.execute('BEGIN IMMEDIATE')
        ids = []
        try:
            for q in questions:
                ids.append(insert_question(c,q.model_dump()))
            c.commit()
        except ValueError as e:
            c.rollback(); raise HTTPException(422,str(e)) from e
        except Exception:
            c.rollback(); raise
    return {'imported':len(ids),'ids':ids}


@app.patch('/api/admin/questions/{qid}', dependencies=[Depends(require_admin)])
def admin_toggle_question(qid: str, active: bool):
    with database() as c:
        c.execute('BEGIN IMMEDIATE')
        cur = c.execute('UPDATE questions SET active=? WHERE id=?', (int(active),qid))
        c.commit()
    if cur.rowcount != 1:
        raise HTTPException(404,'Question not found.')
    return {'id':qid,'active':active}


@app.get('/api/admin/sessions', dependencies=[Depends(require_admin)])
def admin_sessions():
    with database() as c:
        rows = c.execute('''SELECT id,student_name,student_code,exam_goal,created_at,ends_at,status,score,blueprint_json
                 FROM exam_sessions ORDER BY created_at DESC LIMIT 100''').fetchall()
    return [{**{k:r[k] for k in r.keys() if k != 'blueprint_json'},
             'question_count':json.loads(r['blueprint_json'])['question_count']} for r in rows]


@app.get('/')
def homepage():
    return FileResponse(ROOT / 'frontend' / 'index.html')


app.mount('/static', StaticFiles(directory=ROOT / 'frontend'), name='static')
