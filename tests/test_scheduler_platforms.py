"""Scheduler branches for Windows / Darwin / Linux."""

from __future__ import annotations

from pathlib import Path

import cyberdigest.scheduler as sched


def test_verify_windows(monkeypatch):
    monkeypatch.setattr(sched.platform, "system", lambda: "Windows")

    class Res:
        stdout = "TaskName: CyberDigest\n"
        returncode = 0

    monkeypatch.setattr(sched.subprocess, "run", lambda *a, **k: Res())
    assert sched.verify_scheduler() is True


def test_verify_darwin(monkeypatch):
    monkeypatch.setattr(sched.platform, "system", lambda: "Darwin")

    class Res:
        stdout = "123\t0\tcom.cyberdigest\n"
        returncode = 0

    monkeypatch.setattr(sched.subprocess, "run", lambda *a, **k: Res())
    assert sched.verify_scheduler() is True


def test_register_windows_ok(monkeypatch):
    monkeypatch.setattr(sched.platform, "system", lambda: "Windows")

    class Res:
        returncode = 0
        stdout = "SUCCESS"
        stderr = ""

    monkeypatch.setattr(sched.subprocess, "run", lambda *a, **k: Res())
    monkeypatch.setattr(sched, "verify_scheduler", lambda: True)
    monkeypatch.setattr(sched, "get_config", lambda: {"interval_days": 3})
    assert sched.register_scheduler() is True


def test_register_windows_fail(monkeypatch):
    monkeypatch.setattr(sched.platform, "system", lambda: "Windows")

    class Res:
        returncode = 1
        stdout = ""
        stderr = "access denied"

    monkeypatch.setattr(sched.subprocess, "run", lambda *a, **k: Res())
    monkeypatch.setattr(sched, "get_config", lambda: {"interval_days": 3})
    assert sched.register_scheduler() is False


def test_register_darwin(monkeypatch, tmp_path):
    monkeypatch.setattr(sched.platform, "system", lambda: "Darwin")
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)

    class Res:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr(sched.subprocess, "run", lambda *a, **k: Res())
    monkeypatch.setattr(sched, "verify_scheduler", lambda: True)
    monkeypatch.setattr(sched, "get_config", lambda: {"interval_days": 2})
    assert sched.register_scheduler() is True
    plist = home / "Library" / "LaunchAgents" / "com.cyberdigest.plist"
    assert plist.exists()
    assert "StartInterval" in plist.read_text()


def test_uninstall_windows(monkeypatch, capsys):
    monkeypatch.setattr(sched.platform, "system", lambda: "Windows")

    class Res:
        returncode = 0

    monkeypatch.setattr(sched.subprocess, "run", lambda *a, **k: Res())
    sched.uninstall_scheduler()
    out = capsys.readouterr().out
    assert "removed" in out.lower() or "✔" in out


def test_uninstall_darwin(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(sched.platform, "system", lambda: "Darwin")
    home = tmp_path / "home"
    la = home / "Library" / "LaunchAgents"
    la.mkdir(parents=True)
    pp = la / "com.cyberdigest.plist"
    pp.write_text("<plist/>")
    monkeypatch.setattr(Path, "home", lambda: home)

    class Res:
        returncode = 0

    monkeypatch.setattr(sched.subprocess, "run", lambda *a, **k: Res())
    sched.uninstall_scheduler()
    assert not pp.exists()
