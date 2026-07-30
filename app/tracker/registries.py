"""Best-effort corroboration of a provider's page-scraped domicile claim
against an authoritative company registry - GLEIF (global LEI database,
covers every EU/EEA member) and Brønnøysundregistrene (Norway specifically -
a natural fit given ShadowAI's own Norway focus). Deliberately not BRIS
(not very API-friendly in practice) or VIES (validates VAT format/
association against a name, not domicile itself - marginal value here).

This is corroboration, not a replacement authority: it never overrides the
page-scraped eu_domicile_status computed by domicile_classifier.py, only
supplements it - see scripts/verify_domicile_registries.py, which surfaces
a disagreement between "what the page says" and "what an official registry
says" rather than auto-resolving it either way.

Matching a free-text display name against a registry is itself an
approximate operation, and a live run against all 41 providers (2026-07-29)
showed exactly how badly that can go wrong on short/generic names: "Runway"
matched an unrelated Indian car dealer ("Runway Motors"), "Canva" matched
"Canva Bioorganics LLP", "Zoom" matched "Zoom Electricals & Zoom Lites",
"Grain" matched "Grain Fundacion" - all real registry hits, all completely
unrelated companies. A substring check doesn't catch these (the query
genuinely is a substring of the wrong match); only requiring the matched
name to be *exactly* the query once common legal-form suffixes are
stripped from both sides is strict enough to reject them - see
_names_match. That means many genuine matches get rejected too whenever
the official legal name isn't a simple "query + suffix" (e.g. "Writer
Ventures GmbH" for a query of "Writer") - an intentional, conservative
trade-off: a missed corroboration is much cheaper than a confidently wrong
one used the same discipline everywhere else in this project (evidence
before assertion).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import httpx

_GLEIF_BASE_URL = "https://api.gleif.org/api/v1/lei-records"
_BRREG_BASE_URL = "https://data.brreg.no/enhetsregisteret/api/enheter"
_TIMEOUT_SECONDS = 10.0

_LEGAL_SUFFIXES = re.compile(
    r"[,]?\s*\b(?:Inc|LLC|Ltd|Limited|LLP|GmbH|SE|SA|AS|ASA|AB|OY|OU|PBC|Corp|Corporation|Co|"
    r"Holding|Group|PLC|BV|NV|SAS|SARL)\.?\s*$",
    re.I,
)


def _normalize_company_name(name: str) -> str:
    """Strips trailing legal-form suffixes (repeatedly, for chains like
    "X Holding GmbH") and reduces to bare alphanumerics for a strict
    equality check - see module docstring for why this needs to be exact,
    not a substring/fuzzy match."""
    name = name.strip()
    for _ in range(3):
        stripped = _LEGAL_SUFFIXES.sub("", name).strip().rstrip(",.")
        if stripped == name:
            break
        name = stripped
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _names_match(query: str, candidate: str) -> bool:
    return _normalize_company_name(query) == _normalize_company_name(candidate)


@dataclass(frozen=True)
class RegistryMatch:
    country_code: str  # ISO 3166-1 alpha-2
    matched_name: str
    source: str  # "gleif" | "brreg"


def lookup_gleif(legal_name: str) -> RegistryMatch | None:
    """Looks up a legal entity by name in GLEIF's public LEI database
    (free, keyless, no rate-limit key required). Returns the first ACTIVE
    record whose name is an exact match (after suffix-stripping) for
    legal_name, or None on no match/network failure."""
    try:
        response = httpx.get(
            _GLEIF_BASE_URL,
            params={"filter[entity.legalName]": legal_name, "page[size]": 5},
            timeout=_TIMEOUT_SECONDS,
            headers={"Accept": "application/vnd.api+json"},
        )
        response.raise_for_status()
        records = response.json().get("data", [])
    except Exception:
        return None

    for record in records:
        entity = record.get("attributes", {}).get("entity", {})
        if entity.get("status") != "ACTIVE":
            continue
        country = entity.get("legalAddress", {}).get("country")
        if not country:
            continue
        legal_name_matched = entity.get("legalName", {}).get("name")
        if not legal_name_matched or not _names_match(legal_name, legal_name_matched):
            continue
        return RegistryMatch(country_code=country, matched_name=legal_name_matched, source="gleif")
    return None


def lookup_brreg(name_or_org_number: str) -> RegistryMatch | None:
    """Looks up a Norwegian legal entity by name (or organisasjonsnummer)
    in Brønnøysundregistrene's open Enhetsregisteret API (free, keyless).
    Always country_code="NO" since this registry only covers Norwegian
    entities. Returns the first entry whose name is an exact match (after
    suffix-stripping); None on no match/network failure."""
    try:
        response = httpx.get(
            _BRREG_BASE_URL,
            params={"navn": name_or_org_number, "size": 5},
            timeout=_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        entries = response.json().get("_embedded", {}).get("enheter", [])
    except Exception:
        return None

    for entry in entries:
        matched_name = entry.get("navn")
        if not matched_name or not _names_match(name_or_org_number, matched_name):
            continue
        return RegistryMatch(country_code="NO", matched_name=matched_name, source="brreg")
    return None
