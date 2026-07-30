from pathlib import Path

def test_latest_report_name(isolated_app):
    import cyberdigest.reports as reports

    # Should return None when no reports match prefix
    assert reports.latest_report_name("cybersec_report_") is None

    # Write multiple reports with same prefix
    rdir: Path = isolated_app["reports"]

    reports_to_create = [
        "cybersec_report_20240101_1200.html",
        "cybersec_report_20240105_1200.html",
        "cybersec_report_20240103_1200.html",
        "other_report_20240110_1200.html"
    ]
    for r in reports_to_create:
        (rdir / r).write_text("dummy content", encoding="utf-8")

    # The glob sorted backwards should return the latest one alphabetically
    name = reports.latest_report_name("cybersec_report_")
    assert name == "cybersec_report_20240105_1200.html"

    # Check what happens for other_report_
    other = reports.latest_report_name("other_report_")
    assert other == "other_report_20240110_1200.html"

def test_first_available_report(isolated_app):
    import cyberdigest.reports as reports

    rdir: Path = isolated_app["reports"]

    # 1. Empty list
    assert reports.first_available_report([]) is None

    # 2. None in list or all non-existent
    assert reports.first_available_report([None]) is None
    assert reports.first_available_report([rdir / "non_existent.html"]) is None

    # 3. Finding the first existing
    f1 = rdir / "f1.html"
    f2 = rdir / "f2.html"
    f2.write_text("exists", encoding="utf-8")

    # Since f1 doesn't exist, it should return f2
    assert reports.first_available_report([f1, f2]) == f2

    # 4. First one exists
    f1.write_text("now exists", encoding="utf-8")
    assert reports.first_available_report([f1, f2]) == f1
