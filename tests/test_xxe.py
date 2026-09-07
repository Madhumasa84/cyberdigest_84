import pytest

from cyberdigest.feeds import _parse_rss_fallback


def test_xxe_vulnerability_is_prevented():
    # Malicious XML payload containing an external entity
    malicious_xml = b"""<?xml version="1.0" encoding="utf-8"?>
    <!DOCTYPE test [
      <!ENTITY xxe SYSTEM "file:///etc/passwd">
    ]>
    <rss version="2.0">
      <channel>
        <item>
          <title>Test Title &xxe;</title>
          <link>https://example.com</link>
          <description>Test Description</description>
        </item>
      </channel>
    </rss>
    """

    with pytest.raises(Exception):
        _parse_rss_fallback(malicious_xml)
