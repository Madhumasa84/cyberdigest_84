"""NVD rate-limit budget behaviour."""

from __future__ import annotations

import json
from io import BytesIO

from cyberdigest.enrich import NvdBudget, enrich_articles, fetch_cve_score


def test_budget_skips_after_max_lookups(isolated_app, monkeypatch):
    import cyberdigest.enrich as enrich

    calls = {"n": 0}

    def fake_urlopen(req, timeout=8):
        calls["n"] += 1
        payload = {
            "vulnerabilities": [
                {
                    "cve": {
                        "metrics": {
                            "cvssMetricV31": [
                                {
                                    "cvssData": {"baseScore": 9.8, "baseSeverity": "CRITICAL"},
                                    "baseSeverity": "CRITICAL",
                                }
                            ]
                        }
                    }
                }
            ]
        }
        return BytesIO(json.dumps(payload).encode())

    class CM:
        def __init__(self, bio):
            self.bio = bio

        def __enter__(self):
            return self.bio

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        enrich.urllib.request,
        "urlopen",
        lambda req, timeout=8: CM(fake_urlopen(req, timeout)),
    )
    monkeypatch.setattr(enrich.time, "sleep", lambda *_a, **_k: None)

    budget = NvdBudget(
        enabled=True,
        max_lookups=2,
        timeout_seconds=60,
        sleep_no_key=0,
        sleep_with_key=0,
    )
    # Use unique IDs not in cache
    ids = [f"CVE-2099-{i:04d}" for i in range(5)]
    results = [fetch_cve_score(cid, budget=budget) for cid in ids]
    assert sum(1 for r in results if r is not None) == 2
    assert budget.lookups == 2
    assert budget.skipped >= 3


def test_budget_disabled(isolated_app, monkeypatch):
    import cyberdigest.enrich as enrich

    monkeypatch.setattr(
        enrich.urllib.request,
        "urlopen",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not call NVD")),
    )
    budget = NvdBudget(enabled=False, max_lookups=10, timeout_seconds=30)
    assert fetch_cve_score("CVE-2098-0001", budget=budget) is None
    assert budget.skipped >= 1


def test_enrich_articles_uses_config_budget(isolated_app, monkeypatch):
    import cyberdigest.config as config_mod
    import cyberdigest.enrich as enrich

    cfg = config_mod.get_config()
    cfg["nvd_max_lookups"] = 1
    cfg["nvd_timeout_seconds"] = 60
    cfg["nvd_sleep_no_key"] = 0
    cfg["nvd_sleep_with_key"] = 0

    payload = {
        "vulnerabilities": [
            {
                "cve": {
                    "metrics": {
                        "cvssMetricV31": [
                            {
                                "cvssData": {"baseScore": 7.5, "baseSeverity": "HIGH"},
                                "baseSeverity": "HIGH",
                            }
                        ]
                    }
                }
            }
        ]
    }

    class CM:
        def __enter__(self):
            return BytesIO(json.dumps(payload).encode())

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(enrich.urllib.request, "urlopen", lambda *a, **k: CM())
    monkeypatch.setattr(enrich.time, "sleep", lambda *_a, **_k: None)

    arts = [
        {"title": "CVE-2097-1111 one", "summary": ""},
        {"title": "CVE-2097-2222 two", "summary": ""},
        {"title": "CVE-2097-3333 three", "summary": ""},
    ]
    scores = enrich_articles(arts)
    # Only one live lookup allowed
    assert len(scores) == 1


def test_cache_hit_does_not_count_as_lookup(isolated_app, monkeypatch):
    import cyberdigest.enrich as enrich
    from cyberdigest.db import put_cve_cache

    put_cve_cache("CVE-2096-0001", "5.0", "MEDIUM")
    monkeypatch.setattr(
        enrich.urllib.request,
        "urlopen",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no network")),
    )
    budget = NvdBudget(max_lookups=0, timeout_seconds=1)
    assert fetch_cve_score("CVE-2096-0001", budget=budget) == ("5.0", "MEDIUM")
    assert budget.cache_hits == 1
    assert budget.lookups == 0
