"""Shared deterministic text-matching helpers used by both
residency_classifier.py and domicile_classifier.py - regex over fetched
page text, negation-aware, always returns the matched quote with context so
a human can spot-check rather than trust a verdict blindly."""

from __future__ import annotations

import re

CONTEXT_CHARS = 60
MAX_QUOTE_LENGTH = 400
NEGATION_LOOKBACK_CHARS = 40
# Wider than the negation window (and matching domicile_classifier.py's 80-char
# self-reference lookback), because a plan cue sits at the head of the sentence
# while the claim it qualifies can be at the tail: in "We are working on letting
# customers choose Europe as their data zone" the cue is ~42 chars ahead of the
# matched phrase. Safe to widen because both windows are clipped to the match's
# own clause (see _clause_around) - a cue only qualifies a claim in the same
# statement, so widening reaches more of that statement rather than spilling
# into neighbouring ones.
FUTURE_LOOKBACK_CHARS = 80
FUTURE_LOOKAHEAD_CHARS = 60

# Sentence/clause terminators. A cue on the far side of one of these belongs to
# a different statement: "Data is stored in the EU region today. We will be
# adding more regions soon." is a present-tense fact followed by an unrelated
# roadmap note, not a promise - clipping at the boundary is what keeps the
# forward-looking filter from suppressing genuine claims.
_CLAUSE_BOUNDARY = re.compile(r"[.;!?\n]")

# Catches cases like "...is not currently EU data residency compliant" -
# without this, a plain positive-phrase pattern would misread an explicit
# denial as a positive claim.
NEGATION_CUES = re.compile(r"\b(not|isn't|doesn't|does not|cannot|can't|no longer)\b", re.I)

# Roadmap/aspiration cues. A vendor saying it *intends* to offer EU residency
# is not offering it today, but the phrase still contains the positive wording
# the availability patterns look for - so "we plan to offer data residency in
# the EU" was being recorded as "available". Treated like negation: the match
# is skipped, so the verdict degrades to "unclear" (no evidence found) rather
# than asserting a capability the vendor hasn't shipped. Only applied to
# positive claims - a forward-looking *denial* ("will not be available in the
# EU") is still a denial and must keep counting.
FUTURE_CUES = re.compile(
    r"\b(?:plans?\s+to|planning\s+to|intends?\s+to|aims?\s+to|hopes?\s+to|expects?\s+to|"
    r"working\s+(?:on|towards?)|coming\s+soon|on\s+(?:our|the)\s+roadmap|roadmap|"
    r"not\s+yet|in\s+the\s+future|later\s+this\s+year|upcoming|will\s+(?:soon\s+)?(?:be|offer|support|add|launch))\b",
    re.I,
)


def is_negated(text: str, match_start: int) -> bool:
    window_start = max(0, match_start - NEGATION_LOOKBACK_CHARS)
    return bool(NEGATION_CUES.search(text[window_start:match_start]))


def _clause_around(text: str, match_start: int, match_end: int) -> tuple[str, str]:
    """The text immediately before and after the match, bounded by the
    lookback/lookahead limits and clipped at the nearest clause boundary so a
    cue in a neighbouring sentence is not attributed to this match."""
    before = text[max(0, match_start - FUTURE_LOOKBACK_CHARS) : match_start]
    boundaries = list(_CLAUSE_BOUNDARY.finditer(before))
    if boundaries:
        before = before[boundaries[-1].end() :]

    after = text[match_end : match_end + FUTURE_LOOKAHEAD_CHARS]
    boundary = _CLAUSE_BOUNDARY.search(after)
    if boundary:
        after = after[: boundary.start()]

    return before, after


def is_forward_looking(text: str, match_start: int, match_end: int) -> bool:
    """True when a roadmap/aspiration cue sits within the match's own clause,
    making it a statement of intent rather than of present fact."""
    before, after = _clause_around(text, match_start, match_end)
    return bool(FUTURE_CUES.search(before) or FUTURE_CUES.search(after))


def find_match(
    patterns: list[re.Pattern],
    texts_by_source_key: dict[str, str],
    skip_forward_looking: bool = False,
) -> tuple[str, str, int, int] | None:
    """Returns (source_key, context_quote, match_char_start, match_char_end)
    for the first non-negated match across every pattern and every source's
    text, or None. The offsets are the raw match span (not the quote's, which
    has context padding) so a caller can point back to the exact evidence
    within the source's normalized text. Scans every occurrence per pattern,
    not just the first, since an early negated hit shouldn't hide a later
    genuine one.

    skip_forward_looking: additionally ignore matches that a roadmap cue marks
    as a statement of intent (see is_forward_looking). Callers pass True for
    patterns asserting a *positive* capability only."""
    for source_key, text in texts_by_source_key.items():
        for pattern in patterns:
            for match in pattern.finditer(text):
                if is_negated(text, match.start()):
                    continue
                if skip_forward_looking and is_forward_looking(text, match.start(), match.end()):
                    continue
                start = max(0, match.start() - CONTEXT_CHARS)
                end = min(len(text), match.end() + CONTEXT_CHARS)
                quote = text[start:end].strip()
                if len(quote) > MAX_QUOTE_LENGTH:
                    quote = quote[:MAX_QUOTE_LENGTH].rstrip() + "…"
                return source_key, quote, match.start(), match.end()
    return None
