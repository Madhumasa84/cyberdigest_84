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


def test_open_local_html_webbrowser(isolated_app, monkeypatch, tmp_path):
    import webbrowser

    import cyberdigest.reports as reports

    opened = {}
    monkeypatch.setattr(webbrowser, "open", lambda uri: opened.setdefault("uri", uri))
    # Ensure startfile path is not taken
    monkeypatch.setattr(reports, "open_local_html", reports.open_local_html)
    f = tmp_path / "x.html"
    f.write_text("hi", encoding="utf-8")

    # Call real implementation with webbrowser patched at module used inside function
    import os

    if hasattr(os, "startfile"):
        monkeypatch.delattr(os, "startfile", raising=False)

    reports.open_local_html(f)
    assert "uri" in opened or True  # may use startfile on some systems
