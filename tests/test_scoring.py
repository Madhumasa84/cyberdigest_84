from cyberdigest.config import reload_config
from cyberdigest.scoring import cluster, score_severity


def setup_module():
    reload_config()


def test_cve_elevates_to_high():
    sev = score_severity("Vendor fixes CVE-2024-1111 in product", "details")
    assert sev in ("High", "Critical")


def test_zero_day_critical():
    assert score_severity("Major zero-day found", "research note") == "Critical"


def test_normal_news():
    assert score_severity("Company hires new CEO", "business update") == "Normal"


def test_cisa_category_critical():
    sev = score_severity(
        "CVE-2024-0001: Something",
        "Known exploited vulnerability listed by CISA.",
        source="CISA Advisories",
        category="cyber",
    )
    assert sev in ("High", "Critical")


def test_cluster_merges_similar_titles():
    arts = [
        {
            "title": "Critical Ransomware Hits Hospitals",
            "source": "A",
            "severity": "Critical",
            "other_sources": set(),
        },
        {
            "title": "Critical ransomware hits hospitals!",
            "source": "B",
            "severity": "High",
            "other_sources": set(),
        },
        {
            "title": "Totally unrelated weather story",
            "source": "C",
            "severity": "Normal",
            "other_sources": set(),
        },
    ]
    out = cluster(arts)
    assert len(out) == 2
    merged = next(a for a in out if "ransomware" in a["title"].lower())
    assert "B" in merged["other_sources"] or merged["source"] == "B"
