from app.tracker.normalize import normalize_html

SAMPLE_HTML = """
<html>
<head><title>Data controls in the OpenAI platform</title></head>
<body>
  <nav>Home | Docs | Pricing</nav>
  <header>Site header banner</header>
  <main>
    <h1>Data residency</h1>
    <p>Requests are processed in the European Union.</p>
    <script>trackPageView();</script>
  </main>
  <footer>Copyright 2026</footer>
</body>
</html>
"""


def test_normalize_strips_boilerplate_and_scripts() -> None:
    doc = normalize_html(SAMPLE_HTML)

    assert doc.title == "Data controls in the OpenAI platform"
    assert "Requests are processed in the European Union." in doc.text
    assert "Home | Docs | Pricing" not in doc.text
    assert "Site header banner" not in doc.text
    assert "Copyright 2026" not in doc.text
    assert "trackPageView" not in doc.text


def test_normalize_is_deterministic_for_identical_content() -> None:
    first = normalize_html(SAMPLE_HTML)
    second = normalize_html(SAMPLE_HTML)
    assert first.text_sha256 == second.text_sha256


def test_normalize_hash_changes_when_main_content_changes() -> None:
    changed = SAMPLE_HTML.replace("European Union", "United States")
    original = normalize_html(SAMPLE_HTML)
    modified = normalize_html(changed)
    assert original.text_sha256 != modified.text_sha256


def test_normalize_hash_unaffected_by_nav_or_script_changes() -> None:
    changed = SAMPLE_HTML.replace("Home | Docs | Pricing", "Home | Docs | Pricing | New Tab").replace(
        "trackPageView();", "trackPageView(); trackOther();"
    )
    original = normalize_html(SAMPLE_HTML)
    modified = normalize_html(changed)
    assert original.text_sha256 == modified.text_sha256


def test_normalize_falls_back_to_body_without_main_tag() -> None:
    html = "<html><head><title>T</title></head><body><p>Plain content</p></body></html>"
    doc = normalize_html(html)
    assert "Plain content" in doc.text
