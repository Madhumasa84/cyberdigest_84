import pytest

from cyberdigest.feeds import _download_feed, _parse_feed_list, _parse_rss_fallback


def test_rss_fallback_regex_path():
    # Malformed XML that still has item blocks
    raw = b"""
    <rss><channel>
    <item><title>Broken Feed Title</title><link>https://ex.com/1</link>
    <description>Hello</description><pubDate>Mon</pubDate></item>
    not valid xml overall <
    """
    # This may parse via ET or regex depending on content
    parsed = _parse_rss_fallback(raw)
    # Even if empty, function should not raise
    assert hasattr(parsed, "entries")


def test_rss_fallback_valid_xml():
    raw = b"""<?xml version="1.0"?>
    <rss><channel>
      <item>
        <title>T1</title>
        <link>https://ex.com/a</link>
        <description>Sum</description>
        <pubDate>Mon, 1 Jan 2024</pubDate>
      </item>
    </channel></rss>"""
    parsed = _parse_rss_fallback(raw)
    assert len(parsed.entries) == 1
    assert parsed.entries[0]["title"] == "T1"


def test_parse_feed_list_empty_means_empty():
    assert _parse_feed_list([], [("X", "http://x", "#000")]) == []
    assert _parse_feed_list(None, [("X", "http://x", "#000")])[0][0] == "X"


def test_parse_feed_list_dict_items():
    raw = [{"name": "A", "url": "https://a.test/feed", "color": "#fff"}]
    out = _parse_feed_list(raw, [])
    assert out == [("A", "https://a.test/feed", "#fff")]


def test_parse_feed_list_rejects_non_http_urls():
    raw = [{"name": "Local file", "url": "file:///etc/passwd"}]
    assert _parse_feed_list(raw, []) == []


def test_download_feed_rejects_non_http_url():
    with pytest.raises(ValueError, match="http or https"):
        _download_feed("file:///etc/passwd")
