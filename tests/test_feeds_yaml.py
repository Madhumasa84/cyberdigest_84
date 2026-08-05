from cyberdigest.feeds import _parse_simple_feeds_yaml, load_feeds


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


def test_load_feeds_read_error(monkeypatch):
    from unittest.mock import MagicMock

    import cyberdigest.feeds as feeds_module

    mock_file = MagicMock()
    mock_file.exists.return_value = True
    mock_file.read_text.side_effect = PermissionError("Permission denied")

    monkeypatch.setattr("cyberdigest.feeds.FEEDS_FILE", mock_file)
    warning = MagicMock()
    monkeypatch.setattr(feeds_module.log, "warning", warning)

    feeds = load_feeds()

    warning.assert_called_once()
    assert "Could not load feeds.yaml" in warning.call_args.args[0]
    assert len(feeds["cyber"]) >= 5
    assert len(feeds["network"]) >= 1
    assert all(len(t) == 3 for t in feeds["cyber"])


def test_explicit_empty_categories_stay_empty(monkeypatch):
    from unittest.mock import MagicMock

    mock_file = MagicMock()
    mock_file.exists.return_value = True
    mock_file.read_text.return_value = "cyber: []\nnetwork: []\ncisco: []\nfortinet: []\n"
    monkeypatch.setattr("cyberdigest.feeds.FEEDS_FILE", mock_file)

    assert load_feeds() == {"cyber": [], "network": [], "cisco": [], "fortinet": []}
