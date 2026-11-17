"""Database-only, constraint-aware MCQ selection. No language model or content generation.

A clear heuristic composes an exam according to its purpose, balances subjects and
estimated difficulty, avoids repeated topics/exposure, and adds secure randomness.
"""
from __future__ import annotations

import hashlib
import random
from collections import Counter
from typing import Any

GOALS: dict[str, dict[str, Any]] = {
    'practice': {
        'label': 'Practice & learning',
        'description': 'Approachable questions with a few stretch problems',
        'weights': {'easy': 60, 'medium': 30, 'hard': 10},
    },
    'class_test': {
        'label': 'Class test',
        'description': 'Balanced recall, application and higher-order questions',
        'weights': {'easy': 30, 'medium': 50, 'hard': 20},
    },
    'competitive': {
        'label': 'Competitive exam',
        'description': 'More difficult questions and problem-solving',
        'weights': {'easy': 15, 'medium': 35, 'hard': 50},
    },
    'revision': {
        'label': 'Quick revision',
        'description': 'Broad foundational review across selected subjects',
        'weights': {'easy': 45, 'medium': 40, 'hard': 15},
    },
}
DIFFICULTIES = ('easy', 'medium', 'hard')


def allocate(total: int, weights: dict[str, float], caps: dict[str, int] | None = None) -> dict[str, int]:
    """Largest-remainder allocation honoring per-category inventory limits."""
    keys = list(weights)
    result = {k: 0 for k in keys}
    caps = caps or {k: total for k in keys}
    if sum(caps.get(k, 0) for k in keys) < total:
        raise ValueError('Not enough eligible questions to fulfil this exam.')
    for _ in range(total):
        eligible = [k for k in keys if result[k] < caps.get(k, 0)]
        if not eligible:
            raise ValueError('Not enough eligible questions to fulfil this exam.')
        weight_sum = sum(max(float(weights[k]), 0) for k in keys) or len(keys)
        targets = {k: total * (max(float(weights[k]), 0) or (1 if weight_sum == len(keys) else 0)) / weight_sum for k in keys}
        # Prioritize underrepresented quotas, then stable key ordering.
        chosen = max(eligible, key=lambda k: (targets[k] - result[k], -keys.index(k)))
        result[chosen] += 1
    return result


def blueprint(pool: list[dict], goal: str, subjects: list[str], count: int) -> dict:
    if goal not in GOALS:
        raise ValueError('Unknown exam goal.')
    if count < 1 or count > 40:
        raise ValueError('Question count must be between 1 and 40.')
    subject_caps = Counter(q['subject'] for q in pool)
    if any(subject_caps.get(s, 0) == 0 for s in subjects):
        missing = [s for s in subjects if not subject_caps.get(s, 0)]
        raise ValueError('No eligible MCQs for: ' + ', '.join(missing))
    if len(pool) < count:
        raise ValueError(f'Only {len(pool)} eligible questions are available for your filters; requested {count}.')
    difficulty_caps = Counter(q['difficulty'] for q in pool)
    subject_targets = allocate(count, {s: 1 for s in subjects}, subject_caps)
    difficulty_targets = allocate(count, GOALS[goal]['weights'], difficulty_caps)
    return {
        'goal': goal,
        'goal_label': GOALS[goal]['label'],
        'strategy': 'Rule-based intelligent selection; no generative AI',
        'eligible_questions': len(pool),
        'question_count': count,
        'subjects': subject_targets,
        'difficulty': difficulty_targets,
    }


def fingerprint(selected: list[dict]) -> str:
    return hashlib.sha256(','.join(sorted(q['id'] for q in selected)).encode()).hexdigest()


def select_questions(
    pool: list[dict], plan: dict, seen_by_student: set[str],
    exposure: Counter, prior_fingerprints: set[str],
    rng: random.Random | random.SystemRandom | None = None,
) -> list[dict]:
    """Build individual sessions with adaptive quotas and low-reuse preference.

    If enough fresh questions exist for this student, prior items are excluded.
    Fingerprint collisions with other sessions are retried when alternatives exist.
    """
    rng = rng or random.SystemRandom()
    n = plan['question_count']
    unused = [q for q in pool if q['id'] not in seen_by_student]
    choices = unused if len(unused) >= n else pool
    possible_subject = Counter(q['subject'] for q in choices)
    possible_difficulty = Counter(q['difficulty'] for q in choices)
    subject_quota = allocate(n, {s: plan['subjects'][s] for s in plan['subjects']}, possible_subject)
    diff_quota = allocate(n, {d: max(plan['difficulty'][d], 0.01) for d in DIFFICULTIES}, possible_difficulty)
    best = []
    for attempt in range(12):
        used_subject, used_difficulty, used_type, used_topic = Counter(), Counter(), Counter(), Counter()
        chosen, available = [], choices[:]
        for _ in range(n):
            # Subject quotas are hard; difficulty is a soft target when stock makes
            # a particular subject/difficulty combination impossible.
            allowed = [q for q in available if used_subject[q['subject']] < subject_quota[q['subject']]]
            if not allowed:
                raise ValueError('Unable to satisfy subject quotas with available questions.')
            def value(q):
                d_shortfall = max(0, diff_quota[q['difficulty']] - used_difficulty[q['difficulty']])
                s_shortfall = subject_quota[q['subject']] - used_subject[q['subject']]
                return (
                    18 * (d_shortfall > 0)
                    + 5 * d_shortfall
                    + 2.5 * s_shortfall
                    + (9 if used_topic[(q['subject'], q['topic'])] == 0 else 0)
                    + 5 / (1 + used_type[q['question_type']])
                    - 1.7 * exposure.get(q['id'], 0)
                    - (22 if q['id'] in seen_by_student else 0)
                    + rng.random() * 18
                )
            picked = max(allowed, key=value)
            chosen.append(picked)
            used_subject[picked['subject']] += 1
            used_difficulty[picked['difficulty']] += 1
            used_type[picked['question_type']] += 1
            used_topic[(picked['subject'], picked['topic'])] += 1
            available.remove(picked)
        if fingerprint(chosen) not in prior_fingerprints or len(pool) == n:
            rng.shuffle(chosen)
            return chosen
        best = chosen
    # A previously selected set is acceptable only when no alternate could be found.
    # Option sampling and answer-position shuffle are still independently random.
    rng.shuffle(best)
    return best
