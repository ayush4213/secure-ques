# SecurePaper — policy-governed AI question paper system

## Run
```bash
python -m venv venv && source venv/bin/activate     # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn backend.main:app --reload
```
Open http://127.0.0.1:8000  (needs internet once for the React/Tailwind CDN scripts).

Optional: `export ANTHROPIC_API_KEY=...` lets the LLM reword questions (numbers are re-verified; falls back to templates).
Optional: `SECUREPAPER_MASTER_KEY=...` sets the master key (otherwise `data/master.key` is created).

## Demo flow
1. **Policy** → Save → *Compile* to see slot contracts / autonomy envelopes.
2. **Generate Preview** → pick a family, see bounded generation + validation badges.
3. **Papers** → *Generate & seal* (release in 0.5 min) → wait for the countdown → *Request release* with k shares.
   Fewer than k shares, wrong shares, or early release are denied and audited.
4. **Audit** → hash-chained log of every event.

## Layout
- `backend/crypto_utils.py` AES-256-GCM, HMAC-SHA-256, Shamir k-of-n
- `backend/engine.py` policy compiler, DoF envelopes, families, SymPy validators, similarity, randomiser + constraint checks
- `backend/main.py` FastAPI + SQLite API
- `frontend/index.html` React (CDN) UI
