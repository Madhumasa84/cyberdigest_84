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

    class Res:
        stdout = ""
        returncode = 0

    monkeypatch.setattr(sched.subprocess, "run", lambda *a, **k: Res())
    monkeypatch.setattr(sched, "verify_scheduler", lambda: True)
    monkeypatch.setattr(sched, "get_config", lambda: {"interval_days": 3})
    assert sched.register_scheduler() is True


def test_uninstall_scheduler_linux(monkeypatch, capsys):
    monkeypatch.setattr(sched.platform, "system", lambda: "Linux")

    class Res:
        returncode = 0
        stdout = "0 10 * * * news_agent.py\nother job\n"

    monkeypatch.setattr(sched.subprocess, "run", lambda *a, **k: Res())
    sched.uninstall_scheduler()
    out = capsys.readouterr().out
    assert "removed" in out.lower() or "✔" in out
