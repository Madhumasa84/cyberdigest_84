"""CLI-level unit checks (no long-running loops)."""

from __future__ import annotations


def test_version_flag():
    import cyberdigest.cli as cli

    try:
        cli.main(["--version"])
        assert False, "should SystemExit"
    except SystemExit as e:
        assert e.code == 0


def test_help_flag():
    import cyberdigest.cli as cli

    try:
        cli.main(["--help"])
        assert False, "should SystemExit"
    except SystemExit as e:
        assert e.code == 0


def test_healthcheck_offline_reports_issue(isolated_app, monkeypatch):
    import cyberdigest.cli as cli
    import cyberdigest.network as net
    import cyberdigest.scheduler as sched

    monkeypatch.setattr(net, "check_internet", lambda: False)
    monkeypatch.setattr(cli, "check_internet", lambda: False)
    monkeypatch.setattr(sched, "verify_scheduler", lambda: False)
    monkeypatch.setattr(cli, "verify_scheduler", lambda: False)
    monkeypatch.setattr(cli, "is_headless", lambda: True)
    monkeypatch.setattr(cli, "load_feeds", lambda: {
        "cyber": [],
        "network": [],
        "cisco": [],
        "fortinet": [],
    })

    rc = cli.run_healthcheck(require_scheduler=False)
    # No internet → overall unhealthy
    assert rc == 1


def test_healthcheck_headless_without_scheduler_can_be_healthy(
    isolated_app, mock_network_ok, monkeypatch
):
    import cyberdigest.cli as cli
    import cyberdigest.scheduler as sched

    monkeypatch.setattr(sched, "verify_scheduler", lambda: False)
    monkeypatch.setattr(cli, "verify_scheduler", lambda: False)
    monkeypatch.setattr(cli, "is_headless", lambda: True)
    monkeypatch.setattr(
        cli,
        "load_feeds",
        lambda: {"cyber": [], "network": [], "cisco": [], "fortinet": []},
    )

    rc = cli.run_healthcheck(require_scheduler=False)
    assert rc == 0
