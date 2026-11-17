"""Policy compiler, bounded generator, deterministic validators, selector."""
import json, os, random, re, urllib.request, uuid
from collections import Counter
import sympy as sp

DIFF_TARGET = {"easy": 1.5, "medium": 3.0, "hard": 4.5}
SECONDS = {"numerical": {"easy": 60, "medium": 90, "hard": 150},
           "conceptual": {"easy": 45, "medium": 75, "hard": 120}}
AUTONOMY = {  # derived autonomy envelope per difficulty (hard => less freedom)
    "easy":   dict(numeric_freedom=.95, wording_freedom=.90, context_freedom=.65, formula_freedom=.20, unknown_freedom=.80),
    "medium": dict(numeric_freedom=.90, wording_freedom=.85, context_freedom=.60, formula_freedom=.20, unknown_freedom=.70),
    "hard":   dict(numeric_freedom=.70, wording_freedom=.60, context_freedom=.30, formula_freedom=.10, unknown_freedom=.50),
}
ZERO = dict(numeric_freedom=0, wording_freedom=0, context_freedom=0, formula_freedom=0, unknown_freedom=0)

DEFAULT_POLICY = {
    "name": "Demo Paper Policy", "total_questions": 20, "duration_minutes": 35,
    "topics": {"Arithmetic": 40, "Mechanics": 30, "Electricity": 30},
    "difficulty": {"easy": 25, "medium": 50, "hard": 25},
    "types": {"numerical": 60, "conceptual": 40},
    "max_reference_examples": 3, "similarity_threshold": 0.9, "candidates_per_slot": 3,
}


def F(id, topic, diff, formula, out, out_lab, unknowns, ctx, vars_):
    return dict(id=id, topic=topic, difficulty=diff, formula=formula, out=out, out_lab=out_lab,
                unknowns=unknowns, ctx=ctx, vars=vars_)

FAMILIES = [
    F("arith-linear", "Arithmetic", "easy", "Y = P - Q*R + K", "Y", ("result", ""), ["Y", "P", "Q", "R", "K"],
      "a number puzzle", {"P": ("first number", "", 20, 99), "Q": ("multiplier", "", 2, 9), "R": ("second number", "", 2, 9), "K": ("constant", "", 1, 20)}),
    F("arith-grouped", "Arithmetic", "medium", "Y = (P + Q)*R - K", "Y", ("result", ""), ["Y", "P", "Q", "K"],
      "a grouped-expression problem", {"P": ("first term", "", 5, 40), "Q": ("second term", "", 5, 40), "R": ("factor", "", 2, 9), "K": ("offset", "", 1, 30)}),
    F("arith-hard", "Arithmetic", "hard", "Y = (P - Q)*R + S*T", "Y", ("result", ""), ["Y", "P", "Q", "S"],
      "a multi-step arithmetic problem", {"P": ("minuend", "", 30, 99), "Q": ("subtrahend", "", 2, 29), "R": ("factor", "", 2, 9), "S": ("coefficient", "", 2, 9), "T": ("multiplier", "", 2, 9)}),
    F("mech-v", "Mechanics", "easy", "v = u + a*t", "v", ("final velocity", "m/s"), ["v", "u", "a", "t"],
      "uniformly accelerated motion", {"u": ("initial velocity", "m/s", 1, 20), "a": ("acceleration", "m/s^2", 1, 9), "t": ("time", "s", 1, 12)}),
    F("mech-s", "Mechanics", "medium", "s = u*t + a*t**2/2", "s", ("displacement", "m"), ["s", "u", "a"],
      "straight-line motion", {"u": ("initial velocity", "m/s", 1, 20), "a": ("acceleration", "m/s^2", 2, 10), "t": ("time", "s", 2, 10)}),
    F("mech-energy", "Mechanics", "hard", "E = m*g*h + m*v**2/2", "E", ("total mechanical energy", "J"), ["E", "m", "h"],
      "a falling-body energy problem", {"m": ("mass", "kg", 2, 10), "g": ("gravitational acceleration", "m/s^2", 10, 10), "h": ("height", "m", 2, 20), "v": ("speed", "m/s", 2, 12)}),
    F("elec-ohm", "Electricity", "easy", "V = I*R", "V", ("voltage", "V"), ["V", "I", "R"],
      "a resistor circuit", {"I": ("current", "A", 1, 12), "R": ("resistance", "ohm", 2, 30)}),
    F("elec-power", "Electricity", "medium", "P = I**2*R", "P", ("power", "W"), ["P", "R"],
      "a heating element", {"I": ("current", "A", 2, 10), "R": ("resistance", "ohm", 2, 25)}),
    F("elec-series", "Electricity", "hard", "V = I*(R1 + R2) + I*R3", "V", ("supply voltage", "V"), ["V", "I", "R1", "R3"],
      "a series circuit", {"I": ("current", "A", 1, 8), "R1": ("first resistance", "ohm", 2, 20), "R2": ("second resistance", "ohm", 2, 20), "R3": ("third resistance", "ohm", 2, 20)}),
]

SEED_BANK = [
    ("Arithmetic", "easy", "Which of these is a prime number?", ["21", "29", "33", "39"], 1),
    ("Arithmetic", "easy", "Which property is expressed by a + b = b + a?", ["Commutative", "Associative", "Distributive", "Identity"], 0),
    ("Arithmetic", "medium", "The LCM of 12 and 18 is", ["36", "54", "72", "6"], 0),
    ("Arithmetic", "medium", "Which number is divisible by both 3 and 4?", ["18", "24", "30", "42"], 1),
    ("Arithmetic", "hard", "The sum of the first n odd natural numbers equals", ["n", "n^2", "n(n+1)/2", "2n"], 1),
    ("Arithmetic", "hard", "How many positive divisors does 36 have?", ["6", "8", "9", "12"], 2),
    ("Mechanics", "easy", "The SI unit of force is", ["Joule", "Newton", "Watt", "Pascal"], 1),
    ("Mechanics", "easy", "A body stays at rest unless a net force acts on it. This is", ["Newton's first law", "Newton's second law", "Newton's third law", "Law of gravitation"], 0),
    ("Mechanics", "medium", "Which of these quantities is a vector?", ["Speed", "Distance", "Displacement", "Mass"], 2),
    ("Mechanics", "medium", "Under constant acceleration, the velocity-time graph is", ["A horizontal line", "A straight inclined line", "A parabola", "A circle"], 1),
    ("Mechanics", "hard", "On level ground, a projectile has maximum range at a launch angle of", ["30 deg", "45 deg", "60 deg", "90 deg"], 1),
    ("Mechanics", "hard", "At the highest point of a projectile's path, its acceleration is", ["Zero", "g downward", "g upward", "Horizontal"], 1),
    ("Electricity", "easy", "The SI unit of resistance is", ["Ohm", "Volt", "Ampere", "Farad"], 0),
    ("Electricity", "easy", "Which instrument measures electric current?", ["Voltmeter", "Ammeter", "Wattmeter", "Hygrometer"], 1),
    ("Electricity", "medium", "Resistors in series have an equivalent resistance equal to the", ["Reciprocal of the sum", "Sum of resistances", "Product", "Difference"], 1),
    ("Electricity", "medium", "In a parallel circuit, which quantity is the same across every branch?", ["Current", "Voltage", "Resistance", "Power"], 1),
    ("Electricity", "hard", "Doubling a wire's length (same material and area) makes its resistance", ["Half", "Double", "Four times", "Unchanged"], 1),
    ("Electricity", "hard", "Kirchhoff's current law follows from conservation of", ["Energy", "Charge", "Momentum", "Mass"], 1),
]

KEYWORDS = {"Arithmetic": ["prime", "lcm", "hcf", "divisible", "sum", "number", "fraction", "percent"],
            "Mechanics": ["force", "velocity", "acceleration", "newton", "projectile", "momentum", "displacement"],
            "Electricity": ["current", "voltage", "resistance", "ohm", "circuit", "kirchhoff", "ampere"]}


def auto_tag(text, topic=None, difficulty=None):
    """Simple keyword tagger standing in for the LLM tagging module."""
    low = text.lower()
    if not topic:
        topic = max(KEYWORDS, key=lambda t: sum(w in low for w in KEYWORDS[t]))
    if not difficulty:
        difficulty = "easy" if len(text) < 60 else "medium" if len(text) < 110 else "hard"
    return topic, difficulty


# ---------- policy compiler ----------
def allocate(total, pct):
    s = sum(pct.values()) or 1
    raw = {k: total * v / s for k, v in pct.items()}
    base = {k: int(v) for k, v in raw.items()}
    for k in sorted(raw, key=lambda k: raw[k] - base[k], reverse=True)[: total - sum(base.values())]:
        base[k] += 1
    return base


def expand(alloc):
    return [k for k, v in alloc.items() for _ in range(v)]


def make_contract(i, topic, diff, qtype, policy):
    a = AUTONOMY[diff] if qtype == "numerical" else ZERO
    return {"slot_id": f"Q-{i + 1:03d}", "topic_region": [topic], "difficulty": diff,
            "difficulty_target": f"{DIFF_TARGET[diff]} +/- 0.3", "allowed_types": [qtype],
            "dof_level": (3 if diff != "hard" else 2) if qtype == "numerical" else 0,
            "max_reference_examples": policy.get("max_reference_examples", 3),
            "similarity_threshold": policy.get("similarity_threshold", 0.9),
            **a, "deterministic_validation": "required" if qtype == "numerical" else "n/a (stored item)"}


def compile_policy(policy, rng, bank_counts):
    n = int(policy["total_questions"])
    fam_topics = {f["topic"] for f in FAMILIES}
    bad = [t for t in policy["topics"] if t not in fam_topics]
    if bad:
        raise ValueError(f"Topics outside the approved syllabus: {bad}")
    topics = expand(allocate(n, policy["topics"]))
    for _ in range(300):
        diffs, types = expand(allocate(n, policy["difficulty"])), expand(allocate(n, policy["types"]))
        rng.shuffle(diffs); rng.shuffle(types)
        need = Counter((t, d) for t, d, ty in zip(topics, diffs, types) if ty == "conceptual")
        if all(bank_counts.get(k, 0) >= v for k, v in need.items()):
            return [make_contract(i, t, d, ty, policy) for i, (t, d, ty) in enumerate(zip(topics, diffs, types))]
    raise ValueError("Question bank too small for this policy. Upload more conceptual questions or lower the conceptual share.")


# ---------- generation + deterministic validation ----------
def jaccard(a, b):
    A, B = set(re.findall(r"\w+", a.lower())), set(re.findall(r"\w+", b.lower()))
    return len(A & B) / len(A | B) if A | B else 0


def llm_reword(text):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return text
    try:
        body = {"model": os.environ.get("SECUREPAPER_MODEL", "claude-sonnet-4-6"), "max_tokens": 300,
                "messages": [{"role": "user", "content": "Rewrite this exam question in different words. Keep every number, symbol, unit and formula EXACTLY unchanged. Return only the question.\n\n" + text}]}
        req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(body).encode(),
                                     headers={"content-type": "application/json", "x-api-key": key, "anthropic-version": "2023-06-01"})
        new = json.loads(urllib.request.urlopen(req, timeout=20).read())["content"][0]["text"].strip()
        nums = lambda s: sorted(re.findall(r"\d+", s))
        return new if nums(new) == nums(text) else text  # numbers must survive rewording
    except Exception:
        return text


def lab(fam, v):
    return fam["vars"][v][:2] if v in fam["vars"] else fam["out_lab"]


def generate_numerical(fam, c, rng):
    out = fam["out"]
    rhs = fam["formula"].split("=")[1].strip()
    syms = {v: sp.Symbol(v) for v in [*fam["vars"], out]}
    expr = sp.sympify(rhs, locals=syms)
    for _ in range(80):
        vals = {v: rng.randint(lo, lo + int((hi - lo) * c["numeric_freedom"])) for v, (_l, _u, lo, hi) in fam["vars"].items()}
        res = expr.subs({syms[v]: x for v, x in vals.items()})          # 1) forward computation
        if not (res.is_integer and res > 0):
            continue
        vals[out] = int(res)
        unknown = out if c["unknown_freedom"] < 0.3 else rng.choice(fam["unknowns"])
        known = {syms[v]: x for v, x in vals.items() if v != unknown}
        sols = [s for s in sp.solve(sp.Eq(syms[out], expr).subs(known), syms[unknown]) if s.is_real and s > 0]  # 2) independent solve
        if len(sols) != 1 or sols[0] != vals[unknown]:
            continue
        fmt = lambda v: f"{lab(fam, v)[0]} ({v}) = {vals[v]}" + (f" {lab(fam, v)[1]}" if lab(fam, v)[1] else "")
        given = ", ".join(fmt(v) for v in [*fam["vars"], out] if v != unknown)
        target, formula = f"the {lab(fam, unknown)[0]} ({unknown})", fam["formula"].replace("**", "^")
        styles = [f"Given the relation {formula}, with {given}, find {target}.",
                  f"A system obeys {formula}. It is known that {given}. Determine {target}.",
                  f"In {fam['ctx']}, the quantities satisfy {formula}. If {given}, what is {target}?"]
        si = rng.randrange(3) if c["wording_freedom"] >= .5 else 0
        if si == 2 and c["context_freedom"] < .5:
            si = 0
        text = llm_reword(styles[si]) if c["wording_freedom"] >= .5 else styles[si]
        ans, opts = vals[unknown], {vals[unknown]}
        while len(opts) < 4:
            d = ans + rng.choice([-1, 1]) * rng.randint(1, max(3, ans // 4))
            if d > 0:
                opts.add(d)
        opts = list(opts); rng.shuffle(opts)
        est = DIFF_TARGET[fam["difficulty"]] + (0.15 if unknown != out else 0) + (0.1 if ans >= 50 else 0)
        checks = [("forward_formula_computation", True), ("independent_symbolic_solve", True),
                  ("positive_integer_unique_answer", True), ("syllabus_boundary", fam["topic"] == c["topic_region"][0]),
                  ("difficulty_in_target_band(heuristic)", abs(est - DIFF_TARGET[c["difficulty"]]) <= 0.31)]
        if not all(ok for _, ok in checks):
            continue
        return {"id": uuid.uuid4().hex[:8], "slot_id": c["slot_id"], "src": f"{fam['id']}:{unknown}:{sorted(vals.items())}",
                "topic": fam["topic"], "difficulty": c["difficulty"], "type": "numerical", "family": fam["id"], "unknown": unknown,
                "text": text, "options": [str(o) for o in opts], "answer": opts.index(ans), "answer_value": ans,
                "est_seconds": SECONDS["numerical"][c["difficulty"]], "est_difficulty": round(est, 2),
                "validation": [{"check": n, "passed": ok} for n, ok in checks]}
    return None


def generate_slot(c, policy, bank, rng, seen):
    topic, diff, qtype = c["topic_region"][0], c["difficulty"], c["allowed_types"][0]
    if qtype == "conceptual":  # DoF 0: use approved item exactly as stored
        return [{"id": uuid.uuid4().hex[:8], "slot_id": c["slot_id"], "src": "bank:" + b["id"], "topic": topic, "difficulty": diff,
                 "type": "conceptual", "family": "bank", "unknown": "-", "text": b["text"], "options": b["options"], "answer": b["answer"],
                 "answer_value": b["options"][b["answer"]], "est_seconds": SECONDS["conceptual"][diff], "est_difficulty": DIFF_TARGET[diff],
                 "validation": [{"check": "approved_bank_item", "passed": True}]} for b in bank if b["topic"] == topic and b["difficulty"] == diff], 0
    fams = [f for f in FAMILIES if f["topic"] == topic and f["difficulty"] == diff] or [f for f in FAMILIES if f["topic"] == topic]
    n, out, rejected, local = policy.get("candidates_per_slot", 3), [], 0, list(seen)
    for _ in range(n * 15):
        if len(out) >= n:
            break
        q = generate_numerical(rng.choice(fams), c, rng)
        if not q:
            rejected += 1; continue
        sim = max((jaccard(q["text"], s) for s in local), default=0)
        ok = sim < c["similarity_threshold"]
        q["validation"].append({"check": f"similarity<{c['similarity_threshold']} (max={sim:.2f})", "passed": ok})
        if not ok:
            rejected += 1; continue
        out.append(q); local.append(q["text"])
    return out, rejected


def preview(fam_id, count, policy, rng):
    fam = next(f for f in FAMILIES if f["id"] == fam_id)
    c = make_contract(0, fam["topic"], fam["difficulty"], "numerical", policy)
    c["slot_id"] = "PREVIEW"
    return c, [q for q in (generate_numerical(fam, c, rng) for _ in range(count)) if q]


# ---------- selection + paper-level validation ----------
def assemble(contracts, pool, seed):
    rng, used, concepts, chosen = random.Random("select:" + seed), set(), Counter(), []
    for c in contracts:
        cands = [q for q in pool[c["slot_id"]] if q["src"] not in used]
        if not cands:
            raise ValueError(f"No unused eligible candidate for {c['slot_id']}")
        rng.shuffle(cands)
        cands.sort(key=lambda q: concepts[(q["family"], q["unknown"])])  # prefer unseen concepts
        q = cands[0]
        used.add(q["src"]); concepts[(q["family"], q["unknown"])] += 1; chosen.append(q)
    return chosen


def paper_checks(chosen, policy):
    n = len(chosen)
    res = []
    for name, key in [("topic_distribution", "topics"), ("difficulty_distribution", "difficulty"), ("type_distribution", "types")]:
        field = {"topics": "topic", "difficulty": "difficulty", "types": "type"}[key]
        want, got = allocate(n, policy[key]), dict(Counter(q[field] for q in chosen))
        res.append({"check": name, "passed": all(got.get(k, 0) == v for k, v in want.items()), "detail": f"required {want} / got {got}"})
    secs = sum(q["est_seconds"] for q in chosen)
    res.append({"check": "expected_time", "passed": secs <= policy["duration_minutes"] * 60, "detail": f"{secs / 60:.1f} of {policy['duration_minutes']} min"})
    res.append({"check": "no_duplicate_items", "passed": len({q["src"] for q in chosen}) == n, "detail": f"{n} unique"})
    return res
