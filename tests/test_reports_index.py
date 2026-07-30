from __future__ import annotations


def test_generate_index_bad_date_format(isolated_app):
    import cyberdigest.reports as reports
    reports_dir = isolated_app["reports"]

    (reports_dir / "cybersec_report_bad_date_format.html").write_text("dummy", encoding="utf-8")

    reports.generate_index_html()

    index_html = (reports_dir / "index.html").read_text(encoding="utf-8")
    assert "bad_date_format" in index_html
