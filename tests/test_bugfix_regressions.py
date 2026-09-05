"""Regressions for scoring/feeds/enrich/report bugs."""

from __future__ import annotations

import re

import pytest

from cyberdigest.config import _apply_env_secrets
from cyberdigest.feeds import DEFAULT_CYBER_FEEDS, _parse_feed_list
from cyberdigest.reports import _JS, _card
from cyberdigest.scoring import score_severity


def test_severity_sort_handles_rank_zero():
    """Critical maps to rank 0, which must not be coerced to the fallback rank."""
    assert "so[a.dataset.severity]||3" not in _JS
    assert "(a.dataset.severity in so)?so[a.dataset.severity]:3" in _JS
    assert re.search(r"\(b\.dataset\.severity in so\)\?so\[b\.dataset\.severity\]:3", _JS)


def test_removed_keywords_are_not_scored(isolated_app):
    cfg = isolated_app["cfg"]
    cfg["critical_keywords"] = []
    cfg["high_keywords"] = []
    assert score_severity("Ransomware hits hospital", "no cve here") == "Normal"
    assert score_severity("New flaw disclosed", "vendor patch pending") == "Normal"


def test_configured_keywords_still_match(isolated_app):
    cfg = isolated_app["cfg"]
    cfg["critical_keywords"] = ["ransomware"]
    cfg["high_keywords"] = ["patch"]
    assert score_severity("Ransomware hits hospital", "") == "Critical"
    assert score_severity("Vendor ships patch", "") == "High"
    # Boundary matching still guards short tokens
    assert score_severity("Dispatcher software released", "") == "Normal"


def test_unusable_feed_section_does_not_fall_back_to_defaults():
    parsed = _parse_feed_list([{"name": "evil", "url": "javascript:alert(1)"}], DEFAULT_CYBER_FEEDS)
    assert parsed == []


def test_valid_feed_entries_are_kept():
    parsed = _parse_feed_list(
        [
            {"name": "evil", "url": "javascript:alert(1)"},
            {"name": "good", "url": "https://example.com/rss"},
        ],
        DEFAULT_CYBER_FEEDS,
    )
    assert parsed == [("good", "https://example.com/rss", "#3b82f6")]


def test_missing_section_still_uses_defaults():
    assert _parse_feed_list(None, DEFAULT_CYBER_FEEDS) == list(DEFAULT_CYBER_FEEDS)


def test_failed_lookup_still_sleeps_politely(isolated_app, monkeypatch):
    import cyberdigest.enrich as enrich

    slept: list[float] = []
    monkeypatch.setattr(enrich.time, "sleep", lambda seconds: slept.append(seconds))
    monkeypatch.setattr(
        enrich.urllib.request,
        "urlopen",
        lambda *a, **k: (_ for _ in ()).throw(OSError("nvd is angry")),
    )

    budget = enrich.NvdBudget(max_lookups=2, timeout_seconds=60, sleep_no_key=0.6)
    assert enrich.fetch_cve_score("CVE-2095-0001", budget=budget) is None
    assert budget.failures == 1
    assert slept == [0.6]


def test_skipped_lookup_does_not_sleep(isolated_app, monkeypatch):
    import cyberdigest.enrich as enrich

    slept: list[float] = []
    monkeypatch.setattr(enrich.time, "sleep", lambda seconds: slept.append(seconds))
    budget = enrich.NvdBudget(enabled=False, sleep_no_key=0.6)
    assert enrich.fetch_cve_score("CVE-2095-0002", budget=budget) is None
    assert slept == []


@pytest.mark.parametrize("severity", ["Info", "", None])
def test_card_tolerates_unknown_severity(severity):
    art = {
        "severity": severity,
        "title": "Odd article",
        "summary": "body",
        "source": "Src",
        "published": "",
        "timestamp": 0,
        "link": "https://example.com/a",
    }
    html = _card(art)
    assert 'data-severity="Normal"' in html


def test_normal_counts_include_normalized_severities(isolated_app):
    from cyberdigest.reports import generate_html

    def art(severity: str, title: str) -> dict:
        return {
            "title": title,
            "summary": "body",
            "link": "https://example.com/a",
            "published": "today",
            "timestamp": 1.0,
            "color": "#e74c3c",
            "source": "Src",
            "severity": severity,
            "other_sources": set(),
            "cve_scores": {},
        }

    html = generate_html(
        [art("Critical", "c"), art("High", "hi"), art("Normal", "n"), art("Info", "i")],
        "20260101_1200",
        {},
        "",
        [("Src", "https://example.com", "#e74c3c")],
        "cyber",
        {},
    )
    assert html.count('data-severity="Normal"') == 2
    assert 'data-f="Normal">&#x1F535; Normal (2)' in html
    assert 'data-f="Critical">&#x1F534; Critical (1)' in html


def test_env_secrets_replace_invalid_email_block(monkeypatch):
    monkeypatch.setenv("CYBERDIGEST_SMTP_PASSWORD", "s3cret")
    cfg = _apply_env_secrets({"email": "not-an-object"})
    assert cfg["email"] == {"password": "s3cret"}


def test_duplicate_feed_names_counted_once(isolated_app, monkeypatch):
    import cyberdigest.agent as agent

    monkeypatch.setattr(agent, "fetch_feed", lambda *a, **k: [])
    feeds = {
        "cyber": [("Shared", "https://example.com/rss", "#fff")],
        "network": [("Shared", "https://example.com/rss", "#fff")],
        "cisco": [],
        "fortinet": [],
    }
    _articles, _health, ok_count, fail_count = agent._fetch_articles(
        feeds, set(), isolated_app["cfg"]
    )
    assert (ok_count, fail_count) == (1, 0)
