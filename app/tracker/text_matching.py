"""Shared deterministic text-matching helpers used by both
residency_classifier.py and domicile_classifier.py - regex over fetched
page text, negation-aware, always returns the matched quote with context so
a human can spot-check rather than trust a verdict blindly."""

from __future__ import annotations

import re

CONTEXT_CHARS = 60
MAX_QUOTE_LENGTH = 400
NEGATION_LOOKBACK_CHARS = 40

# Catches cases like "...is not currently EU data residency compliant" -
# without this, a plain positive-phrase pattern would misread an explicit
# denial as a positive claim.
NEGATION_CUES = re.compile(r"\b(not|isn't|doesn't|does not|cannot|can't|no longer)\b", re.I)


def is_negated(text: str, match_start: int) -> bool:
    window_start = max(0, match_start - NEGATION_LOOKBACK_CHARS)
    return bool(NEGATION_CUES.search(text[window_start:match_start]))


def find_match(
    patterns: list[re.Pattern], texts_by_source_key: dict[str, str]
) -> tuple[str, str, int, int] | None:
    """Returns (source_key, context_quote, match_char_start, match_char_end)
    for the first non-negated match across every pattern and every source's
    text, or None. The offsets are the raw match span (not the quote's, which
    has context padding) so a caller can point back to the exact evidence
    within the source's normalized text. Scans every occurrence per pattern,
    not just the first, since an early negated hit shouldn't hide a later
    genuine one."""
    for source_key, text in texts_by_source_key.items():
        for pattern in patterns:
            for match in pattern.finditer(text):
                if is_negated(text, match.start()):
                    continue
                start = max(0, match.start() - CONTEXT_CHARS)
                end = min(len(text), match.end() + CONTEXT_CHARS)
                quote = text[start:end].strip()
                if len(quote) > MAX_QUOTE_LENGTH:
                    quote = quote[:MAX_QUOTE_LENGTH].rstrip() + "…"
                return source_key, quote, match.start(), match.end()
    return None
