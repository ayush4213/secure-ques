"""End-to-end API tests for a seeded SQLite bank and student MCQ sessions."""
import json
from collections import Counter
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend import main


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(main, 'DB_PATH', tmp_path / 'test.db')
    with TestClient(main.app) as app_client:
        yield app_client


@pytest.fixture
def exam():
    return {
        'student_name': 'Demo Candidate', 'student_code': 'IT204',
        'goal': 'class_test',
        'subjects': ['Electrical','Chemistry','Computer Science'],
        'question_types': [], 'question_count': 10, 'duration_minutes': 20,
    }


def admin():
    return {'X-Admin-Key': main.ADMIN_KEY}


def test_seed_database_has_verified_markers_and_distractors(client):
    meta = client.get('/api/meta').json()
    assert meta['question_count'] == 90
    assert len(meta['subjects']) == 5
    assert len(meta['goals']) == 4
    with main.database() as db:
        rows = db.execute('''SELECT q.id,COUNT(o.id) n,SUM(o.is_correct) c
            FROM questions q JOIN question_options o ON q.id=o.question_id GROUP BY q.id''').fetchall()
        assert len(rows) == 90
        assert all(x['n'] == 6 and x['c'] == 1 for x in rows)
    assert client.get('/api/health').json()['status'] == 'ok'


def test_planner_honors_selected_subjects_and_goal_mix(client, exam):
    res = client.post('/api/blueprint', json=exam)
    assert res.status_code == 200
    plan = res.json()
    assert plan['difficulty'] == {'easy':3,'medium':5,'hard':2}
    assert sum(plan['subjects'].values()) == 10
    assert set(plan['subjects']) == set(exam['subjects'])
    assert plan['eligible_questions'] == 54


def test_student_paper_uses_only_saved_questions_and_keeps_key_private(client, exam):
    res = client.post('/api/sessions', json=exam)
    assert res.status_code == 201, res.text
    session = res.json()
    assert session['status'] == 'active' and session['score'] is None
    assert len(session['questions']) == 10
    assert 'review' not in session
    actual = session['blueprint']['actual']
    assert actual['difficulty'] == {'easy':3,'medium':5,'hard':2}
    assert sum(actual['subjects'].values()) == 10
    assert all(q['subject'] in exam['subjects'] for q in session['questions'])
    # API never includes correctness flags, correct answer IDs or an answer key.
    raw = res.text
    assert 'is_correct' not in raw and 'correct_text' not in raw
    assert 'answer_key' not in raw and 'correct_option_id' not in raw
    with main.database() as db:
        for q in session['questions']:
            assert len(q['options']) == 4
            assert len(set(o['id'] for o in q['options'])) == 4
            qs = [db.execute('SELECT is_correct FROM question_options WHERE id=?',(o['id'],)).fetchone()[0] for o in q['options']]
            assert sum(qs) == 1
            assert db.execute('SELECT 1 FROM questions WHERE id=?',(q['id'],)).fetchone()


def test_two_students_receive_different_question_sets(client, exam):
    first = client.post('/api/sessions',json=exam).json()
    exam['student_name']='Second Candidate';exam['student_code']='IT205'
    second = client.post('/api/sessions',json=exam).json()
    a = {q['id'] for q in first['questions']}
    b = {q['id'] for q in second['questions']}
    assert a != b
    assert all(len(q['options'])==4 for q in second['questions'])


def test_same_student_gets_unseen_questions_when_sufficient_bank(client, exam):
    first = client.post('/api/sessions', json=exam).json()
    second = client.post('/api/sessions', json=exam).json()
    assert set(q['id'] for q in first['questions']).isdisjoint(q['id'] for q in second['questions'])


def test_autosave_and_server_side_perfect_scoring(client, exam):
    session = client.post('/api/sessions',json=exam).json()
    sid = session['id']
    with main.database() as db:
        for q in session['questions']:
            correct = db.execute('SELECT id FROM question_options WHERE question_id=? AND is_correct=1',(q['id'],)).fetchone()[0]
            assert correct in {o['id'] for o in q['options']}
            saved = client.post(f'/api/sessions/{sid}/answer',json={'question_id':q['id'],'option_id':correct})
            assert saved.status_code == 200, saved.text
    resumed = client.get(f'/api/sessions/{sid}').json()
    assert sum(1 for q in resumed['questions'] if q['selected_option']) == 10
    completed = client.post(f'/api/sessions/{sid}/submit').json()
    assert completed['status'] == 'submitted'
    assert completed['score'] == 10
    assert len(completed['review'])==10
    assert all(q['is_correct'] for q in completed['review'])
    wrong = client.post(f'/api/sessions/{sid}/answer',json={'question_id':session['questions'][0]['id'],'option_id':session['questions'][0]['options'][0]['id']})
    assert wrong.status_code == 409
    assert client.post(f'/api/sessions/{sid}/submit').json()['score']==10


def test_nonmember_option_rejected_and_no_grading_oracle(client, exam):
    session = client.post('/api/sessions',json=exam).json()
    q = session['questions'][0]
    assert client.post('/api/sessions/'+session['id']+'/answer',json={'question_id':q['id'],'option_id':'guess-option-id'}).status_code==422
    assert client.get('/api/sessions/'+session['id']).json()['score'] is None
    assert client.get('/api/sessions/unrecognised-token').status_code==404


def test_session_expiry_finalizes_and_releases_review(client, exam):
    session=client.post('/api/sessions',json=exam).json()
    with main.database() as db:
        db.execute('UPDATE exam_sessions SET ends_at=? WHERE id=?',((datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat(),session['id']))
    result=client.get('/api/sessions/'+session['id']).json()
    assert result['status']=='submitted' and result['score']==0
    assert len(result['review'])==10


def test_admin_private_options_add_archive_and_import(client, exam):
    assert client.get('/api/admin/questions').status_code==401
    assert client.get('/api/admin/sessions').status_code==401
    assert client.post('/api/admin/questions',json={}).status_code==401
    questions = client.get('/api/admin/questions',headers=admin()).json()
    assert len(questions)==90
    assert any(o['is_correct']==1 for o in questions[0]['options'])
    new = {'subject':'Electrical','topic':'Sample', 'difficulty':'easy', 'question_type':'conceptual',
           'text':'What is a deliberately new demonstration sample?', 'correct_option':'Approved choice',
           'wrong_options':['Not approved','Unrelated choice','Incorrect choice','Other incorrect','Last incorrect']}
    added = client.post('/api/admin/questions',json=new,headers=admin())
    assert added.status_code==201,added.text
    qid = added.json()['id']
    assert client.get('/api/meta').json()['question_count']==91
    archived=client.patch(f'/api/admin/questions/{qid}?active=false',headers=admin())
    assert archived.status_code==200
    assert client.get('/api/meta').json()['question_count']==90
    restored=client.patch(f'/api/admin/questions/{qid}?active=true',headers=admin())
    assert restored.status_code==200
    new['text'] = 'What is another demonstration sample?'
    bad = client.post('/api/admin/questions/import',json=[new,new],headers=admin())
    assert bad.status_code==422
    assert not any(q['text']==new['text'] for q in client.get('/api/admin/questions',headers=admin()).json())
    new['text']='What is a unique bulk import question?'
    ok = client.post('/api/admin/questions/import',json=[new],headers=admin())
    assert ok.status_code==200 and ok.json()['imported']==1


def test_filtering_and_insufficient_bank(client, exam):
    exam['subjects']=['Electrical']
    exam['question_types']=['numerical']
    exam['question_count']=6
    p=client.post('/api/blueprint',json=exam)
    assert p.status_code==200
    session=client.post('/api/sessions',json=exam).json()
    assert all(q['subject']=='Electrical' and q['question_type']=='numerical' for q in session['questions'])
    exam['question_count']=30
    assert client.post('/api/blueprint',json=exam).status_code==422


def test_frontend_assets_and_safe_http_headers(client):
    home=client.get('/')
    assert home.status_code==200
    assert 'SecurePaper' in home.text
    assert 'src="/static/app.js"' in home.text
    script=client.get('/static/app.js')
    assert script.status_code==200 and 'saveSelectedOption' in script.text
    assert 'default-src' in script.headers['content-security-policy']
    assert client.get('/api/meta').headers['cache-control']=='no-store'
