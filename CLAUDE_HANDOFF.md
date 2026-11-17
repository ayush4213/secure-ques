# SecurePaper MCQ demo — integration and hosting handoff

This archive is intended to be handed to Claude (or a developer) for **hosting and final integration**. The implementation is complete for a local single-service demonstration; no deployment or production security approval is claimed.

## Objective and decisions implemented

- **Database only:** never generate or rewrite the questions.
- Question tags: subject (Electrical, Chemistry, Physics, Mathematics, Computer Science), topic, difficulty (`easy`/`medium`/`hard`) and question type (`conceptual`, `numerical`, `application`, `reasoning`).
- Each question has exactly one `is_correct = 1` row and at least three `is_correct = 0` option rows. Seed questions have one right + five wrong.
- Dynamic exam planning based on purpose, not manually supplied percentages; subject/difficulty mix can adapt to stock.
- For each student and each question: sample 1 right + 3 wrong; shuffle order; store immutable selected option IDs; hide correct markers from students until after grading.
- Distinct question selection across student sessions when inventory allows; prefer unseen questions for the same student ID.
- Student web exam + admin question bank + grading, no encryption/timed-release or AI text generation.

## Start / deploy

From project root:

```bash
pip install -r requirements.txt
SECUREPAPER_ADMIN_KEY='replace-this-with-a-private-secret' uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

With persistent Docker volume:

```bash
cp .env.example .env
# Edit the admin key
docker compose up --build -d
```

- Docker starts the same app on `$PORT` (8000 by default).
- Persistent disk location: `SECUREPAPER_DATA_DIR` defaults to `<project>/data`; Docker default is `/app/data`.
- Seed source is deliberately **outside the mutable database directory** at `seed/seed_questions.json` so an empty mounted volume can be initialized safely.
- Optional separate frontend origin: set `SECUREPAPER_CORS_ORIGINS` to explicit comma-separated URL origins, then modify the base in `frontend/app.js` `api()`.
- `/api/health` is the health-check endpoint; `/docs` provides an OpenAPI contract.
- On providers without persistent volumes, user-added questions and attempts disappear on restart/redeploy.

## Integration points

- `backend/main.py` — all API routes, Pydantic validations, database persistence, answer marking, autosave and scoring.
- `backend/selector.py` — goal→difficulty preference, adaptive allocation and randomized selection. If a real LLM is added later, confine it to proposing distribution weights **from allowed subject tags**; keep question IDs and correctness determined by the database and server-side validators.
- `frontend/app.js` — self-contained UI, `api()` helper at top for changing backend base URL. No React build step.
- `backend/schema.sql` — SQLite DDL. If migrating to PostgreSQL, update queries/connection management, preserving exactly-one-correct and session-option snapshot invariants.
- `tests/test_mcq_api.py` — executable API contract and expected behavior.

## Deployment review checklist

1. Set **nondefault** admin key via secret environment variable.
2. Configure HTTPS/domain, proxy forwarded headers and a persisted volume for the DB.
3. Check `/api/health`, `GET /api/meta` and student exam flow.
4. Check admin login, add question, import, archive and restore.
5. Test two students, 4-option selection, correct scoring and expiry.
6. Back up SQLite database (use SQLite backup API or clean service stop, not blindly copying live WAL files).
7. If running a high-stakes exam, add real user/admin identity and access control, anti-cheating controls, rate limits, monitoring and additional privacy protections.
8. Keep the legacy demo under `legacy/original_demo` as archival reference, not part of deployed entrypoint.

## Key caveat

"AI" here means an **offline intelligent rule-based selector** (constraint-aware heuristics and stochastic diversification), not a learned model. It chooses only stored MCQ IDs, not new content. This is intentional for reliable demo-level delivery without API keys, internet, hallucinations or extra hosting services.
