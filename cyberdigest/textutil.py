"""HTML/text helpers and safe URL handling."""

from __future__ import annotations

import re
from html import escape, unescape
from urllib.parse import urlparse

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_CVE_RE = re.compile(r"(CVE-\d{4}-\d{4,7})", re.IGNORECASE)


def strip_html(text: str | None) -> str:
    if not text:
        return ""
    return _WS_RE.sub(" ", unescape(_TAG_RE.sub(" ", text))).strip()


def truncate(text: str, n: int = 260) -> str:
    if len(text) <= n:
        return text
    return (text[:n].rsplit(" ", 1)[0] or text[:n]) + "…"


def h(text: str) -> str:
    """Escape text for safe HTML embedding."""
    return escape(str(text), quote=True)


def reading_time(text: str) -> str:
    return f"{max(1, round(len(text.split()) / 200))} min read"


def safe_http_url(url: str | None, fallback: str = "#") -> str:
    """Allow only http(s) URLs; block javascript:/data:/etc."""
    if not url:
        return fallback
    url = str(url).strip()
    try:
        parsed = urlparse(url)
    except Exception:
        return fallback
    if parsed.scheme.lower() not in ("http", "https"):
        return fallback
    if not parsed.netloc:
        return fallback
    return url


def extract_cve_ids(text: str) -> list[str]:
    if not text:
        return []
    found = _CVE_RE.findall(text)
    # Normalize to uppercase unique preserving order
    seen: set[str] = set()
    out: list[str] = []
    for c in found:
        u = c.upper()
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out
