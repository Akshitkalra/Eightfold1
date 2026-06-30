"""Confidence scoring.

Per-field confidence in [0,1] combines three deterministic factors:

    field_conf = trust_weight(winning_source)   # how reliable the source is
               * agreement_factor               # boost when sources agree, penalty on conflict
               * completeness_factor             # full vs partial value

overall_confidence is the weighted mean of populated field confidences.
No randomness: identical inputs always yield identical scores.
"""
from __future__ import annotations

from .canonical import trust_weight


def agreement_factor(n_agree: int, n_conflict: int) -> float:
    """>1 boost when multiple sources agree, <1 penalty when sources conflict.

    Clamped to [0.6, 1.15]. One lone source is neutral (1.0).
    """
    factor = 1.0 + 0.08 * max(0, n_agree - 1) - 0.18 * n_conflict
    return max(0.6, min(1.15, factor))


def completeness_factor(value) -> float:
    """Partial values score lower. Empty -> 0."""
    if value is None or value == "" or value == []:
        return 0.0
    if isinstance(value, dict):
        present = sum(1 for v in value.values() if v not in (None, "", [], {}))
        total = max(1, len(value))
        return 0.5 + 0.5 * (present / total)
    return 1.0


def field_confidence(source: str, n_agree: int, n_conflict: int, value) -> float:
    """Combine the three factors into a clamped [0,1] confidence."""
    score = (
        trust_weight(source)
        * agreement_factor(n_agree, n_conflict)
        * completeness_factor(value)
    )
    return round(max(0.0, min(1.0, score)), 3)


def overall_confidence(field_confs: dict[str, float]) -> float:
    """Weighted mean over populated fields. Identity fields weigh a bit more."""
    if not field_confs:
        return 0.0
    weights = {
        "full_name": 1.5, "emails": 1.5, "phones": 1.2,
        "skills": 1.0, "experience": 1.0, "education": 0.8,
    }
    num = den = 0.0
    for field, conf in field_confs.items():
        w = weights.get(field, 1.0)
        num += w * conf
        den += w
    return round(num / den, 3) if den else 0.0
