"""Small tests to cover remaining high-value branches."""

from __future__ import annotations


def test_network_windows_darwin(monkeypatch):
    import cyberdigest.network as net

    monkeypatch.delenv("CYBERDIGEST_HEADLESS", raising=False)
    monkeypatch.setattr(net.platform, "system", lambda: "Windows")
    assert net.is_headless() is False
    monkeypatch.setattr(net.platform, "system", lambda: "Darwin")
    assert net.is_headless() is False


def test_pid_alive_and_dead(monkeypatch):
    import cyberdigest.lock as lock_mod

    assert lock_mod._pid_alive(-1) is False
    assert lock_mod._pid_alive(0) is False
    # current process is alive
    import os

    assert lock_mod._pid_alive(os.getpid()) is True


def test_config_env_email_and_interval(monkeypatch, tmp_path):
    import json

    from cyberdigest import config as config_mod

    base = dict(config_mod.DEFAULT_CONFIG)
    (tmp_path / "config.json").write_text(json.dumps(base), encoding="utf-8")
    monkeypatch.setattr(config_mod, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(config_mod, "CONFIG_LOCAL_FILE", tmp_path / "nolocal.json")
    monkeypatch.setattr(config_mod, "CONFIG_EXAMPLE_FILE", tmp_path / "ex.json")
    monkeypatch.setenv("CYBERDIGEST_EMAIL_ENABLED", "true")
    monkeypatch.setenv("CYBERDIGEST_SMTP_HOST", "smtp.example")
    monkeypatch.setenv("CYBERDIGEST_SMTP_PORT", "465")
    monkeypatch.setenv("CYBERDIGEST_SMTP_USERNAME", "u@ex")
    monkeypatch.setenv("CYBERDIGEST_SMTP_PASSWORD", "secret")
    monkeypatch.setenv("CYBERDIGEST_EMAIL_FROM", "from@ex")
    monkeypatch.setenv("CYBERDIGEST_EMAIL_TO", "a@ex, b@ex")
    monkeypatch.setenv("CYBERDIGEST_INTERVAL_DAYS", "5")
    monkeypatch.setenv("CYBERDIGEST_NVD_API_KEY", "key-from-env")
    config_mod.CONFIG = {}
    cfg = config_mod.load_config(exit_on_error=False)
    assert cfg["email"]["enabled"] is True
    assert cfg["email"]["smtp_host"] == "smtp.example"
    assert cfg["email"]["smtp_port"] == 465
    assert cfg["email"]["to_addrs"] == ["a@ex", "b@ex"]
    assert cfg["interval_days"] == 5
    assert cfg["nvd_api_key"] == "key-from-env"


def test_healthcheck_require_scheduler(isolated_app, mock_network_ok, monkeypatch):
    import cyberdigest.cli as cli

    monkeypatch.setattr(cli, "verify_scheduler", lambda: False)
    monkeypatch.setattr(cli, "is_headless", lambda: False)
    monkeypatch.setattr(
        cli,
        "load_feeds",
        lambda: {"cyber": [], "network": [], "cisco": [], "fortinet": []},
    )
    assert cli.run_healthcheck(require_scheduler=True) == 1


def test_budget_timeout(isolated_app, monkeypatch):
    import cyberdigest.enrich as enrich
    from cyberdigest.enrich import NvdBudget, fetch_cve_score

    budget = NvdBudget(
        enabled=True,
        max_lookups=100,
        timeout_seconds=0,  # immediately exhausted
        sleep_no_key=0,
    )
    monkeypatch.setattr(
        enrich.urllib.request,
        "urlopen",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no call")),
    )
    assert fetch_cve_score("CVE-2095-0001", budget=budget) is None
    assert budget.skipped >= 1
    assert "timeout" in (budget._exhausted_reason or "")


def test_feeds_json_document():
    from cyberdigest.feeds import _load_feeds_document

    data = _load_feeds_document(
        '{"cyber": [{"name": "A", "url": "https://a.test", "color": "#fff"}]}'
    )
    assert data["cyber"][0]["name"] == "A"
