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


def test_open_latest_missing(isolated_app, monkeypatch):
    import cyberdigest.reports as reports

    monkeypatch.setattr(reports, "latest_report_path", lambda: None)
    assert reports.open_latest_report() is False


def test_open_local_html_uses_xdg_or_webbrowser(isolated_app, monkeypatch, tmp_path):
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

    monkeypatch.setattr(reports.platform if hasattr(reports, "platform") else __import__("platform"), "system", lambda: "Linux")
    import platform
    import subprocess

    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    ok = reports.open_local_html(f)
    assert ok is True
    assert called["xdg"] is True
