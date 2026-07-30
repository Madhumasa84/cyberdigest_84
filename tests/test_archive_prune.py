"""Archive retention policy."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path


def test_global_archive_prunes_across_categories(isolated_app, monkeypatch):
    import cyberdigest.config as config_mod
    import cyberdigest.reports as reports

    reports_dir: Path = isolated_app["reports"]
    base = datetime(2024, 1, 1, 10, 0)
    # Create 4 cyber + 4 network = 8 files; max_archived_reports=5 global
    for i in range(4):
        ts = (base + timedelta(hours=i)).strftime("%Y%m%d_%H%M")
        (reports_dir / f"cybersec_report_{ts}.html").write_text("c", encoding="utf-8")
        (reports_dir / f"network_report_{ts}.html").write_text("n", encoding="utf-8")

    cfg = config_mod.get_config()
    cfg["max_archived_reports"] = 5
    cfg["archive_global"] = True

    reports.generate_index_html()

    remaining = list(reports_dir.glob("*_report_*.html"))
    assert len(remaining) <= 5
    assert (reports_dir / "index.html").exists()


def test_prune_reports_unlink_error_ignored(isolated_app, monkeypatch):
    import cyberdigest.config as config_mod
    import cyberdigest.reports as reports

    reports_dir: Path = isolated_app["reports"]
    base = datetime(2024, 1, 1, 10, 0)

    # Create 4 reports
    for i in range(4):
        ts = (base + timedelta(hours=i)).strftime("%Y%m%d_%H%M")
        (reports_dir / f"cybersec_report_{ts}.html").write_text("c", encoding="utf-8")

    cfg = config_mod.get_config()
    cfg["max_archived_reports"] = 2  # Less than 4 to trigger pruning

    def mock_unlink(self, *args, **kwargs):
        raise OSError("Mock error")

    monkeypatch.setattr(Path, "unlink", mock_unlink)

    # Test with archive_global = True
    cfg["archive_global"] = True
    reports.generate_index_html()  # Should not crash

    # Test with archive_global = False
    cfg["archive_global"] = False
    reports.generate_index_html()  # Should not crash
