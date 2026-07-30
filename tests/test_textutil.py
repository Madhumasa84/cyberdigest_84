from cyberdigest.textutil import extract_cve_ids, h, safe_http_url, strip_html, truncate


def test_strip_html():
    assert strip_html("<b>Hello</b> world") == "Hello world"
    assert strip_html(None) == ""


def test_escape_html():
    assert "&lt;script&gt;" in h("<script>")
    assert "&quot;" in h('say "hi"')


def test_safe_http_url_blocks_javascript():
    assert safe_http_url("javascript:alert(1)") == "#"
    assert safe_http_url("data:text/html,hi") == "#"
    assert safe_http_url("https://example.com/a") == "https://example.com/a"
    assert safe_http_url("http://x.test") == "http://x.test"
    assert safe_http_url("") == "#"
    assert safe_http_url(None) == "#"

    class BadURL:
        def strip(self):
            raise Exception("bad")

    assert safe_http_url(BadURL()) == "#"


def test_extract_cve_ids():
    ids = extract_cve_ids("See CVE-2024-1234 and cve-2023-99999 together")
    assert ids == ["CVE-2024-1234", "CVE-2023-99999"]
    assert extract_cve_ids(None) == []
    assert extract_cve_ids("") == []


def test_reading_time():
    from cyberdigest.textutil import reading_time

    assert reading_time("word") == "1 min read"
    assert reading_time("word " * 200) == "1 min read"
    assert reading_time("word " * 300) == "2 min read"


def test_truncate():
    assert truncate("short") == "short"
    long = "word " * 100
    assert len(truncate(long, 20)) <= 22
