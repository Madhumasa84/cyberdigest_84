from cyberdigest.feeds import _load_feeds_document, _parse_simple_feeds_yaml, load_feeds


def test_simple_yaml_parser():
    text = """
# comment must not break hex colors
cyber:
  - name: Example
    url: https://example.com/feed
    color: "#ff0000"
network:
  - name: Net
    url: https://net.example/rss
    color: "#00ff00"
"""
    data = _parse_simple_feeds_yaml(text)
    assert data["cyber"][0]["name"] == "Example"
    assert data["cyber"][0]["color"] == "#ff0000"
    assert data["network"][0]["url"] == "https://net.example/rss"
    assert data["network"][0]["color"] == "#00ff00"


def test_load_default_or_project_feeds():
    feeds = load_feeds()
    assert len(feeds["cyber"]) >= 5
    assert len(feeds["network"]) >= 1
    assert all(len(t) == 3 for t in feeds["cyber"])


def test_load_feeds_document_yaml_error_fallback():
    # Provide YAML that causes PyYAML to raise an exception (ScannerError)
    # but that _parse_simple_feeds_yaml can still parse successfully.
    # Unclosed bracket is invalid in standard YAML but fine for our simple parser regex.
    text = """
cyber:
  - name: [broken
    url: https://example.com
    color: "#ff0000"
"""
    data = _load_feeds_document(text)
    assert "cyber" in data
    assert data["cyber"][0]["name"] == "[broken"
    assert data["cyber"][0]["url"] == "https://example.com"
    assert data["cyber"][0]["color"] == "#ff0000"
