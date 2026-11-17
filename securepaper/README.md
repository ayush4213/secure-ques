# SecurePaper — database-driven MCQ demo

A **working, single-service FastAPI + SQLite web application** adapted from the uploaded SecurePaper project. This version intentionally focuses on question-bank selection and online MCQ delivery, **not** on AI question generation, cryptographic paper release, or the complete research proposal.

## What is included

- **90 seeded MCQs** covering Electrical, Chemistry, Physics, Mathematics and Computer Science, with six questions for every subject/difficulty combination.
- SQLite tables for subjects/topics/difficulty/question type, an explicit **one correct option** and **five stored wrong options** per seed question.
- An automatic **rule-based intelligent exam selector**. It filters only approved stored questions; balances subjects; adjusts *easy / medium / hard* targets for an exam's purpose; diversifies topics; and reduces repeat exposure when possible. This is **not a trained model or LLM** and does not invent MCQs.
- For every selected question, the backend picks **exactly 1 marked correct option and 3 random marked wrong options**, shuffles the four positions, and persists that individual set for the session.
- Students get different question sets and separately shuffled options when the bank has enough variety. Identical sets cannot be ruled out if the selected bank is very small or exhausted.
- Student UI: exam configuration, live blueprint preview, countdown, question navigator, autosaved answers, resume in the same browser, submission, backend grading and answer review.
- Admin UI: private answer-bank inspection, create tagged MCQs, bulk import via JSON, archive/restore and exam-session history.
- No frontend build tooling, CDN, API key for an LLM, PostgreSQL, or external online service required.

## Run locally (Python)

Install **Python 3.10+**. From the project directory:

```bash
python -m venv .venv
# Linux / macOS
source .venv/bin/activate
# Windows PowerShell
# .venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn backend.main:app --reload
```

Then open **http://127.0.0.1:8000/**. The seeded SQLite database is included under `data/securepaper.db`; if missing or if a different empty data directory is mounted, the app auto-creates it and seeds 90 questions from `seed/seed_questions.json`.

**Demo admin key:** `demo1234` by default for local use. Before hosting, set `SECUREPAPER_ADMIN_KEY` to a long random secret (see `.env.example`). The public student view does not require a key.

## Run with Docker (for hosting / Claude handoff)

```bash
cp .env.example .env
# Edit .env and set a private SECUREPAPER_ADMIN_KEY.
docker compose up --build -d
```

Open **http://localhost:8000/**. The SQLite file is persisted in the Docker named volume `securepaper_data`. To restart after code changes, rebuild; don't delete the volume unless you intend to reset all questions and sessions.

Or deploy the included `Dockerfile` to any Docker-compatible host, expose port `$PORT` (default 8000) and mount a **persistent directory** at `/app/data`. A sample `render.yaml` is included for Render (the persistent disk is a paid-tier feature). If you use a host with ephemeral storage and no mounted disk, changes to questions and sessions will be lost on redeployment.

**Separate frontend hosting:** The app already serves the frontend at `/` and `/static`. For a split frontend/backend deployment, point the JS `api()` calls in `frontend/app.js` at the backend URL, and add the exact frontend origin(s) as comma-separated values in `SECUREPAPER_CORS_ORIGINS` before starting the API. For this demo, same-origin is simpler and safer.

## Try the full demo

1. Under **Create exam**, enter a name and optional student ID. Choose a goal, subjects, question types, number of questions and duration. Read the proposed distribution at the right.
2. Select **Generate unique MCQ paper**. The candidate receives four shuffled choices per question and a timer. Answers are autosaved in SQLite.
3. Submit to see grading and the stored correct answers. Create a second exam with the same student ID to see preference for unseen questions.
4. Open **Question bank**, unlock with the admin key and inspect which choices are marked correct vs wrong. Add one new question with 3+ wrong options, or import `samples_import.json`.
5. Open **Sessions** as an admin to see attempts and scores.

## Database schema

The schema is in `backend/schema.sql` and is applied at startup. SQLite is intentionally used because this is a demo.

| Table | Role |
| --- | --- |
| `questions` | MCQ stem, subject, topic, difficulty, type, active flag |
| `question_options` | Separate option rows with `is_correct=1` or `is_correct=0` |
| `exam_sessions` | Student, purpose, requested blueprint, actual composition, status, timer, score |
| `exam_items` | Questions selected for each student, in per-session order |
| `session_options` | The four options selected and their per-student shuffled positions |
| `session_answers` | Autosaved selections (server scores them against `question_options`) |

`question_options` has a partial unique index preventing multiple correct rows for a question. API imports also require exactly one correct option, at least three distinct wrong ones and non-duplicate answer text.

### Automatic mix by exam purpose

| Purpose | Easy | Medium | Hard |
| --- | ---: | ---: | ---: |
| Practice & learning | 60% | 30% | 10% |
| Class test | 30% | 50% | 20% |
| Competitive exam | 15% | 35% | 50% |
| Quick revision | 45% | 40% | 15% |

These are adaptive **targets**, not a fixed manual distribution. The backend adjusts to available inventory, balances selected subjects and avoids repeating the same topics when possible; the actual mix is saved on every session.

## API reference for later integration

Interactive API docs are automatically available at `/docs` while the server runs. Important routes:

| Method | Path | Role |
| --- | --- | --- |
| `GET` | `/api/health` | Deployment health check |
| `GET` | `/api/meta` | Public subject/type counts and purposes (no answers) |
| `POST` | `/api/blueprint` | Preview a proposed selection for exam requirements |
| `POST` | `/api/sessions` | Create a unique student exam |
| `GET` | `/api/sessions/{session_id}` | Resume an exam; **no correct-answer flags before submission** |
| `POST` | `/api/sessions/{session_id}/answer` | Save/change a choice |
| `POST` | `/api/sessions/{session_id}/submit` | Close and grade |
| `GET` | `/api/admin/questions` | Admin-only question bank with option markers |
| `POST` | `/api/admin/questions` | Admin add one MCQ |
| `POST` | `/api/admin/questions/import` | Admin add 1–500 MCQs from a JSON array (atomic transaction) |
| `PATCH` | `/api/admin/questions/{id}?active=false` | Admin archive (or restore with `true`) |
| `GET` | `/api/admin/sessions` | Admin session history |

All `/api/admin/*` calls must include the HTTP header `X-Admin-Key: <secret>`.

Example exam request:

```json
{
  "student_name": "Demo Student",
  "student_code": "IT-001",
  "goal": "class_test",
  "subjects": ["Electrical", "Chemistry"],
  "question_types": [],
  "question_count": 10,
  "duration_minutes": 20
}
```

`question_types: []` means all types; otherwise use `conceptual`, `numerical`, `application`, and/or `reasoning`. The API rejects a paper request if the question bank cannot supply enough eligible MCQs.

Bulk import shape: use `samples_import.json`. The admin frontend reads a JSON array file and sends it to the import API. Existing questions are never rewritten or generated by the selection engine. `scripts/build_seed.py` recreates the original 90-question seed JSON only (it does not modify a live SQLite database).

## Project structure

```text
securepaper/
├── backend/
│   ├── main.py              FastAPI endpoints, SQLite data layer, grading
│   ├── selector.py          Automatic subject/difficulty/topic selection
│   └── schema.sql           Normalized SQLite schema
├── frontend/
│   ├── index.html           Static UI entry point
│   ├── app.js               Student and admin interactions
│   └── styles.css           Responsive styling
├── seed/seed_questions.json 90 curated MCQs with verified answer markers
├── data/securepaper.db      Ready-to-use, seeded SQLite database
├── samples_import.json     Optional additional questions
├── tests/                  Backend integration tests
├── scripts/build_seed.py   Seed-data preparation
├── legacy/original_demo/   The original uploaded app, preserved as reference
├── Dockerfile, compose.yaml, render.yaml, start.sh
├── requirements.txt, .env.example, .gitignore, .dockerignore
├── CLAUDE_HANDOFF.md
└── README.md
```

## Validation

```bash
python -m pytest -q tests/
```

The **test suite** checks seed integrity, exact 4-option composition, absence of student-visible answer keys, adaptive selection, distinct student sets, saved answers, grading, expiry, admin authorization, bulk import rollback, filters and static frontend delivery. The test package `pytest` and HTTP test client `httpx` are available in many development environments; install for testing if missing:

```bash
pip install pytest httpx
```

## Demo limitations and security notes

This is **not a production examination system**. The rule-based selector is not a trained AI; difficulty tags are instructor-supplied estimates, not psychometrically calibrated. The public exam sessions use secret unguessable URL-style tokens and a single shared admin key, not real user authentication. Anyone with the admin key can see answers. Anyone with a session token can view and submit that session. No proctoring, attempt limits, abuse prevention, per-student accounts, formal exam scheduling, encryption-at-rest or key-share release is included. Use HTTPS, real accounts and authorization, backup policies, rate limits and an audited database before administering important assessments.

The original report-scope code was preserved under `legacy/original_demo/` for reference. Its generation/encryption endpoints are not used by this focused demo.
# secure-q
