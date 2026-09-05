"""CVE enrichment pipeline: collect IDs → cache/lookup → attach to articles.

NVD rate-limit budget
---------------------
Without an API key, NVD is ~5 req / 30s. With a key, much higher.
We enforce a per-run budget so digests never hang for minutes:

  nvd_enabled          – master switch (default true)
  nvd_max_lookups      – max live HTTP lookups per run (cache hits free)
  nvd_timeout_seconds  – wall-clock budget for all live lookups
  nvd_sleep_no_key     – polite delay after each unauthenticated call
  nvd_sleep_with_key   – delay with API key
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request

from cyberdigest.config import get_config
from cyberdigest.db import get_cve_cached, put_cve_cache
from cyberdigest.logging_setup import log
from cyberdigest.textutil import extract_cve_ids, h

USER_AGENT = "CyberDigest/4.3 (+https://github.com/Madhumasa84/cyberdigest_84)"
_CVE_RE = re.compile(r"(CVE-\d{4}-\d{4,7})", re.IGNORECASE)


class NvdBudget:
    """Tracks live NVD lookups for a single enrich pass."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        max_lookups: int = 15,
        timeout_seconds: float = 25.0,
        sleep_no_key: float = 0.6,
        sleep_with_key: float = 0.2,
        has_api_key: bool = False,
    ):
        self.enabled = enabled
        self.max_lookups = max(0, int(max_lookups))
        self.timeout_seconds = max(0.0, float(timeout_seconds))
        self.sleep_no_key = max(0.0, float(sleep_no_key))
        self.sleep_with_key = max(0.0, float(sleep_with_key))
        self.has_api_key = has_api_key
        self.started = time.monotonic()
        self.lookups = 0
        self.cache_hits = 0
        self.skipped = 0
        self.failures = 0
        self._exhausted_reason: str | None = None

    def allow_live(self) -> bool:
        if not self.enabled:
            self._exhausted_reason = self._exhausted_reason or "nvd_disabled"
            self.skipped += 1
            return False
        if self.lookups >= self.max_lookups:
            self._exhausted_reason = self._exhausted_reason or "max_lookups"
            self.skipped += 1
            return False
        if (time.monotonic() - self.started) >= self.timeout_seconds:
            self._exhausted_reason = self._exhausted_reason or "timeout"
            self.skipped += 1
            return False
        return True

    def record_lookup(self) -> None:
        self.lookups += 1

    def record_cache_hit(self) -> None:
        self.cache_hits += 1

    def record_failure(self) -> None:
        self.failures += 1

    def sleep_politely(self) -> None:
        delay = self.sleep_with_key if self.has_api_key else self.sleep_no_key
        if delay > 0:
            time.sleep(delay)

    def summary(self) -> str:
        return (
            f"NVD budget: lookups={self.lookups}/{self.max_lookups} "
            f"cache_hits={self.cache_hits} skipped={self.skipped} "
            f"failures={self.failures} reason={self._exhausted_reason or 'ok'}"
        )


def _budget_from_config() -> NvdBudget:
    cfg = get_config()
    api_key = (cfg.get("nvd_api_key") or "").strip()
    return NvdBudget(
        enabled=bool(cfg.get("nvd_enabled", True)),
        max_lookups=int(cfg.get("nvd_max_lookups", 15)),
        timeout_seconds=float(cfg.get("nvd_timeout_seconds", 25)),
        sleep_no_key=float(cfg.get("nvd_sleep_no_key", 0.6)),
        sleep_with_key=float(cfg.get("nvd_sleep_with_key", 0.2)),
        has_api_key=bool(api_key),
    )


def fetch_cve_score(
    cve_id: str,
    budget: NvdBudget | None = None,
) -> tuple[str, str] | None:
    """Return (score, severity) from cache or NVD. Honors rate-limit budget."""
    cached = get_cve_cached(cve_id)
    if cached:
        if budget:
            budget.record_cache_hit()
        return cached

    if budget is None:
        budget = _budget_from_config()

    if not budget.allow_live():
        return None

    cfg = get_config()
    attempted = False
    try:
        headers = {"User-Agent": USER_AGENT}
        api_key = (cfg.get("nvd_api_key") or "").strip()
        if api_key:
            headers["apiKey"] = api_key
        req = urllib.request.Request(
            f"https://services.nvd.nist.gov/rest/json/cves/2.0?cveId={cve_id}",
            headers=headers,
        )
        budget.record_lookup()
        attempted = True
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read().decode())
        metrics = data.get("vulnerabilities", [{}])[0].get("cve", {}).get("metrics", {})
        for ver in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
            if ver in metrics:
                score = str(metrics[ver][0]["cvssData"]["baseScore"])
                sev = metrics[ver][0].get("baseSeverity") or metrics[ver][0]["cvssData"].get(
                    "baseSeverity", "UNKNOWN"
                )
                put_cve_cache(cve_id, score, sev)
                return score, sev
        budget.record_failure()
    except (
        urllib.error.HTTPError,
        urllib.error.URLError,
        TimeoutError,
        OSError,
        ValueError,
        KeyError,
        IndexError,
    ) as exc:
        budget.record_failure()
        log.debug("CVE lookup failed for %s: %s", cve_id, exc)
    except Exception as exc:  # pragma: no cover — unexpected
        budget.record_failure()
        log.debug("CVE lookup failed for %s: %s", cve_id, exc)
    finally:
        if attempted:
            budget.sleep_politely()
    return None


def collect_cve_ids(articles: list[dict]) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    for a in articles:
        blob = f"{a.get('title', '')} {a.get('summary', '')}"
        for cid in extract_cve_ids(blob):
            if cid not in seen:
                seen.add(cid)
                ids.append(cid)
    return ids


def enrich_articles(articles: list[dict]) -> dict[str, tuple[str, str]]:
    """
    Look up unique CVEs within the NVD budget, attach scores to articles.
    Call this BEFORE HTML rendering.
    """
    budget = _budget_from_config()
    scores: dict[str, tuple[str, str]] = {}
    for cid in collect_cve_ids(articles):
        info = fetch_cve_score(cid, budget=budget)
        if info:
            scores[cid] = info
    for a in articles:
        blob = f"{a.get('title', '')} {a.get('summary', '')}"
        a["cve_scores"] = {cid: scores[cid] for cid in extract_cve_ids(blob) if cid in scores}
    if budget.lookups or budget.skipped or budget.cache_hits:
        log.info(budget.summary())
    return scores


def format_with_cves(text: str, cve_scores: dict[str, tuple[str, str]] | None = None) -> str:
    """HTML-escape text and link CVE IDs with optional CVSS badges."""
    safe = h(text)
    scores = cve_scores or {}

    def repl(m: re.Match) -> str:
        cid = m.group(1).upper()
        display = m.group(1)
        link = (
            f'<a href="https://nvd.nist.gov/vuln/detail/{h(cid)}" '
            f'target="_blank" rel="noopener noreferrer" '
            f'style="color:#38bdf8;text-decoration:none">{h(display)}</a>'
        )
        info = scores.get(cid)
        if info:
            score, sev = info
            col = (
                "#ef4444"
                if sev.upper() in ("HIGH", "CRITICAL")
                else "#f59e0b"
                if sev.upper() == "MEDIUM"
                else "#3b82f6"
            )
            link += (
                f' <span style="background:{col};color:#fff;padding:1px 6px;'
                f'border-radius:4px;font-size:10px;font-weight:700;vertical-align:middle">'
                f"CVSS {h(score)}</span>"
            )
        return link

    return _CVE_RE.sub(repl, safe)
