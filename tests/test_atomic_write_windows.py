"""Cross-platform atomic write must overwrite existing files (Windows rename fails)."""

from __future__ import annotations

from pathlib import Path


def test_atomic_write_overwrites_existing(tmp_path):
    from cyberdigest.agent import _atomic_write

    target = tmp_path / "report.html"
    _atomic_write(target, "first")
    assert target.read_text(encoding="utf-8") == "first"
    _atomic_write(target, "second")
    assert target.read_text(encoding="utf-8") == "second"
    assert not list(tmp_path.glob("*.tmp"))


def test_index_html_regenerate(isolated_app):
    import cyberdigest.reports as reports

    reports.generate_index_html()
    idx: Path = isolated_app["reports"] / "index.html"
    assert idx.exists()
    first = idx.read_text(encoding="utf-8")
    reports.generate_index_html()  # second write must not raise on Windows
    assert idx.exists()
    assert "CyberDigest Archive" in idx.read_text(encoding="utf-8")
    assert first  # prior content existed
