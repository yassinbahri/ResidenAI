import httpx

from app.tracker.discovery import discover_company_info_source, discover_privacy_source
from app.tracker.fetch import HttpFetcher

HOMEPAGE_HTML = """
<html><body>
  <nav>
    <a href="/product">Product</a>
    <a href="/pricing">Pricing</a>
    <a href="/privacy">Privacy Policy</a>
    <a href="/security">Security</a>
  </nav>
</body></html>
"""

HOMEPAGE_WITH_IMPRINT_HTML = """
<html><body>
  <nav>
    <a href="/product">Product</a>
    <a href="/pricing">Pricing</a>
    <a href="/imprint">Imprint</a>
    <a href="/about">About Us</a>
  </nav>
</body></html>
"""

REAL_PRIVACY_PAGE = "<main>" + ("This is a real privacy policy discussing data handling. " * 20) + "</main>"

REAL_IMPRINT_PAGE = "<main>" + ("Example GmbH, registered in Berlin, Germany. Handelsregister HRB 12345. " * 10) + "</main>"

# Real content, real static text, but no domicile-relevant marker anywhere -
# the shape of the actual Salesforce/Hugging Face/GitHub false positives
# found while backfilling the registry (2026-07-29): a genuine, substantial
# page that simply isn't a legal notice.
MARKETING_PAGE_NO_MARKER = "<main>" + ("Join our team and help us build the future of AI for everyone. " * 20) + "</main>"

JS_SHELL_SECURITY_PAGE = "<main><div id='root'></div><script>loadApp()</script></main>"


def test_finds_and_verifies_the_privacy_link_from_the_homepage() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            return httpx.Response(200, text=HOMEPAGE_HTML)
        if request.url.path == "/privacy":
            return httpx.Response(200, text=REAL_PRIVACY_PAGE)
        return httpx.Response(200, text=JS_SHELL_SECURITY_PAGE)

    fetcher = HttpFetcher(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    result = discover_privacy_source("https://example.test/", fetcher=fetcher)

    assert result == "https://example.test/privacy"


def test_falls_through_to_next_candidate_when_first_is_a_js_shell() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            return httpx.Response(200, text=HOMEPAGE_HTML)
        if request.url.path == "/privacy":
            return httpx.Response(200, text=JS_SHELL_SECURITY_PAGE)  # privacy page is a JS shell
        if request.url.path == "/security":
            return httpx.Response(200, text=REAL_PRIVACY_PAGE)  # security page has real content
        return httpx.Response(404)

    fetcher = HttpFetcher(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    result = discover_privacy_source("https://example.test/", fetcher=fetcher)

    assert result == "https://example.test/security"


def test_returns_none_when_no_candidate_works() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            return httpx.Response(200, text=HOMEPAGE_HTML)
        return httpx.Response(200, text=JS_SHELL_SECURITY_PAGE)

    fetcher = HttpFetcher(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    result = discover_privacy_source("https://example.test/", fetcher=fetcher)

    assert result is None


def test_returns_none_when_homepage_itself_is_unreachable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    fetcher = HttpFetcher(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    result = discover_privacy_source("https://example.test/", fetcher=fetcher)

    assert result is None


def test_returns_none_when_homepage_has_no_relevant_links() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html><body><a href='/pricing'>Pricing</a></body></html>")

    fetcher = HttpFetcher(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    result = discover_privacy_source("https://example.test/", fetcher=fetcher)

    assert result is None


def test_finds_and_verifies_the_imprint_link_from_the_homepage() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            return httpx.Response(200, text=HOMEPAGE_WITH_IMPRINT_HTML)
        if request.url.path == "/imprint":
            return httpx.Response(200, text=REAL_IMPRINT_PAGE)
        return httpx.Response(200, text=JS_SHELL_SECURITY_PAGE)

    fetcher = HttpFetcher(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    result = discover_company_info_source("https://example.test/", fetcher=fetcher)

    assert result is not None
    assert result.url == "https://example.test/imprint"
    assert result.confident is True


def test_company_info_discovery_falls_through_to_about_page_when_imprint_is_a_js_shell() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            return httpx.Response(200, text=HOMEPAGE_WITH_IMPRINT_HTML)
        if request.url.path == "/imprint":
            return httpx.Response(200, text=JS_SHELL_SECURITY_PAGE)
        if request.url.path == "/about":
            return httpx.Response(200, text=REAL_IMPRINT_PAGE)
        return httpx.Response(404)

    fetcher = HttpFetcher(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    result = discover_company_info_source("https://example.test/", fetcher=fetcher)

    assert result is not None
    assert result.url == "https://example.test/about"
    assert result.confident is True


def test_company_info_discovery_returns_none_when_homepage_has_no_relevant_links() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=HOMEPAGE_HTML)  # privacy/security links, no imprint/about/legal

    fetcher = HttpFetcher(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    result = discover_company_info_source("https://example.test/", fetcher=fetcher)

    assert result is None


def test_company_info_discovery_flags_a_marketing_page_as_unconfident() -> None:
    # Regression test for the real Salesforce/Hugging Face/GitHub false
    # positives found while backfilling all 41 providers: a page can have
    # plenty of real static content and still not be a legal notice. Such a
    # candidate is still returned (better than nothing), but flagged
    # unconfident so it isn't trusted as domicile evidence.
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            return httpx.Response(200, text=HOMEPAGE_WITH_IMPRINT_HTML)
        if request.url.path == "/imprint":
            return httpx.Response(200, text=MARKETING_PAGE_NO_MARKER)
        return httpx.Response(200, text=MARKETING_PAGE_NO_MARKER)

    fetcher = HttpFetcher(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    result = discover_company_info_source("https://example.test/", fetcher=fetcher)

    assert result is not None
    assert result.confident is False


def test_company_info_discovery_prefers_a_confident_candidate_over_an_earlier_weak_one() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            return httpx.Response(200, text=HOMEPAGE_WITH_IMPRINT_HTML)
        if request.url.path == "/imprint":
            return httpx.Response(200, text=MARKETING_PAGE_NO_MARKER)  # tried first, no marker
        if request.url.path == "/about":
            return httpx.Response(200, text=REAL_IMPRINT_PAGE)  # tried second, has a marker
        return httpx.Response(404)

    fetcher = HttpFetcher(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    result = discover_company_info_source("https://example.test/", fetcher=fetcher)

    assert result is not None
    assert result.url == "https://example.test/about"
    assert result.confident is True
