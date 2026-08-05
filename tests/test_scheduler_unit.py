import cyberdigest.scheduler as sched


def test_verify_scheduler_linux_mock(monkeypatch):
    monkeypatch.setattr(sched.platform, "system", lambda: "Linux")

    class Res:
        stdout = "0 10 */3 * * /usr/bin/python /app/news_agent.py --cli-only\n"
        returncode = 0

    monkeypatch.setattr(sched.subprocess, "run", lambda *a, **k: Res())
    assert sched.verify_scheduler() is True


def test_verify_scheduler_missing(monkeypatch):
    monkeypatch.setattr(sched.platform, "system", lambda: "Linux")

    class Res:
        stdout = "# empty crontab\n"
        returncode = 0

    monkeypatch.setattr(sched.subprocess, "run", lambda *a, **k: Res())
    assert sched.verify_scheduler() is False


def test_register_scheduler_linux(monkeypatch):
    monkeypatch.setattr(sched.platform, "system", lambda: "Linux")

    calls = []

    class Res:
        stdout = ""
        returncode = 0

    def fake_run(*args, **kwargs):
        calls.append((args, kwargs))
        return Res()

    monkeypatch.setattr(sched.subprocess, "run", fake_run)
    monkeypatch.setattr(sched, "verify_scheduler", lambda: True)
    assert sched.register_scheduler() is True
    cron_text = calls[-1][1]["input"]
    assert "0 10 * * *" in cron_text
    assert "--once --cli-only" in cron_text
    assert "--force" not in cron_text
    assert sched.CRON_MARKER in cron_text


def test_scheduled_command_uses_module_for_installed_package(monkeypatch, tmp_path):
    monkeypatch.setattr(sched, "SOURCE_ROOT", None)
    monkeypatch.setattr(sched.sys, "executable", "/opt/python")

    assert sched._scheduled_command() == [
        "/opt/python",
        "-m",
        "cyberdigest",
        "--once",
        "--cli-only",
    ]


def test_scheduled_command_uses_launcher_in_source_checkout(monkeypatch, tmp_path):
    launcher = tmp_path / "news_agent.py"
    launcher.write_text("", encoding="utf-8")
    monkeypatch.setattr(sched, "SOURCE_ROOT", tmp_path)
    monkeypatch.setattr(sched.sys, "executable", "/opt/python")

    assert sched._scheduled_command() == [
        "/opt/python",
        str(launcher),
        "--once",
        "--cli-only",
    ]


def test_uninstall_scheduler_linux(monkeypatch, capsys):
    monkeypatch.setattr(sched.platform, "system", lambda: "Linux")

    class Res:
        returncode = 0
        stdout = "0 10 * * * news_agent.py\nother job\n"

    monkeypatch.setattr(sched.subprocess, "run", lambda *a, **k: Res())
    sched.uninstall_scheduler()
    out = capsys.readouterr().out
    assert "removed" in out.lower() or "✔" in out
