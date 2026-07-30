"""Deterministic classifier for a second, independent signal: is the
*company itself* legally domiciled in the EU/EEA/Norway - not where they let
you host data, but where the legal entity actually is. This matters because
a US company offering an "EU region" is still a US legal entity subject to
US jurisdiction (Schrems II/CLOUD Act concerns); an EU-domiciled company
processing in the EU is a materially different, stronger position. See
app/tracker/scoring.py for how this combines with residency_classifier.py's
processing-location signal into one score.

Same discipline as residency_classifier.py: regex over fetched text, no
LLM, evidence-quoted, wrong sometimes - that's why the quote is always
shown. Deliberately conservative: ambiguous legal suffixes used both inside
and outside the EU (e.g. plain "Ltd" - Ireland and the UK both use it,
post-Brexit the UK is not EEA) are excluded to avoid false positives that
would wrongly inflate a vendor's score.

Requires a *self-referential* subject close to the match, not just any
location statement nearby - found via live testing that a plain "based in
X" scan readily matches sentences about a mentioned *third party* (a
subprocessor, a dispute-resolution provider), not the vendor itself, e.g.
DeepL's own privacy policy mentioning "Zoom is based in the USA" as a
subprocessor disclosure was misread as DeepL's own domicile. A self
-reference is either a first-person pronoun ("we", "our") *or* the
provider's own name appearing right at the match (legal imprints commonly
state facts in third person using the company's own name, e.g. "DeepL SE,
registered in Cologne, is the data controller" - there's no "we" to find).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.tracker.text_matching import CONTEXT_CHARS, MAX_QUOTE_LENGTH, is_negated

_SELF_REFERENCE_LOOKBACK_CHARS = 80

# VAT numbers and national company-registry references get a much wider
# lookback than location statements. Found via live testing against
# Mistral's actual legal notice: "Mistral, a simplified joint stock company
# with capital of EUR 15,000, listed on the Paris Trade and Companies
# Register (R.C.S.) under number 952 418 325..." puts the company name ~120
# chars before the registry mention - one long legal sentence, not the
# short "X is based in Y" shape the 80-char default was tuned against. This
# is safe to widen only for these patterns: the DeepL/Zoom and Fathom/JAMS
# false positives this project already hit were about a third party's
# *location*, never its VAT/registry number - subprocessor disclosures
# don't quote a subprocessor's own registration number.
_STRUCTURAL_ID_LOOKBACK_CHARS = 220

_PRONOUN_CUES = re.compile(r"\b(we|us|our|this company|the company)\b", re.I)

_EU_EEA_COUNTRIES = (
    r"Norway|Sweden|Denmark|Finland|Iceland|Germany|France|the Netherlands|Netherlands|"
    r"Belgium|Luxembourg|Ireland|Spain|Portugal|Italy|Austria|Poland|Czech Republic|"
    r"Slovakia|Hungary|Romania|Bulgaria|Greece|Croatia|Slovenia|Estonia|Latvia|Lithuania|"
    r"Malta|Cyprus"
)

# ISO VAT-prefix country codes for EU/EEA members (Greece uses "EL" on VAT
# numbers, not its ISO code "GR" - both accepted since real pages vary).
_EU_VAT_COUNTRY_CODES = (
    r"AT|BE|BG|HR|CY|CZ|DE|DK|EE|ES|FI|FR|EL|GR|HU|IE|IT|LT|LU|LV|MT|NL|PL|PT|RO|SE|SI|SK"
)

# National company-registry references. Each is jurisdiction-specific
# enough on its own to be treated as a domicile signal without needing a
# nearby country name: RCS (France, both "RCS Paris"-style and the spelled-
# out "Trade and Companies Register (R.C.S.)" real companies actually use),
# Handelsregister/HRB/HRA (Germany/Austria), KVK (Netherlands), Org.nr
# (Norway), CVR (Denmark), Bolagsverket (Sweden).
_EU_REGISTRY_PATTERN = re.compile(
    r"\b(?:Handelsregister|HRB|HRA|KVK|Org(?:anisasjons)?\.?\s*nr|CVR|Bolagsverket)\b"
    r"|RCS\s+\w+"
    r"|\bR\.C\.S\.",
    re.I,
)

# Allows one or more capitalized words before the country (e.g. "San
# Francisco, California" or "Cologne, Germany"), not just a single word.
_OPTIONAL_CITY = r"(?:[A-Z][a-zA-Z.]+(?:\s+[A-Z][a-zA-Z.]+)*,\s+)?"

_EU_DOMICILE_PATTERNS = [
    re.compile(
        rf"(?:headquartered|based|incorporated|registered)\s+in\s+{_OPTIONAL_CITY}(?:{_EU_EEA_COUNTRIES})\b",
        re.I,
    ),
    re.compile(
        rf"registered office\s+(?:is\s+)?(?:located\s+)?in\s+{_OPTIONAL_CITY}(?:{_EU_EEA_COUNTRIES})\b", re.I
    ),
    re.compile(rf"is\s+an?\s+\w*\s*(?:{_EU_EEA_COUNTRIES})\s+(?:company|corporation|entity)\b", re.I),
    # Societas Europaea - an EU-only legal form, unambiguous on its own.
    #
    # Requires a capitalized preceding word and rejects a preceding street-type
    # word: "SE" is also the standard US quadrant abbreviation, so the bare
    # `\w+\s+SE` shape matched "1201 Broad Street SE, Atlanta, Georgia" and
    # classified US vendors as eu_domiciled off their own postal address - the
    # exact overstatement-of-compliance failure this module is built to avoid.
    # The negative lookahead keeps genuine names ("DeepL SE,") matching while
    # dropping the address shape ("Street SE,", "St SE,", "Ave SE.").
    re.compile(
        r"\b(?!(?:Street|St|Avenue|Ave|Boulevard|Blvd|Road|Rd|Drive|Dr|Lane|Ln|"
        r"Court|Ct|Place|Pl|Terrace|Ter|Way|Highway|Hwy|Parkway|Pkwy|Suite|Ste)\b)"
        r"[A-Z][\w.&-]*\s+SE\b(?:,|\.|\s+is\b)",
        re.U,
    ),
]

# A company's own VAT number or national registry reference on its own page
# is essentially always self-referential (checked with a wider lookback -
# see _STRUCTURAL_ID_LOOKBACK_CHARS - since imprint sentences put the
# company's name well before these facts); still passes negation +
# self-reference checks as a guard against a subprocessor's VAT/registry
# number appearing in a DPA table.
_EU_DOMICILE_STRUCTURAL_PATTERNS = [
    re.compile(rf"VAT\s*(?:number|no\.?|ID)\s*[:\-]?\s*(?:{_EU_VAT_COUNTRY_CODES})\s?\d{{6,12}}\b", re.I),
    _EU_REGISTRY_PATTERN,
]

_NON_EU_DOMICILE_PATTERNS = [
    re.compile(
        rf"(?:headquartered|based|incorporated|registered)\s+in\s+{_OPTIONAL_CITY}"
        r"(?:the\s+)?(?:United States|U\.S\.|USA|California|Delaware|New York)\b",
        re.I,
    ),
    re.compile(
        rf"(?:headquartered|based|incorporated|registered)\s+in\s+{_OPTIONAL_CITY}(?:the\s+)?United Kingdom\b",
        re.I,
    ),
    re.compile(r"a\s+Delaware\s+corporation\b", re.I),
]


@dataclass(frozen=True)
class DomicileAssessment:
    status: str  # "eu_domiciled" | "non_eu_domiciled" | "unclear" | "conflicting"
    evidence_quote: str | None
    evidence_source_key: str | None
    evidence_char_start: int | None = None
    evidence_char_end: int | None = None
    # Populated only when status == "conflicting": a second, contradictory
    # self-referential match (a non-EU claim, when evidence_* above is the
    # EU claim). See classify_eu_domicile.
    conflicting_quote: str | None = None
    conflicting_source_key: str | None = None
    conflicting_char_start: int | None = None
    conflicting_char_end: int | None = None


@dataclass(frozen=True)
class _Match:
    source_key: str
    quote: str
    char_start: int
    char_end: int


def _has_self_reference(
    text: str, match_start: int, match_end: int, provider_name: str | None, lookback_chars: int
) -> bool:
    window_start = max(0, match_start - lookback_chars)
    window = text[window_start:match_end]
    if _PRONOUN_CUES.search(text[window_start:match_start]):
        return True
    if provider_name:
        first_word = provider_name.split()[0] if provider_name.split() else provider_name
        if len(first_word) >= 3 and re.search(re.escape(first_word), window, re.I):
            return True
    return False


def _find_self_referential_match(
    patterns: list[re.Pattern],
    texts_by_source_key: dict[str, str],
    provider_name: str | None,
    lookback_chars: int = _SELF_REFERENCE_LOOKBACK_CHARS,
) -> _Match | None:
    for source_key, text in texts_by_source_key.items():
        for pattern in patterns:
            for match in pattern.finditer(text):
                if is_negated(text, match.start()):
                    continue
                if not _has_self_reference(text, match.start(), match.end(), provider_name, lookback_chars):
                    continue
                start = max(0, match.start() - CONTEXT_CHARS)
                end = min(len(text), match.end() + CONTEXT_CHARS)
                quote = text[start:end].strip()
                if len(quote) > MAX_QUOTE_LENGTH:
                    quote = quote[:MAX_QUOTE_LENGTH].rstrip() + "…"
                return _Match(source_key, quote, match.start(), match.end())
    return None


def _find_eu_domiciled_match(texts_by_source_key: dict[str, str], provider_name: str | None) -> _Match | None:
    found = _find_self_referential_match(_EU_DOMICILE_PATTERNS, texts_by_source_key, provider_name)
    if found:
        return found
    return _find_self_referential_match(
        _EU_DOMICILE_STRUCTURAL_PATTERNS,
        texts_by_source_key,
        provider_name,
        lookback_chars=_STRUCTURAL_ID_LOOKBACK_CHARS,
    )


def classify_eu_domicile(
    texts_by_source_key: dict[str, str], provider_name: str | None = None
) -> DomicileAssessment:
    """provider_name (optional): the provider's own display name, used as a
    self-reference anchor for third-person legal-imprint phrasing ("DeepL
    SE, registered in Cologne, is..."). Without it, only first-person
    pronoun phrasing ("we are headquartered in...") is recognized.

    Checks for *both* an EU-domiciled and a non-EU-domiciled self-referential
    match before deciding - if a provider's enabled sources contradict each
    other (e.g. an outdated imprint still naming a since-relocated entity),
    that's reported as "conflicting" rather than silently picking whichever
    pattern list happened to be checked first."""
    eu_match = _find_eu_domiciled_match(texts_by_source_key, provider_name)
    non_eu_match = _find_self_referential_match(_NON_EU_DOMICILE_PATTERNS, texts_by_source_key, provider_name)

    if eu_match and non_eu_match:
        return DomicileAssessment(
            "conflicting",
            eu_match.quote,
            eu_match.source_key,
            eu_match.char_start,
            eu_match.char_end,
            non_eu_match.quote,
            non_eu_match.source_key,
            non_eu_match.char_start,
            non_eu_match.char_end,
        )
    if eu_match:
        return DomicileAssessment(
            "eu_domiciled", eu_match.quote, eu_match.source_key, eu_match.char_start, eu_match.char_end
        )
    if non_eu_match:
        return DomicileAssessment(
            "non_eu_domiciled",
            non_eu_match.quote,
            non_eu_match.source_key,
            non_eu_match.char_start,
            non_eu_match.char_end,
        )
    return DomicileAssessment("unclear", None, None)
