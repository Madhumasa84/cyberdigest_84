from cyberdigest.enrich import collect_cve_ids, enrich_articles, format_with_cves


def test_format_with_cves_badge():
    html = format_with_cves(
        "See CVE-2024-1234 now",
        {"CVE-2024-1234": ("9.1", "CRITICAL")},
    )
    assert "nvd.nist.gov" in html
    assert "CVSS 9.1" in html
    assert "&lt;" not in html or "CVE" in html


def test_format_escapes_html():
    html = format_with_cves("<b>bold</b> CVE-2021-44228", {})
    assert "<b>" not in html
    assert "&lt;b&gt;" in html


def test_collect_and_enrich(isolated_app, monkeypatch):
    import cyberdigest.enrich as enrich

    monkeypatch.setattr(enrich, "fetch_cve_score", lambda c, budget=None: ("5.0", "MEDIUM"))
    arts = [
        {"title": "CVE-2020-1111 issue", "summary": "x"},
        {"title": "no cve here", "summary": "y"},
    ]
    ids = collect_cve_ids(arts)
    assert ids == ["CVE-2020-1111"]
    scores = enrich_articles(arts)
    assert "CVE-2020-1111" in scores
    assert arts[0]["cve_scores"]["CVE-2020-1111"] == ("5.0", "MEDIUM")
