"""RSS / JSON feed definitions, fetch, and parse."""

from __future__ import annotations

import json
import re
import socket
import time
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import feedparser

from cyberdigest.config import get_config
from cyberdigest.db import update_health
from cyberdigest.enrich import USER_AGENT
from cyberdigest.logging_setup import log
from cyberdigest.paths import FEEDS_FILE
from cyberdigest.scoring import score_severity
from cyberdigest.textutil import safe_http_url, strip_html, truncate

FETCH_TIMEOUT = 15
socket.setdefaulttimeout(FETCH_TIMEOUT)

FEED_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/rss+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.7",
}

# Default feed catalog — can be overridden by feeds.yaml
DEFAULT_CYBER_FEEDS: list[tuple[str, str, str]] = [
    ("The Hacker News", "https://feeds.feedburner.com/TheHackersNews", "#e74c3c"),
    ("SecurityWeek", "https://www.securityweek.com/feed/", "#c0392b"),
    ("BleepingComputer", "https://www.bleepingcomputer.com/feed/", "#e74c3c"),
    ("Krebs on Security", "https://krebsonsecurity.com/feed/", "#2c3e50"),
    ("Schneier on Security", "https://www.schneier.com/feed/atom/", "#3498db"),
    ("Cisco Talos", "https://blog.talosintelligence.com/rss/", "#049fd4"),
    ("Cisco Security", "https://feedpress.me/ciscosecurity", "#049fd4"),
    ("Palo Alto Unit 42", "https://feeds.feedburner.com/Unit42", "#fa4616"),
    ("Sophos Threat Research", "https://news.sophos.com/en-us/category/threat-research/feed/", "#9b59b6"),
    ("CISA Advisories", "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json", "#27ae60"),
    ("Fortinet Blog", "https://feeds.feedburner.com/fortinetblog", "#ee3124"),
    ("Microsoft Security", "https://www.microsoft.com/security/blog/feed/", "#0078d4"),
    ("Google Online Security Blog", "https://security.googleblog.com/feeds/posts/default?alt=rss", "#4285f4"),
    ("WeLiveSecurity (ESET)", "https://feeds.feedburner.com/eset/blog", "#16a085"),
    ("Graham Cluley", "https://grahamcluley.com/feed/", "#e67e22"),
    ("Cloudflare Security", "https://blog.cloudflare.com/tag/security/rss", "#f38020"),
    ("Dark Reading", "https://www.darkreading.com/rss.xml", "#8b0000"),
]

DEFAULT_NETWORK_FEEDS: list[tuple[str, str, str]] = [
    ("Network World", "https://www.networkworld.com/feed/", "#0ea5e9"),
    ("Packet Pushers", "https://feeds.packetpushers.net/packetpushersfullfeed/", "#6366f1"),
    ("Cisco Blogs", "https://blogs.cisco.com/developer/feed", "#049fd4"),
    ("AWS Networking", "https://aws.amazon.com/blogs/networking-and-content-delivery/feed/", "#ff9900"),
    ("The New Stack", "https://thenewstack.io/feed/", "#0077c8"),
]

DEFAULT_CISCO_PSIRT_FEEDS: list[tuple[str, str, str]] = [
    ("Cisco PSIRT", "https://sec.cloudapps.cisco.com/security/center/psirtrss20/CiscoSecurityAdvisory.xml", "#049fd4"),
]

DEFAULT_FORTINET_PSIRT_FEEDS: list[tuple[str, str, str]] = [
    ("Fortinet PSIRT", "https://www.fortiguard.com/rss/ir.xml", "#ee3124"),
]

def _load_feeds_document(text: str) -> dict[str, Any]:
    """Load feeds.yaml as JSON or simple YAML (no PyYAML required)."""
    text = text.strip()
    if not text:
        return {}
    if text.startswith("{"):
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("feeds document root must be an object")
        return data
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text) or {}
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return _parse_simple_feeds_yaml(text)

def _parse_simple_feeds_yaml(text: str) -> dict[str, Any]:
    """
    Minimal YAML subset for feeds.yaml:
      section:
        - name: X
          url: Y
          color: Z
    """
    data: dict[str, Any] = {}
    section: str | None = None
    current: dict[str, str] | None = None

    for raw_line in text.splitlines():
        # Full-line comments only — do not strip "#rrggbb" color values
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        line = raw_line.rstrip()
        if not line.strip():
            continue
        # section header (no leading space, ends with :)
        if re.match(r"^[A-Za-z_][\w]*:\s*$", line):
            if current is not None and section:
                data.setdefault(section, []).append(current)
                current = None
            section = line.strip().rstrip(":")
            data.setdefault(section, [])
            continue
        if section is None:
            continue
        m_item = re.match(r"^\s*-\s+name:\s*(.+)$", line)
        if m_item:
            if current is not None:
                data[section].append(current)
            current = {"name": m_item.group(1).strip().strip("\"'")}
            continue
        m_kv = re.match(r"^\s+(url|color):\s*(.+)$", line)
        if m_kv and current is not None:
            current[m_kv.group(1)] = m_kv.group(2).strip().strip("\"'")
    if current is not None and section:
        data.setdefault(section, []).append(current)
    return data

def _parse_feed_list(raw: list | None, default: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    # None → defaults; explicit empty list → no feeds for that category
    if raw is None:
        return list(default)
    if not isinstance(raw, list):
        return list(default)
    if len(raw) == 0:
        return []
    out: list[tuple[str, str, str]] = []
    for item in raw:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            name, url = str(item[0]), str(item[1])
            color = str(item[2]) if len(item) > 2 else "#3b82f6"
            out.append((name, url, color))
        elif isinstance(item, dict) and item.get("name") and item.get("url"):
            out.append(
                (
                    str(item["name"]),
                    str(item["url"]),
                    str(item.get("color") or "#3b82f6"),
                )
            )
    return out if out else list(default)

def load_feeds() -> dict[str, list[tuple[str, str, str]]]:
    """Load feeds from feeds.yaml if present, else defaults."""
    cyber, network, cisco, fortinet = (
        list(DEFAULT_CYBER_FEEDS),
        list(DEFAULT_NETWORK_FEEDS),
        list(DEFAULT_CISCO_PSIRT_FEEDS),
        list(DEFAULT_FORTINET_PSIRT_FEEDS),
    )
    if FEEDS_FILE.exists():
        try:
            text = FEEDS_FILE.read_text(encoding="utf-8")
            data = _load_feeds_document(text)
            if isinstance(data, dict):
                cyber = _parse_feed_list(data.get("cyber") or data.get("cybersecurity"), cyber)
                network = _parse_feed_list(data.get("network") or data.get("networking"), network)
                cisco = _parse_feed_list(data.get("cisco") or data.get("cisco_psirt"), cisco)
                fortinet = _parse_feed_list(data.get("fortinet") or data.get("fortinet_psirt"), fortinet)
                log.info("Loaded custom feeds from feeds.yaml")
        except Exception as exc:
            log.warning("Could not load feeds.yaml (%s) — using defaults", exc)

    return {
        "cyber": cyber,
        "network": network,
        "cisco": cisco,
        "fortinet": fortinet,
    }

def all_feeds() -> list[tuple[str, str, str]]:
    f = load_feeds()
    return f["cyber"] + f["network"] + f["cisco"] + f["fortinet"]

@dataclass
class _ParsedFeed:
    entries: list[dict]
    bozo: bool = False

def _download_feed(url: str) -> bytes:
    req = urllib.request.Request(url, headers=FEED_HEADERS)
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
        return resp.read()

def _xml_text(node: ET.Element, tag: str) -> str:
    found = node.find(tag)
    if found is None:
        return ""
    return "".join(found.itertext()).strip()

def _regex_tag_text(block: str, tag: str) -> str:
    match = re.search(
        rf"<{tag}\b[^>]*>(.*?)</{tag}>", block, flags=re.IGNORECASE | re.DOTALL
    )
    if not match:
        return ""
    text = re.sub(r"^\s*<!\[CDATA\[|\]\]>\s*$", "", match.group(1).strip())
    return strip_html(text)

def _parse_rss_fallback(raw: bytes) -> _ParsedFeed:
    text = raw.decode("utf-8", "replace")
    entries: list[dict] = []
    try:
        root = ET.fromstring(text)
        for item in root.findall(".//item"):
            title = _xml_text(item, "title")
            link = _xml_text(item, "link") or _xml_text(item, "guid")
            summary = _xml_text(item, "description")
            pub = _xml_text(item, "pubDate") or _xml_text(item, "{*}date")
            if title or link:
                entries.append(
                    {"title": title, "link": link, "summary": summary, "published": pub}
                )
    except ET.ParseError:
        for block in re.findall(
            r"<item\b[^>]*>(.*?)</item>", text, flags=re.IGNORECASE | re.DOTALL
        ):
            title = _regex_tag_text(block, "title")
            link = _regex_tag_text(block, "link") or _regex_tag_text(block, "guid")
            summary = _regex_tag_text(block, "description")
            pub = _regex_tag_text(block, "pubDate")
            if title or link:
                entries.append(
                    {"title": title, "link": link, "summary": summary, "published": pub}
                )
    return _ParsedFeed(entries)

def _parse_cisa_kev_json(raw: bytes) -> _ParsedFeed:
    data = json.loads(raw.decode("utf-8", "replace"))
    entries: list[dict] = []
    for vuln in data.get("vulnerabilities", []):
        cve = str(vuln.get("cveID") or "").strip()
        name = str(vuln.get("vulnerabilityName") or "").strip()
        vendor = str(vuln.get("vendorProject") or "").strip()
        product = str(vuln.get("product") or "").strip()
        date_added = str(vuln.get("dateAdded") or "").strip()
        notes = str(vuln.get("notes") or "").strip()
        link_match = re.search(r"https?://\S+", notes)
        link = (
            link_match.group(0).rstrip(" ;,")
            if link_match
            else f"https://nvd.nist.gov/vuln/detail/{cve}"
        )
        title = (
            f"{cve}: {name}"
            if cve and name
            else (name or cve or "CISA Known Exploited Vulnerability")
        )
        summary_parts = [
            "Known exploited vulnerability listed by CISA.",
            f"Affected: {vendor} {product}.".strip(),
            str(vuln.get("shortDescription") or "").strip(),
            f"Required action due: {vuln.get('dueDate')}." if vuln.get("dueDate") else "",
        ]
        summary = " ".join(part for part in summary_parts if part)
        item: dict[str, Any] = {
            "title": title,
            "link": link,
            "summary": summary,
            "published": date_added,
        }
        try:
            item["published_parsed"] = datetime.strptime(date_added, "%Y-%m-%d").timetuple()
        except ValueError:
            pass
        entries.append(item)
    return _ParsedFeed(entries)

def _fetch_attempt(name: str, url: str) -> Any:

    raw: bytes | None = None
    try:
        raw = _download_feed(url)
        is_json_feed = (
            url.lower().endswith(".json")
            or "known_exploited_vulnerabilities" in url
        )
        if is_json_feed:
            parsed_json = _parse_cisa_kev_json(raw)
            if parsed_json.entries:
                return parsed_json
        p = feedparser.parse(raw)
    except Exception as download_exc:
        log.debug("Direct feed download failed for %s: %s", name, download_exc)
        p = feedparser.parse(url, agent=USER_AGENT)
    if not getattr(p, "entries", None):
        if raw:
            fallback = _parse_rss_fallback(raw)
            if fallback.entries:
                log.info(
                    "Recovered %d entries from malformed feed: %s",
                    len(fallback.entries),
                    name,
                )
                return fallback
        if getattr(p, "bozo", False):
            raise ValueError(f"Feed parse error: {getattr(p, 'bozo_exception', 'unknown')}")
        return []
    if getattr(p, "bozo", False) and raw:
        fallback = _parse_rss_fallback(raw)
        if len(fallback.entries) > len(p.entries):
            log.info(
                "Recovered %d entries from malformed feed: %s",
                len(fallback.entries),
                name,
            )
            return fallback
    return p

def _fetch_with_retry(name: str, url: str) -> Any:
    delays = [2, 5, 10]
    last_exc: Exception | None = None
    for attempt, delay in enumerate(delays, 1):
        try:

            return _fetch_attempt(name, url)

        except Exception as exc:
            last_exc = exc
            log.debug("Feed %s attempt %d/%d failed: %s", name, attempt, len(delays), exc)
            if attempt < len(delays):
                time.sleep(delay)
    raise last_exc or RuntimeError("Feed fetch failed")

def fetch_feed(
    name: str,
    url: str,
    color: str,
    seen: set[str],
    category: str = "cyber",
    max_arts: int | None = None,
) -> list[dict]:
    try:
        parsed = _fetch_with_retry(name, url)
        arts: list[dict] = []
        if not parsed:
            update_health(name, True)
            return arts
        cfg = get_config()
        cap = max_arts if max_arts is not None else cfg["max_articles_per_feed"]
        for entry in parsed.entries[:cap]:
            link = safe_http_url((entry.get("link") or "").strip(), fallback="")
            if not link or link in seen:
                continue
            title = strip_html(entry.get("title") or "Untitled")
            summary = truncate(
                strip_html(entry.get("summary") or entry.get("description") or "")
            )
            pub = strip_html(entry.get("published") or entry.get("updated") or "")
            pt = entry.get("published_parsed") or entry.get("updated_parsed")
            try:
                ts = time.mktime(pt) if pt else time.time()
            except Exception:
                ts = time.time()
            arts.append(
                {
                    "title": title,
                    "link": link,
                    "summary": summary,
                    "published": pub,
                    "timestamp": ts,
                    "color": color,
                    "source": name,
                    "severity": score_severity(
                        title, summary, source=name, category=category
                    ),
                    "category": category,
                    "other_sources": set(),
                }
            )
        update_health(name, True)
        log.debug("Fetched %d articles from %s", len(arts), name)
        return arts
    except Exception as exc:
        log.warning("Feed failed — %s: %s", name, exc)
        update_health(name, False)
        return []
