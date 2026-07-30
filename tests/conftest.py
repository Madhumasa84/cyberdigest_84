"""Shared fixtures — isolate config/DB/reports under tmp paths."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Sample Feed</title>
    <item>
      <title>Critical zero-day CVE-2024-99999 in ExampleWare</title>
      <link>https://example.com/article/cve-2024-99999</link>
      <description>Actively exploited remote code execution flaw. Vendors rush patch.</description>
      <pubDate>Mon, 01 Jan 2024 12:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Company opens new office in Austin</title>
      <link>https://example.com/article/office</link>
      <description>Business expansion news with no security impact.</description>
      <pubDate>Tue, 02 Jan 2024 12:00:00 GMT</pubDate>
    </item>
    <item>
      <title>javascript:alert(1)</title>
      <link>javascript:alert(1)</link>
      <description>Malicious feed item that must be blocked</description>
      <pubDate>Wed, 03 Jan 2024 12:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""

SAMPLE_NETWORK_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Net Feed</title>
    <item>
      <title>SD-WAN firmware update improves resilience</title>
      <link>https://net.example.com/sdwan</link>
      <description>Networking vendors ship firmware update for branch routers.</description>
      <pubDate>Mon, 01 Jan 2024 10:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""


@pytest.fixture
def isolated_app(tmp_path, monkeypatch):
    """Redirect all runtime state into tmp_path and load a clean config."""
    data = tmp_path / "data"
    data.mkdir()
    reports = data / "reports"
    reports.mkdir()
    cfg_path = tmp_path / "config.json"
    cfg_local = tmp_path / "config.local.json"
    cfg_example = tmp_path / "config.example.json"
    feeds_path = tmp_path / "feeds.yaml"

    cfg = {
        "interval_days": 3,
        "max_archived_reports": 5,
        "archive_global": True,
        "max_articles_per_feed": 10,
        "max_articles_per_network_feed": 5,
        "log_level": "WARNING",
        "critical_keywords": [
            "cve-",
            "zero-day",
            "actively exploited",
            "rce",
            "ransomware",
            "breach",
        ],
        "high_keywords": ["vulnerability", "flaw", "patch", "firmware update", "sd-wan"],
        "email": {"enabled": False},
        "nvd_api_key": "",
    }
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    feeds_path.write_text(
        """
cyber:
  - name: Sample Cyber
    url: https://fixtures.local/cyber.xml
    color: "#e74c3c"
network:
  - name: Sample Net
    url: https://fixtures.local/net.xml
    color: "#0ea5e9"
cisco: []
fortinet: []
""",
        encoding="utf-8",
    )

    monkeypatch.setenv("CYBERDIGEST_HEADLESS", "1")
    monkeypatch.setenv("CYBERDIGEST_DATA_DIR", str(data))
    for key in (
        "NVD_API_KEY",
        "CYBERDIGEST_NVD_API_KEY",
        "CYBERDIGEST_SMTP_PASSWORD",
        "CYBERDIGEST_EMAIL_ENABLED",
    ):
        monkeypatch.delenv(key, raising=False)

    import cyberdigest.agent as agent_mod
    import cyberdigest.cli as cli_mod
    import cyberdigest.config as config_mod
    import cyberdigest.db as db_mod
    import cyberdigest.feeds as feeds_mod
    import cyberdigest.lock as lock_mod
    import cyberdigest.logging_setup as log_mod
    import cyberdigest.paths as paths
    import cyberdigest.reports as reports_mod

    # Redirect paths
    for mod in (
        paths,
        config_mod,
        db_mod,
        lock_mod,
        log_mod,
        agent_mod,
        reports_mod,
        feeds_mod,
        cli_mod,
    ):
        if hasattr(mod, "DATA_DIR"):
            monkeypatch.setattr(mod, "DATA_DIR", data, raising=False)
        if hasattr(mod, "REPORTS_DIR"):
            monkeypatch.setattr(mod, "REPORTS_DIR", reports, raising=False)
        if hasattr(mod, "DB_FILE"):
            monkeypatch.setattr(mod, "DB_FILE", data / "state.db", raising=False)
        if hasattr(mod, "LOG_FILE"):
            monkeypatch.setattr(mod, "LOG_FILE", data / "agent_log.txt", raising=False)
        if hasattr(mod, "STATUS_FILE"):
            monkeypatch.setattr(mod, "STATUS_FILE", data / "status.txt", raising=False)
        if hasattr(mod, "HEARTBEAT_FILE"):
            monkeypatch.setattr(mod, "HEARTBEAT_FILE", data / "heartbeat.txt", raising=False)
        if hasattr(mod, "LOCK_FILE"):
            monkeypatch.setattr(mod, "LOCK_FILE", data / "agent.lock", raising=False)
        if hasattr(mod, "CONFIG_FILE"):
            monkeypatch.setattr(mod, "CONFIG_FILE", cfg_path, raising=False)
        if hasattr(mod, "CONFIG_LOCAL_FILE"):
            monkeypatch.setattr(mod, "CONFIG_LOCAL_FILE", cfg_local, raising=False)
        if hasattr(mod, "CONFIG_EXAMPLE_FILE"):
            monkeypatch.setattr(mod, "CONFIG_EXAMPLE_FILE", cfg_example, raising=False)
        if hasattr(mod, "FEEDS_FILE"):
            monkeypatch.setattr(mod, "FEEDS_FILE", feeds_path, raising=False)

    monkeypatch.setattr(paths, "DATA_DIR", data)
    monkeypatch.setattr(paths, "REPORTS_DIR", reports)
    monkeypatch.setattr(paths, "DB_FILE", data / "state.db")
    monkeypatch.setattr(paths, "LOG_FILE", data / "agent_log.txt")
    monkeypatch.setattr(paths, "STATUS_FILE", data / "status.txt")
    monkeypatch.setattr(paths, "HEARTBEAT_FILE", data / "heartbeat.txt")
    monkeypatch.setattr(paths, "LOCK_FILE", data / "agent.lock")
    monkeypatch.setattr(paths, "CONFIG_FILE", cfg_path)
    monkeypatch.setattr(paths, "CONFIG_LOCAL_FILE", cfg_local)
    monkeypatch.setattr(paths, "CONFIG_EXAMPLE_FILE", cfg_example)
    monkeypatch.setattr(paths, "FEEDS_FILE", feeds_path)

    config_mod.CONFIG = {}
    cfg_loaded = config_mod.load_config(exit_on_error=False)
    config_mod.CONFIG = cfg_loaded

    db_mod.init_db()

    return {
        "data": data,
        "reports": reports,
        "config": cfg_path,
        "feeds": feeds_path,
        "cfg": cfg_loaded,
    }


@pytest.fixture
def mock_network_ok(monkeypatch):
    import cyberdigest.agent as agent
    import cyberdigest.network as net

    monkeypatch.setattr(net, "check_internet", lambda: True)
    monkeypatch.setattr(agent, "check_internet", lambda: True)
    monkeypatch.setattr(net, "is_headless", lambda: True)
    monkeypatch.setattr(agent, "is_headless", lambda: True)


@pytest.fixture
def mock_feeds_http(monkeypatch):
    """Serve fixture RSS for known fixture URLs; fail others."""
    import cyberdigest.feeds as feeds

    def fake_download(url: str) -> bytes:
        if url.endswith("cyber.xml") or "cyber.xml" in url:
            return SAMPLE_RSS.encode()
        if url.endswith("net.xml") or "net.xml" in url:
            return SAMPLE_NETWORK_RSS.encode()
        raise OSError(f"unexpected url {url}")

    monkeypatch.setattr(feeds, "_download_feed", fake_download)
    # Speed: no retry sleeps
    monkeypatch.setattr(feeds.time, "sleep", lambda *_a, **_k: None)

    import cyberdigest.enrich as enrich

    monkeypatch.setattr(
        enrich,
        "fetch_cve_score",
        lambda cve_id, budget=None: ("9.8", "CRITICAL") if cve_id else None,
    )
    monkeypatch.setattr(enrich.time, "sleep", lambda *_a, **_k: None)
