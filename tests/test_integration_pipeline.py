"""End-to-end agent pipeline with mocked network I/O."""

from __future__ import annotations

from pathlib import Path


def test_full_run_writes_reports(isolated_app, mock_network_ok, mock_feeds_http, monkeypatch):
    import cyberdigest.agent as agent
    import cyberdigest.reports as reports

    # Never open browser / notify in tests
    monkeypatch.setattr(agent, "_HAS_PLYER", False)
    monkeypatch.setattr(reports, "open_local_html", lambda p: None)
    monkeypatch.setattr(reports, "open_latest_report", lambda: False)

    ok = agent.run_agent(is_fallback=False)
    assert ok is True

    reports_dir: Path = isolated_app["reports"]
    cyber = list(reports_dir.glob("cybersec_report_*.html"))
    network = list(reports_dir.glob("network_report_*.html"))
    assert cyber, "expected cybersecurity report"
    assert network, "expected networking report"
    assert (reports_dir / "index.html").exists()

    html = cyber[0].read_text(encoding="utf-8")
    assert "CVE-2024-99999" in html or "cve-2024-99999" in html.lower()
    assert "javascript:alert" not in html
    assert "CVSS" in html  # badge from mocked NVD
    assert "Sample Cyber" in html

    status = (isolated_app["data"] / "status.txt").read_text(encoding="utf-8")
    assert "New Articles" in status
    assert (isolated_app["data"] / "heartbeat.txt").exists()
    assert (isolated_app["data"] / "state.db").exists()


def test_second_run_dedupes(isolated_app, mock_network_ok, mock_feeds_http, monkeypatch):
    import cyberdigest.agent as agent
    import cyberdigest.reports as reports

    monkeypatch.setattr(agent, "_HAS_PLYER", False)
    monkeypatch.setattr(reports, "open_local_html", lambda p: None)
    monkeypatch.setattr(reports, "open_latest_report", lambda: False)

    assert agent.run_agent(is_fallback=False) is True
    # Second run: same feed items already in seen DB → no new articles
    assert agent.run_agent(is_fallback=False) is False


def test_offline_skips_run(isolated_app, monkeypatch):
    import cyberdigest.agent as agent
    import cyberdigest.network as net

    monkeypatch.setattr(net, "check_internet", lambda: False)
    monkeypatch.setattr(agent, "check_internet", lambda: False)
    assert agent.run_agent() is False


def test_fetch_feed_blocks_javascript_links(isolated_app, mock_feeds_http):
    from cyberdigest.feeds import fetch_feed

    arts = fetch_feed(
        "Sample Cyber",
        "https://fixtures.local/cyber.xml",
        "#e74c3c",
        set(),
        "cyber",
        10,
    )
    links = [a["link"] for a in arts]
    assert all(link.startswith("https://") for link in links)
    assert not any("javascript" in link for link in links)
    titles = " ".join(a["title"] for a in arts)
    assert "CVE-2024-99999" in titles or "zero-day" in titles.lower()


def test_cli_force_with_mocks(isolated_app, mock_network_ok, mock_feeds_http, monkeypatch):
    import cyberdigest.agent as agent
    import cyberdigest.cli as cli
    import cyberdigest.reports as reports
    import cyberdigest.scheduler as sched

    monkeypatch.setattr(agent, "_HAS_PLYER", False)
    monkeypatch.setattr(reports, "open_local_html", lambda p: None)
    monkeypatch.setattr(reports, "open_latest_report", lambda: False)
    monkeypatch.setattr(sched, "verify_scheduler", lambda: False)
    monkeypatch.setattr(sched, "register_scheduler", lambda: False)
    monkeypatch.setattr(cli, "verify_scheduler", lambda: False)
    monkeypatch.setattr(cli, "register_scheduler", lambda: False)
    monkeypatch.setattr(cli, "is_headless", lambda: True)
    monkeypatch.setattr(cli, "has_gui", lambda: False)

    # --force should run once and exit (not enter infinite loop)
    rc = cli.main(["--force"])
    assert rc == 0
    assert list(isolated_app["reports"].glob("cybersec_report_*.html"))
