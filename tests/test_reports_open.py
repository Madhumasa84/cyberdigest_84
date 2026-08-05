"""Report helpers: latest path, open, colors."""

from __future__ import annotations

from pathlib import Path


def test_latest_report_path(isolated_app):
    import cyberdigest.reports as reports

    rdir: Path = isolated_app["reports"]
    (rdir / "cybersec_report_20240101_1200.html").write_text("a", encoding="utf-8")
    (rdir / "network_report_20240102_1200.html").write_text("b", encoding="utf-8")
    p = reports.latest_report_path()
    assert p is not None
    assert p.exists()
    assert p.name == "network_report_20240102_1200.html"


def test_open_latest_missing(isolated_app, monkeypatch):
    import cyberdigest.reports as reports

    monkeypatch.setattr(reports, "latest_report_path", lambda: None)
    assert reports.open_latest_report() is False


def test_open_local_html_uses_xdg_or_webbrowser(isolated_app, monkeypatch, tmp_path):
    import platform
    import subprocess

    import cyberdigest.reports as reports

    f = tmp_path / "x.html"
    f.write_text("<html>hi</html>", encoding="utf-8")

    called = {"xdg": False}

    def fake_popen(cmd, **kwargs):
        called["xdg"] = True
        called["cmd"] = cmd

        class P:
            pass

        return P()

    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    ok = reports.open_local_html(f)
    assert ok is True
    assert called["xdg"] is True


def test_open_windows_uses_cmd_start(isolated_app, monkeypatch, tmp_path):
    import platform
    import subprocess

    import cyberdigest.reports as reports

    f = tmp_path / "win.html"
    f.write_text("<html>hi</html>", encoding="utf-8")
    seen = {}

    def fake_popen(cmd, **kwargs):
        seen["cmd"] = cmd

        class P:
            pass

        return P()

    monkeypatch.setattr(platform, "system", lambda: "Windows")
    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    ok = reports.open_local_html(f)
    assert ok is True
    assert seen["cmd"][0] == "cmd"
    assert "start" in seen["cmd"]


def test_open_local_html_reports_all_openers_failed(isolated_app, monkeypatch, tmp_path):
    import platform
    import subprocess
    import webbrowser

    import cyberdigest.reports as reports

    report = tmp_path / "report.html"
    report.write_text("<html></html>", encoding="utf-8")
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setattr(
        subprocess,
        "Popen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("no opener")),
    )
    monkeypatch.setattr(webbrowser, "open", lambda *_args, **_kwargs: False)

    assert reports.open_local_html(report) is False
