"""Exercise more of cli.main without hanging on loops."""

from __future__ import annotations


def _stub_runtime(monkeypatch, isolated_app):
    import cyberdigest.agent as agent
    import cyberdigest.cli as cli
    import cyberdigest.reports as reports
    import cyberdigest.scheduler as sched

    monkeypatch.setattr(agent, "_HAS_PLYER", False)
    monkeypatch.setattr(agent, "run_agent", lambda **k: True)
    monkeypatch.setattr(reports, "open_local_html", lambda p: None)
    monkeypatch.setattr(reports, "open_latest_report", lambda: True)
    monkeypatch.setattr(sched, "verify_scheduler", lambda: True)
    monkeypatch.setattr(sched, "register_scheduler", lambda: True)
    monkeypatch.setattr(cli, "verify_scheduler", lambda: True)
    monkeypatch.setattr(cli, "register_scheduler", lambda: True)
    monkeypatch.setattr(cli, "has_gui", lambda: False)
    monkeypatch.setattr(cli, "is_headless", lambda: True)
    monkeypatch.setattr(cli, "check_internet", lambda: True)
    return cli


def test_main_once_headless(isolated_app, monkeypatch):
    cli = _stub_runtime(monkeypatch, isolated_app)
    rc = cli.main(["--once", "--cli-only"])
    assert rc == 0


def test_main_force(isolated_app, monkeypatch):
    cli = _stub_runtime(monkeypatch, isolated_app)
    rc = cli.main(["--force"])
    assert rc == 0


def test_main_lock_contention(isolated_app, monkeypatch):
    import cyberdigest.cli as cli

    monkeypatch.setattr(cli, "acquire_lock", lambda: False)
    monkeypatch.setattr(cli, "is_headless", lambda: True)
    monkeypatch.setattr(cli, "open_latest_report", lambda: False)
    rc = cli.main(["--force"])
    assert rc == 1


def test_main_lock_contention_opens_report(isolated_app, monkeypatch):
    import cyberdigest.cli as cli

    monkeypatch.setattr(cli, "acquire_lock", lambda: False)
    monkeypatch.setattr(cli, "is_headless", lambda: False)
    monkeypatch.setattr(cli, "open_latest_report", lambda: True)
    rc = cli.main([])
    assert rc == 0


def test_main_recent_run_skips_agent(isolated_app, monkeypatch):
    from datetime import datetime, timedelta

    import cyberdigest.cli as cli
    import cyberdigest.db as db

    _stub_runtime(monkeypatch, isolated_app)
    monkeypatch.setattr(cli, "is_headless", lambda: False)
    monkeypatch.setattr(cli, "has_gui", lambda: False)
    monkeypatch.setattr(
        db, "get_last_run", lambda: datetime.now() - timedelta(hours=1)
    )
    monkeypatch.setattr(cli, "get_last_run", lambda: datetime.now() - timedelta(hours=1))
    ran = {"n": 0}
    monkeypatch.setattr(cli, "run_agent", lambda **k: ran.__setitem__("n", ran["n"] + 1) or True)
    rc = cli.main(["--once", "--cli-only"])
    assert rc == 0
    assert ran["n"] == 0


def test_main_uninstall(isolated_app, monkeypatch):
    import cyberdigest.cli as cli

    called = {"n": 0}
    monkeypatch.setattr(cli, "uninstall_scheduler", lambda: called.__setitem__("n", 1))
    rc = cli.main(["--uninstall"])
    assert rc == 0
    assert called["n"] == 1


def test_main_desktop_tray_path(isolated_app, monkeypatch):
    import cyberdigest.cli as cli

    monkeypatch.setattr(cli, "is_headless", lambda: False)
    monkeypatch.setattr(cli, "has_gui", lambda: True)
    monkeypatch.setattr(cli, "register_scheduler", lambda: True)
    monkeypatch.setattr(cli, "run_agent", lambda **k: True)
    monkeypatch.setattr(cli, "open_latest_report", lambda: True)
    monkeypatch.setattr(cli, "get_last_run", lambda: None)
    monkeypatch.setattr(cli, "run_tray_gui", lambda **k: True)
    rc = cli.main([])
    assert rc == 0


def test_main_due_run_with_once(isolated_app, monkeypatch):
    from datetime import datetime, timedelta

    import cyberdigest.cli as cli

    _stub_runtime(monkeypatch, isolated_app)
    monkeypatch.setattr(cli, "is_headless", lambda: True)
    monkeypatch.setattr(cli, "get_last_run", lambda: datetime.now() - timedelta(days=10))
    ran = {"n": 0}

    def _run(**k):
        ran["n"] += 1
        return True

    monkeypatch.setattr(cli, "run_agent", _run)
    rc = cli.main(["--once"])
    assert rc == 0
    assert ran["n"] == 1
