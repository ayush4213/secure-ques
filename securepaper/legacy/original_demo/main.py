import hashlib, hmac, json, os, random, secrets, sqlite3, time, uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from . import crypto_utils as cu, engine

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"; DATA.mkdir(exist_ok=True)
DB = DATA / "securepaper.db"
app = FastAPI(title="SecurePaper")
now = lambda: datetime.now(timezone.utc)


def master() -> bytes:
    if os.environ.get("SECUREPAPER_MASTER_KEY"):
        return hashlib.sha256(os.environ["SECUREPAPER_MASTER_KEY"].encode()).digest()
    f = DATA / "master.key"
    if not f.exists():
        f.write_bytes(os.urandom(32))
    return f.read_bytes()


def db():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    return c


def audit(event, detail):
    detail = detail if isinstance(detail, str) else json.dumps(detail)
    with db() as c:
        prev = c.execute("SELECT hash FROM audit ORDER BY id DESC LIMIT 1").fetchone()
        ts = now().isoformat()
        h = hashlib.sha256(((prev["hash"] if prev else "") + ts + event + detail).encode()).hexdigest()
        c.execute("INSERT INTO audit(ts,event,detail,hash) VALUES(?,?,?,?)", (ts, event, detail, h))


@app.on_event("startup")
def init():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT);
        CREATE TABLE IF NOT EXISTS bank(id TEXT PRIMARY KEY, j TEXT);
        CREATE TABLE IF NOT EXISTS questions(id TEXT PRIMARY KEY, paper_id TEXT, slot_id TEXT, topic TEXT, difficulty TEXT, type TEXT, status TEXT, wrapped_key BLOB, blob BLOB);
        CREATE TABLE IF NOT EXISTS papers(id TEXT PRIMARY KEY, created TEXT, release_at TEXT, k INT, n INT, seed_hash TEXT, cipher BLOB, sig TEXT, status TEXT, summary TEXT);
        CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, event TEXT, detail TEXT, hash TEXT);""")
        if not c.execute("SELECT 1 FROM bank").fetchone():
            for t, d, text, o, a in engine.SEED_BANK:
                i = uuid.uuid4().hex[:8]
                c.execute("INSERT INTO bank VALUES(?,?)", (i, json.dumps({"id": i, "topic": t, "difficulty": d, "text": text, "options": o, "answer": a})))
        if not c.execute("SELECT 1 FROM kv WHERE k='policy'").fetchone():
            c.execute("INSERT INTO kv VALUES('policy',?)", (json.dumps(engine.DEFAULT_POLICY),))


def get_policy():
    with db() as c:
        return json.loads(c.execute("SELECT v FROM kv WHERE k='policy'").fetchone()["v"])


def get_bank():
    with db() as c:
        return [json.loads(r["j"]) for r in c.execute("SELECT j FROM bank")]


# ---------- policy / bank / families ----------
@app.get("/api/policy")
def policy_get():
    return get_policy()


@app.put("/api/policy")
def policy_put(p: dict = Body(...)):
    try:
        n = int(p["total_questions"]); assert 1 <= n <= 100
        for k in ("topics", "difficulty", "types"):
            assert sum(float(v) for v in p[k].values()) > 0
        p["duration_minutes"] = float(p["duration_minutes"])
    except Exception:
        raise HTTPException(400, "Invalid policy")
    with db() as c:
        c.execute("REPLACE INTO kv VALUES('policy',?)", (json.dumps(p),))
    audit("policy_saved", p)
    return p


@app.post("/api/compile")
def compile_preview():
    bank = get_bank()
    try:
        contracts = engine.compile_policy(get_policy(), random.Random(), Counter((b["topic"], b["difficulty"]) for b in bank))
    except ValueError as e:
        raise HTTPException(422, str(e))
    audit("policy_compiled", {"slots": len(contracts)})
    return contracts


@app.get("/api/families")
def families():
    return [{k: f[k] for k in ("id", "topic", "difficulty", "formula", "unknowns")} for f in engine.FAMILIES]


@app.get("/api/bank")
def bank_list():
    return get_bank()


@app.post("/api/bank")
def bank_add(b: dict = Body(...)):
    text, opts = (b.get("text") or "").strip(), [str(o).strip() for o in b.get("options", []) if str(o).strip()]
    if not text or len(opts) < 2 or not 0 <= int(b.get("answer", -1)) < len(opts):
        raise HTTPException(400, "Need question text, 2+ options and a valid answer index")
    topic, diff = engine.auto_tag(text, b.get("topic") or None, b.get("difficulty") or None)
    i = uuid.uuid4().hex[:8]
    item = {"id": i, "topic": topic, "difficulty": diff, "text": text, "options": opts, "answer": int(b["answer"])}
    with db() as c:
        c.execute("INSERT INTO bank VALUES(?,?)", (i, json.dumps(item)))
    audit("question_ingested", {"id": i, "topic": topic, "difficulty": diff})
    return item


@app.delete("/api/bank/{qid}")
def bank_del(qid: str):
    with db() as c:
        c.execute("DELETE FROM bank WHERE id=?", (qid,))
    audit("question_removed", qid)
    return {"ok": True}


@app.post("/api/preview")
def preview(b: dict = Body(...)):
    try:
        c, qs = engine.preview(b["family_id"], min(int(b.get("count", 3)), 10), get_policy(), random.Random())
    except StopIteration:
        raise HTTPException(404, "Unknown family")
    return {"contract": c, "questions": qs}


# ---------- full pipeline ----------
@app.post("/api/papers/run")
def run_paper(b: dict = Body(default={})):
    policy, bank, mk = get_policy(), get_bank(), master()
    k, n, mins = int(b.get("k", 3)), int(b.get("n", 5)), float(b.get("release_in_minutes", 1))
    if not 1 <= k <= n <= 20:
        raise HTTPException(400, "Need 1 <= k <= n <= 20")
    seed, pid, T = secrets.token_hex(16), "P-" + secrets.token_hex(3).upper(), {}
    rng, t = random.Random(seed), time.time()
    try:
        contracts = engine.compile_policy(policy, rng, Counter((x["topic"], x["difficulty"]) for x in bank))
        T["compile_s"] = round(time.time() - t, 2); t = time.time()
        seen, pool, rejected = [x["text"] for x in bank], {}, 0
        for c in contracts:
            cands, r = engine.generate_slot(c, policy, bank, rng, seen)
            if not cands:
                raise ValueError(f"No valid candidate for {c['slot_id']}")
            rejected += r; pool[c["slot_id"]] = cands
            seen += [q["text"] for q in cands if q["type"] == "numerical"]
        T["generate_validate_s"] = round(time.time() - t, 2); t = time.time()
        chosen = engine.assemble(contracts, pool, seed)
        checks = engine.paper_checks(chosen, policy)
        T["select_s"] = round(time.time() - t, 2)
    except ValueError as e:
        audit("run_failed", str(e)); raise HTTPException(422, str(e))
    if not all(x["passed"] for x in checks):
        audit("paper_rejected", checks); raise HTTPException(422, "Paper-level validation failed: " + json.dumps(checks))

    chosen_ids = {q["id"] for q in chosen}
    with db() as c:  # every accepted candidate is encrypted at rest under its own key
        for cands in pool.values():
            for q in cands:
                qk = os.urandom(32)
                c.execute("INSERT INTO questions VALUES(?,?,?,?,?,?,?,?,?)", (q["id"], pid, q["slot_id"], q["topic"], q["difficulty"], q["type"],
                          "selected" if q["id"] in chosen_ids else "eligible", cu.encrypt(mk, qk), cu.encrypt(qk, json.dumps(q).encode(), q["id"].encode())))
    plain = {"paper_id": pid, "title": policy["name"], "duration_minutes": policy["duration_minutes"],
             "questions": [{"no": i + 1, "topic": q["topic"], "difficulty": q["difficulty"], "type": q["type"], "text": q["text"], "options": q["options"]} for i, q in enumerate(chosen)],
             "answer_key": [{"no": i + 1, "answer": "ABCD"[q["answer"]], "value": q["answer_value"]} for i, q in enumerate(chosen)]}
    pkey = os.urandom(32)
    cipher = cu.encrypt(pkey, json.dumps(plain).encode(), pid.encode())
    sig = cu.sign(hashlib.sha256(mk + b"hmac").digest(), cipher)
    shares = cu.split_secret(pkey, k, n)
    release_at = (now() + timedelta(minutes=mins)).isoformat()
    summary = {"slots": len(contracts), "candidates": sum(len(v) for v in pool.values()), "rejected": rejected, "checks": checks, "timings": T}
    with db() as c:
        c.execute("INSERT INTO papers VALUES(?,?,?,?,?,?,?,?,?,?)", (pid, now().isoformat(), release_at, k, n, hashlib.sha256(seed.encode()).hexdigest(), cipher, sig, "sealed", json.dumps(summary)))
    audit("paper_sealed", {"paper": pid, **{x: summary[x] for x in ("slots", "candidates", "rejected")}, "release_at": release_at, "k_of_n": f"{k}/{n}"})
    return {"paper_id": pid, "release_at": release_at, "k": k, "n": n, "shares": shares, **summary}


@app.get("/api/papers")
def papers():
    with db() as c:
        rows = c.execute("SELECT id,created,release_at,k,n,seed_hash,status,summary FROM papers ORDER BY created DESC").fetchall()
    return [{**dict(r), "summary": json.loads(r["summary"]), "locked": now() < datetime.fromisoformat(r["release_at"])} for r in rows]


@app.post("/api/papers/{pid}/release")
def release(pid: str, b: dict = Body(...)):
    with db() as c:
        p = c.execute("SELECT * FROM papers WHERE id=?", (pid,)).fetchone()
    if not p:
        raise HTTPException(404, "Paper not found")
    left = (datetime.fromisoformat(p["release_at"]) - now()).total_seconds()
    if left > 0:
        audit("release_denied_time", {"paper": pid, "seconds_left": int(left)})
        raise HTTPException(403, f"Release window not open yet ({int(left)} s remaining)")
    shares = list(dict.fromkeys(s.strip() for s in b.get("shares", []) if s.strip()))
    if len(shares) < p["k"]:
        audit("release_denied_threshold", {"paper": pid, "got": len(shares)})
        raise HTTPException(403, f"Need {p['k']} distinct shares, got {len(shares)}")
    if not hmac.compare_digest(p["sig"], cu.sign(hashlib.sha256(master() + b"hmac").digest(), p["cipher"])):
        raise HTTPException(500, "Signature mismatch - ciphertext tampered")
    try:
        plain = cu.decrypt(cu.recover_secret(shares[: p["k"]]), p["cipher"], pid.encode())
    except Exception:
        audit("release_denied_bad_shares", {"paper": pid}); raise HTTPException(400, "Invalid shares - decryption failed")
    with db() as c:
        c.execute("UPDATE papers SET status='released' WHERE id=?", (pid,))
    audit("paper_released", {"paper": pid, "shares_used": p["k"]})
    return json.loads(plain)


@app.get("/api/audit")
def audit_list():
    with db() as c:
        return [dict(r) for r in c.execute("SELECT * FROM audit ORDER BY id DESC LIMIT 300")]


@app.get("/")
def index():
    return FileResponse(ROOT / "frontend" / "index.html")

app.mount("/static", StaticFiles(directory=ROOT / "frontend"), name="static")
