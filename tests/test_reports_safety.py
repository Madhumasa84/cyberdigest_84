from cyberdigest.config import reload_config
from cyberdigest.reports import generate_html, re_safe_color


def test_safe_color():
    assert re_safe_color("#abc") == "#abc"
    assert re_safe_color("#aabbcc") == "#aabbcc"
    assert re_safe_color("red;background:url(x)") == "#3b82f6"
    assert re_safe_color("javascript:x") == "#3b82f6"


def test_generate_html_escapes_and_blocks_js_links():
    reload_config()
    arts = [
        {
            "title": "<script>alert(1)</script> CVE-2024-1234",
            "summary": "Bad & worse",
            "link": "javascript:alert(1)",
            "published": "today",
            "timestamp": 1.0,
            "color": "#e74c3c",
            "source": "Test<script>",
            "severity": "High",
            "other_sources": set(),
            "cve_scores": {},
        }
    ]
    html = generate_html(
        arts,
        "20260101_1200",
        {},
        "Schedule <b>warn</b>",
        [("Test", "https://example.com", "#e74c3c")],
        "cyber",
        {},
    )
    assert "<script>alert(1)</script>" not in html
    assert "javascript:alert" not in html
    assert "Schedule &lt;b&gt;warn&lt;/b&gt;" in html or "Schedule &lt;b&gt;warn" in html
