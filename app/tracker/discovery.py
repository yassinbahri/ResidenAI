"""Best-effort, fully automatic discovery of candidate documentation URLs
for a brand-new company, given just its homepage. No LLM, no web search - a
deterministic scan of the homepage's own links for a keyword set, with each
candidate verified by actually fetching it and checking for substantial
real static content (the same JS-shell/bot-block problem this project hit
repeatedly while seeding the first 42 providers by hand).

Two keyword sets, two purposes:
- privacy/security/trust -> data-handling facts (residency_classifier.py)
- imprint/about/company/legal notice -> company-identity facts
  (domicile_classifier.py)

Root-caused via live inspection (2026-07-28): every provider's domicile
status was stuck at "unclear" not because the classifier was imprecise,
but because privacy/security pages almost never state where a company is
legally registered - an imprint page (legally mandated for EU companies,
"Impressum") reliably does, and nothing was ever looking for one.

Second bug, found the same way while backfilling all 41 providers
(2026-07-29): "real content, >500 chars" is not enough to accept a
company-info candidate as genuine legal-entity evidence - it happily
accepted marketing pages that merely matched a keyword (Salesforce's "be a
trailblazer" page, a Hugging Face org profile, a GitHub security-features
doc). `discover_company_info_source` now requires the page to also contain
a domicile-relevant marker (a VAT/registry keyword, a registered-office/
headquarters phrase, or similar) before treating it as confident evidence;
if no candidate clears that bar, the weakest content-bearing candidate is
still returned but flagged `confident=False` so it isn't silently trusted
as if it were a real legal notice.

Honest limitation, stated plainly: this is not as good as a human (or an
LLM) doing targeted research. It will fail for a real fraction of
companies - non-standard site structure, Cloudflare/bot-management
blocking the fetcher, a JS-rendered trust-center subdomain, or a relevant
link buried somewhere this simple scan doesn't look. When it fails, it
says so (returns None) rather than guessing or silently giving up -
onboarding.py surfaces that as "needs a source added" rather than hiding
the gap.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from app.tracker.fetch import FetchRequest, HttpFetcher
from app.tracker.normalize import normalize_html

# Lower number = tried first.
_PRIVACY_KEYWORD_PRIORITY = {
    "privacy": 0,
    "data protection": 0,
    "data residency": 0,
    "gdpr": 1,
    "security": 1,
    "trust": 2,
    "legal": 3,
}

# Imprint/Impressum is the single most reliable page type for a company's
# own legal-entity/registration facts - EU law requires it on commercial
# sites, so it's tried first. "Contact" is the weakest fallback (often just
# a support form, but occasionally the only page with a registered address).
_COMPANY_INFO_KEYWORD_PRIORITY = {
    "imprint": 0,
    "impressum": 0,
    "legal notice": 1,
    "company": 2,
    "about us": 2,
    "about": 3,
    "contact": 4,
}

# Content-level gate for a company-info candidate: does the page actually
# state a legal-entity fact, not just live at a plausible-sounding URL.
# Deliberately not restricted to EU jurisdictions - a genuine US/UK/etc.
# legal notice is still real evidence, just for a different (correctly
# non_eu_domiciled) verdict downstream.
# RCS/R.C.S. are pulled out of the shared trailing \b group deliberately -
# "R.C.S." ends in a literal period (a non-word char), so a trailing \b
# right after it fails whenever followed by another non-word char (e.g. a
# closing parenthesis, as in the real Mistral page's "(R.C.S.)"). Same fix
# already applied once in domicile_classifier.py's _EU_REGISTRY_PATTERN -
# replicated here since this is a separate regex. "registered offices?" -
# plural, since real imprints commonly say "registered offices at <address>".
_DOMICILE_MARKER_PATTERN = re.compile(
    r"\b(?:registered offices?|registered address|head\s?quarter(?:ed|s)?|"
    r"principal place of business|company registration number|registered in|"
    r"VAT\s*(?:number|no|ID)|Handelsregister|HRB|HRA|"
    r"KVK|Org(?:anisasjons)?\.?\s*nr|CVR|Bolagsverket|Companies House)\b"
    r"|RCS\s+\w+"
    r"|\bR\.C\.S\.",
    re.I,
)

_MAX_CANDIDATES_TRIED = 8
_MIN_REAL_CONTENT_LENGTH = 500


def looks_like_legal_notice(text: str) -> bool:
    """Whether normalized page text contains a domicile-relevant marker.
    Exposed (not just used internally by discover_company_info_source) so
    an already-discovered source's classification can be rechecked without
    re-running full candidate discovery - see
    scripts/discover_company_info_sources.py."""
    return bool(_DOMICILE_MARKER_PATTERN.search(text))


@dataclass(frozen=True)
class CompanyInfoCandidate:
    url: str
    # True if the page itself contains a domicile-relevant marker, not just
    # enough static text to pass the generic JS-shell check - see
    # _DOMICILE_MARKER_PATTERN.
    confident: bool


def _extract_candidate_links(
    homepage_url: str, html: str, keyword_priority: dict[str, int]
) -> list[tuple[str, str]]:
    """Returns [(url, matched_link_text_or_href)], deduplicated, absolute."""
    soup = BeautifulSoup(html, "lxml")
    seen: set[str] = set()
    candidates: list[tuple[str, str]] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(strip=True).lower()
        haystack = f"{href.lower()} {text}"
        if not any(keyword in haystack for keyword in keyword_priority):
            continue
        absolute = urljoin(homepage_url, href)
        if urlparse(absolute).scheme not in ("http", "https"):
            continue
        if absolute in seen:
            continue
        seen.add(absolute)
        candidates.append((absolute, text or href))
    return candidates


def _priority(link_text: str, keyword_priority: dict[str, int]) -> int:
    matches = [score for keyword, score in keyword_priority.items() if keyword in link_text.lower()]
    return min(matches, default=len(keyword_priority))


def _fetch_candidate_text(url: str, fetcher: HttpFetcher) -> str | None:
    """Fetches a candidate URL and returns its normalized text, or None if
    the fetch failed or the page is too short to be real content (a
    JS-shell/loading placeholder rather than an actual document)."""
    try:
        result = fetcher.fetch(FetchRequest(url=url))
    except Exception:
        return None
    if not result.body:
        return None
    text = normalize_html(result.body).text
    if len(text) < _MIN_REAL_CONTENT_LENGTH:
        return None
    return text


def _homepage_candidates(
    homepage_url: str, keyword_priority: dict[str, int], fetcher: HttpFetcher
) -> list[str]:
    try:
        homepage = fetcher.fetch(FetchRequest(url=homepage_url))
    except Exception:
        return []
    if homepage.body is None:
        return []
    candidates = _extract_candidate_links(homepage_url, homepage.body, keyword_priority)
    candidates.sort(key=lambda c: _priority(c[1], keyword_priority))
    return [url for url, _link_text in candidates[:_MAX_CANDIDATES_TRIED]]


def discover_privacy_source(homepage_url: str, fetcher: HttpFetcher | None = None) -> str | None:
    """Data-handling facts: privacy policy, security page, trust center.
    Returns a verified, fetchable, content-bearing candidate URL, or None
    if nothing on the homepage panned out. Never raises - any fetch
    failure along the way is treated as "this candidate doesn't work," not
    an error."""
    owns_fetcher = fetcher is None
    fetcher = fetcher or HttpFetcher()
    try:
        for url in _homepage_candidates(homepage_url, _PRIVACY_KEYWORD_PRIORITY, fetcher):
            if _fetch_candidate_text(url, fetcher) is not None:
                return url
        return None
    finally:
        if owns_fetcher:
            fetcher.close()


def discover_company_info_source(
    homepage_url: str, fetcher: HttpFetcher | None = None
) -> CompanyInfoCandidate | None:
    """Company-identity facts: imprint/legal notice/about page - the page
    type that actually states legal domicile, which privacy/security pages
    almost never do. Prefers a candidate that contains an actual
    domicile-relevant marker (`confident=True`); if none do, still returns
    the first content-bearing candidate but flagged `confident=False` so a
    caller can treat it as "found something, but verify by hand" rather
    than silently trusting it as a real legal notice."""
    owns_fetcher = fetcher is None
    fetcher = fetcher or HttpFetcher()
    try:
        weak_fallback: CompanyInfoCandidate | None = None
        for url in _homepage_candidates(homepage_url, _COMPANY_INFO_KEYWORD_PRIORITY, fetcher):
            text = _fetch_candidate_text(url, fetcher)
            if text is None:
                continue
            if looks_like_legal_notice(text):
                return CompanyInfoCandidate(url=url, confident=True)
            if weak_fallback is None:
                weak_fallback = CompanyInfoCandidate(url=url, confident=False)
        return weak_fallback
    finally:
        if owns_fetcher:
            fetcher.close()
