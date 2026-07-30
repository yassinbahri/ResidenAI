"""Combines the two independent automatic signals - company domicile
(domicile_classifier.py) and processing-location residency
(residency_classifier.py) - into one score. EU/EEA-domiciled companies are
weighted at least as heavily as processing location, since the legal
jurisdiction the company itself operates under doesn't change just because
they let you pick a hosting region (the Schrems II / CLOUD Act distinction).

This is an aggregate of two heuristic signals, not a certified compliance
rating - the tiers exist to make the numbers legible at a glance, not to
imply more precision than the underlying classifiers actually have.
"""

from __future__ import annotations

_DOMICILE_POINTS = {
    "eu_domiciled": 50,
    "unclear": 15,
    "non_eu_domiciled": 0,
    # A provider whose sources contradict each other on domicile is neither
    # confirmed-good nor confirmed-bad - scored like "unclear" (the honest
    # "we don't have a single answer" case), but surfaced as its own tier
    # below so it isn't confused with a plain absence of evidence.
    "conflicting": 15,
}

_RESIDENCY_POINTS = {
    "available": 50,
    "selectable": 30,
    "unclear": 15,
    "not_available": 0,
}

# Checked highest-first; the first threshold the score meets or exceeds wins.
_TIERS = (
    (80, "Strong EU alignment"),
    (50, "Moderate EU alignment"),
    (25, "Weak EU alignment"),
    (0, "Low EU alignment"),
)


def compute_eu_alignment_score(domicile_status: str, eu_eea_status: str) -> tuple[int, str]:
    score = _DOMICILE_POINTS.get(domicile_status, 15) + _RESIDENCY_POINTS.get(eu_eea_status, 15)

    # Contradictory evidence takes priority over every other tier - it's a
    # real finding (two of the provider's own sources disagree), not
    # something the score alone should quietly average away.
    if domicile_status == "conflicting":
        return score, "Conflicting evidence"

    # Both signals unclear means no evidence was ever found either way - not
    # a confirmed weak vendor, just an unresolved one. The numeric score
    # (still shown) would otherwise land in "Weak EU alignment," implying a
    # negative finding rather than an absence of evidence.
    if domicile_status == "unclear" and eu_eea_status == "unclear":
        return score, "Insufficient data"

    for threshold, label in _TIERS:
        if score >= threshold:
            return score, label
    return score, _TIERS[-1][1]
