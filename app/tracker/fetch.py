from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256

import httpx


@dataclass(frozen=True)
class FetchRequest:
    url: str
    etag: str | None = None
    last_modified: str | None = None


@dataclass(frozen=True)
class FetchResult:
    url: str
    status_code: int
    fetched_at: datetime
    body: str | None
    body_sha256: str | None
    etag: str | None
    last_modified: str | None
    not_modified: bool


class HttpFetcher:
    """Conditional-GET fetcher for public vendor documentation pages. Sync
    (httpx.Client) - this is a low-volume batch job (dozens of sources,
    checked at most daily), not a high-concurrency crawler, so there is no
    need for async pooling.

    Note: some providers' Cloudflare-fronted domains (openai.com,
    help.openai.com) return 403 specifically to httpx's TLS/HTTP2
    fingerprint even with an honest, descriptive User-Agent - confirmed via
    curl succeeding on the identical URL where httpx failed. Do not "fix"
    this with a TLS-impersonation library (e.g. curl_cffi) - that crosses
    into bypassing bot protection, which this tracker must not do. Prefer
    an unaffected official source for the same fact instead."""

    def __init__(self, timeout_seconds: float = 30.0, http_client: httpx.Client | None = None) -> None:
        self._client = http_client or httpx.Client(
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "ShadowAI-ResidencyTracker/1.0 "
                    "(internal compliance documentation monitor)"
                )
            },
        )

    def fetch(self, request: FetchRequest) -> FetchResult:
        headers: dict[str, str] = {}
        if request.etag:
            headers["If-None-Match"] = request.etag
        if request.last_modified:
            headers["If-Modified-Since"] = request.last_modified

        response = self._client.get(request.url, headers=headers)

        if response.status_code == 304:
            return FetchResult(
                url=str(response.url),
                status_code=304,
                fetched_at=datetime.now(timezone.utc),
                body=None,
                body_sha256=None,
                etag=response.headers.get("etag", request.etag),
                last_modified=response.headers.get("last-modified", request.last_modified),
                not_modified=True,
            )

        response.raise_for_status()
        body = response.text

        return FetchResult(
            url=str(response.url),
            status_code=response.status_code,
            fetched_at=datetime.now(timezone.utc),
            body=body,
            body_sha256=sha256(body.encode("utf-8")).hexdigest(),
            etag=response.headers.get("etag"),
            last_modified=response.headers.get("last-modified"),
            not_modified=False,
        )

    def close(self) -> None:
        self._client.close()
