"""Article severity scoring and cross-source clustering."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from cyberdigest.config import get_config
from cyberdigest.textutil import extract_cve_ids

# Short tokens matched with word boundaries to reduce false positives
_SHORT_CRITICAL = re.compile(
    r"(?<![a-z0-9])(rce|ddos|ransomware|breach)(?![a-z0-9])",
    re.IGNORECASE,
)
_SHORT_HIGH = re.compile(
    r"(?<![a-z0-9])(exploit|malware|patch|vulnerability|flaw)(?![a-z0-9])",
    re.IGNORECASE,
)


def _keyword_hit(text: str, keywords: list[str], short_re: re.Pattern | None) -> bool:
    for kw in keywords:
        kl = kw.lower().strip()
        if not kl:
            continue
        # Multi-word / long / hyphenated prefixes: substring is fine
        if " " in kl or len(kl) > 6 or kl.endswith("-"):
            if kl in text:
                return True
            continue
        # Short tokens: require boundary via dedicated regex or explicit check
        if short_re and kl in {
            "rce",
            "ddos",
            "ransomware",
            "breach",
            "exploit",
            "malware",
            "patch",
            "vulnerability",
            "flaw",
        }:
            continue  # handled by short_re
        if re.search(rf"(?<![a-z0-9]){re.escape(kl)}(?![a-z0-9])", text):
            return True
    if short_re and short_re.search(text):
        return True
    return False


def score_severity(
    title: str,
    summary: str,
    *,
    source: str = "",
    category: str = "cyber",
) -> str:
    """Score Critical / High / Normal with smarter heuristics than pure substrings."""
    cfg = get_config()
    text = f"{title} {summary}".lower()
    cves = extract_cve_ids(f"{title} {summary}")

    # PSIRT / CISA KEV are high-signal
    if category in ("cisco", "fortinet"):
        return "Critical" if cves or "advisory" in text else "High"
    if "cisa" in source.lower() and (cves or "known exploited" in text):
        return "Critical"

    if cves:
        if any(
            k in text
            for k in (
                "critical",
                "actively exploited",
                "zero-day",
                "0-day",
                "remote code",
                "known exploited",
            )
        ) or _SHORT_CRITICAL.search(text):
            return "Critical"
        return "High"

    if _keyword_hit(text, cfg.get("critical_keywords", []), _SHORT_CRITICAL):
        return "Critical"
    if _keyword_hit(text, cfg.get("high_keywords", []), _SHORT_HIGH):
        return "High"
    return "Normal"


def cluster(arts: list[dict], threshold: float = 0.75) -> list[dict]:
    """Fuzzy title clustering; O(n²) but n is small (tens of articles)."""
    out: list[dict] = []
    norms: list[str] = []
    for a in arts:
        norm = re.sub(r"[^a-z0-9]", "", a["title"].lower())
        found = False
        for i, bnorm in enumerate(norms):
            if SequenceMatcher(None, norm, bnorm).ratio() > threshold:
                out[i].setdefault("other_sources", set()).add(a["source"])
                sev_rank = {"Critical": 0, "High": 1, "Normal": 2}
                if sev_rank.get(a["severity"], 3) < sev_rank.get(out[i]["severity"], 3):
                    out[i]["severity"] = a["severity"]
                found = True
                break
        if not found:
            item = dict(a)
            item.setdefault("other_sources", set())
            out.append(item)
            norms.append(norm)
    return out
