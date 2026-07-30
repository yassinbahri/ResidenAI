import httpx
import pytest

from app.tracker.fetch import FetchRequest, HttpFetcher


def _fetcher_with_transport(handler) -> HttpFetcher:
    return HttpFetcher(http_client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_fetch_returns_body_and_hash_on_200() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>hello</html>", headers={"etag": '"abc"'})

    fetcher = _fetcher_with_transport(handler)
    result = fetcher.fetch(FetchRequest(url="https://example.com/docs"))

    assert result.status_code == 200
    assert result.not_modified is False
    assert result.body == "<html>hello</html>"
    assert result.body_sha256 is not None
    assert result.etag == '"abc"'


def test_conditional_get_sends_etag_and_handles_304() -> None:
    seen_headers = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_headers.update(request.headers)
        return httpx.Response(304)

    fetcher = _fetcher_with_transport(handler)
    result = fetcher.fetch(
        FetchRequest(url="https://example.com/docs", etag='"abc"', last_modified="Mon, 01 Jan 2026 00:00:00 GMT")
    )

    assert result.not_modified is True
    assert result.body is None
    assert result.body_sha256 is None
    assert seen_headers.get("if-none-match") == '"abc"'
    assert seen_headers.get("if-modified-since") == "Mon, 01 Jan 2026 00:00:00 GMT"


def test_fetch_raises_on_http_error_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="server error")

    fetcher = _fetcher_with_transport(handler)
    with pytest.raises(httpx.HTTPStatusError):
        fetcher.fetch(FetchRequest(url="https://example.com/docs"))
