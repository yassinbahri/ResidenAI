"""Deterministic, keyword/phrase-based classifier for the one question this
whole tool exists to answer: is this product's data resident in the EU/EEA,
or not? Not an LLM, not a legal conclusion - a fast, explainable, fully
automatic signal with visible evidence, re-run on every check so it never
needs a human to write anything (see app/tracker/run.py).

Deliberately simple regex matching over rapidfuzz/embeddings/an LLM: the
same "small model where a bigger one isn't earning its keep" judgment
ShadowAI's own scope_risk.py already makes. This will be wrong sometimes -
that's why every verdict carries the matched quote and its source, so a
human can spot-check rather than trust it blindly.

Priority order (checked in this order, first match wins): NOT_AVAILABLE
before SELECTABLE before AVAILABLE. An explicit denial is a strong,
unambiguous signal and is checked first on purpose - a false "available"
claim is more harmful to a compliance user than missing a subtler positive
statement, matching this project's stance of never overstating compliance.

The same stance is why positive matches are additionally filtered for
forward-looking phrasing (see text_matching.is_forward_looking): a roadmap
promise reads as a capability claim to a regex but is not one in fact.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.tracker.text_matching import find_match

_NOT_AVAILABLE_PATTERNS = [
    # "never" and an optional "be" alongside "not": the original
    # "not available in ..." shape missed both future-tense denials a vendor
    # actually writes - "will not be available in the EU" fell through to
    # "unclear", and "will never be available in Europe" was matched by the
    # "available in europe" positive pattern instead and reported as
    # AVAILABLE, turning an explicit denial into a compliance claim.
    re.compile(
        r"(?:not|never)\s+(?:currently\s+)?(?:be\s+)?available\s+(?:in|within)\s+"
        r"(?:the )?(?:eu\b|europe|european union|eea)",
        re.I,
    ),
    re.compile(r"do(?:es)? not (?:currently )?offer[^.]{0,40}(?:eu\b|europe|european union|eea)", re.I),
    re.compile(r"only available in the united states", re.I),
    re.compile(r"\bus[- ]only\b", re.I),
    re.compile(r"no (?:eu|europe|european union|eea) region", re.I),
]

_SELECTABLE_PATTERNS = [
    re.compile(r"(?:select|choose|selecting|choosing)\s+europe as", re.I),
    re.compile(r"you can choose[^.]{0,40}(?:eu\b|europe|european union|eea)", re.I),
    re.compile(r"customers?\s+(?:can|may)\s+choose[^.]{0,40}(?:eu\b|europe|european union|eea)", re.I),
    re.compile(r"\bdata zone\b", re.I),
    re.compile(r"eligible (?:customers|accounts|api customers)[^.]{0,60}(?:eu\b|europe|european union|eea)", re.I),
]

_AVAILABLE_PATTERNS = [
    re.compile(r"data residency (?:in|within) (?:the )?(?:eu\b|europe|european union|eea)", re.I),
    re.compile(r"(?:eu|europe|european union) data residency", re.I),
    re.compile(r"(?:hosted|processed|stored) (?:in|within) (?:the )?(?:eu\b|europe|european union|eea)", re.I),
    re.compile(r"\beu region\b", re.I),
    re.compile(r"\beurope region\b", re.I),
    re.compile(r"available in europe", re.I),
]


@dataclass(frozen=True)
class ResidencyAssessment:
    status: str  # "available" | "selectable" | "not_available" | "unclear"
    evidence_quote: str | None
    evidence_source_key: str | None
    evidence_char_start: int | None = None
    evidence_char_end: int | None = None


def classify_eu_eea_residency(texts_by_source_key: dict[str, str]) -> ResidencyAssessment:
    """texts_by_source_key: normalized_content of the *latest* document
    version for every source belonging to one product, keyed by
    source_key. Empty dict (no content captured yet) returns "unclear"."""
    # skip_forward_looking is set for the two positive verdicts only: a vendor
    # that "plans to offer" or has EU residency "coming soon" does not have it
    # today, and recording that as available/selectable overstates compliance.
    # An explicit denial stays a denial however it is tensed, so
    # not_available deliberately does not skip these.
    for patterns, status, skip_future in (
        (_NOT_AVAILABLE_PATTERNS, "not_available", False),
        (_SELECTABLE_PATTERNS, "selectable", True),
        (_AVAILABLE_PATTERNS, "available", True),
    ):
        found = find_match(patterns, texts_by_source_key, skip_forward_looking=skip_future)
        if found:
            source_key, quote, char_start, char_end = found
            return ResidencyAssessment(
                status=status,
                evidence_quote=quote,
                evidence_source_key=source_key,
                evidence_char_start=char_start,
                evidence_char_end=char_end,
            )

    return ResidencyAssessment(status="unclear", evidence_quote=None, evidence_source_key=None)
