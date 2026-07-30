from cyberdigest.feeds import _parse_feed_list, _parse_rss_fallback


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

def test_rss_fallback_et_parse_error():
    # Force ET.ParseError by having invalid xml tag matching but keep <item> intact
    raw = b"""<rss><channel>
    <item><title>Valid Title</title><link>https://ex.com/valid</link>
    <description>Valid Summary</description><pubDate>Valid PubDate</pubDate></item>
    <item><description>No Title Or Link Here</description></item>
    </invalid_unclosed_tag>
    """

    parsed = _parse_rss_fallback(raw)

    assert len(parsed.entries) == 1
    assert parsed.entries[0]["title"] == "Valid Title"
    assert parsed.entries[0]["link"] == "https://ex.com/valid"
    assert parsed.entries[0]["summary"] == "Valid Summary"
    assert parsed.entries[0]["published"] == "Valid PubDate"
