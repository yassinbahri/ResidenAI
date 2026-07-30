from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256

from bs4 import BeautifulSoup

# Tags that are never part of the substantive policy text on a vendor docs
# page - stripped before diffing so ad/analytics/nav churn doesn't register
# as a content change.
NOISE_TAGS = ["script", "style", "nav", "footer", "header", "aside", "noscript", "svg", "form"]

# Prefer a real content container when the page has one; fall back to the
# whole body for pages that don't mark one up explicitly.
CONTENT_SELECTORS = ["main", "article", "[role=main]"]

_WHITESPACE_RE = re.compile(r"[ \t]+")


@dataclass(frozen=True)
class NormalizedDocument:
    title: str | None
    text: str
    text_sha256: str


def normalize_html(raw_html: str) -> NormalizedDocument:
    soup = BeautifulSoup(raw_html, "lxml")

    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else None

    for tag in soup.find_all(NOISE_TAGS):
        tag.decompose()

    content = None
    for selector in CONTENT_SELECTORS:
        content = soup.select_one(selector)
        if content is not None:
            break
    if content is None:
        content = soup.body or soup

    text = content.get_text(separator="\n")
    text = _WHITESPACE_RE.sub(" ", text)
    lines = [line.strip() for line in text.split("\n")]
    text = "\n".join(line for line in lines if line)

    return NormalizedDocument(
        title=title,
        text=text,
        text_sha256=sha256(text.encode("utf-8")).hexdigest(),
    )
