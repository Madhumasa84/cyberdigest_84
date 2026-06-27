#!/usr/bin/env python3
"""
CyberDigest — Production Edition
==================================
Self-healing, reboot-proof cybersecurity news agent.
Single-file. Zero external config needed. Desktop & server ready.

Features:
  - OS-native scheduling (cron / schtasks / launchd) + fallback loop
  - Rotating logs (5 MB × 3), lock file, SIGTERM graceful shutdown
  - SQLite with atomic writes, 30-day pruning, CVE CVSS enrichment
  - Concurrent feed fetching, fuzzy cross-source deduplication
  - Internet outage detection + per-feed retry/backoff
  - Optional email delivery (SMTP), NVD API key support
  - Headless / server detection (no browser pop-up on servers)
  - --healthcheck, --uninstall, --force CLI flags
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import logging
import logging.handlers
import os
import platform
import re
import shutil
import signal
import smtplib
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.request
import webbrowser
from datetime import datetime, timedelta
from difflib import SequenceMatcher

try:
    import fcntl  # Unix only
except ImportError:
    fcntl = None  # Windows handles locking differently

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import unescape
from pathlib import Path
from typing import Any
import threading

import feedparser
import schedule

try:
    from plyer import notification as _plyer_notification  # type: ignore
    _HAS_PLYER = True
except Exception:
    _HAS_PLYER = False

try:
    from PIL import Image, ImageDraw
    import pystray
    from pystray import MenuItem as item
    _HAS_GUI = True
except Exception:
    _HAS_GUI = False


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR       = Path(__file__).resolve().parent
REPORTS_DIR    = BASE_DIR / "reports"
DB_FILE        = BASE_DIR / "state.db"
LOG_FILE       = BASE_DIR / "agent_log.txt"
STATUS_FILE    = BASE_DIR / "status.txt"
HEARTBEAT_FILE = BASE_DIR / "heartbeat.txt"
CONFIG_FILE    = BASE_DIR / "config.json"
LOCK_FILE      = BASE_DIR / "agent.lock"

# ---------------------------------------------------------------------------
# Feed list  (name, rss-url, brand-color)
# ---------------------------------------------------------------------------
FEEDS: list[tuple[str, str, str]] = [
    ("The Hacker News",        "https://feeds.feedburner.com/TheHackersNews",           "#e74c3c"),
    ("Krebs on Security",      "https://krebsonsecurity.com/feed/",                     "#2c3e50"),
    ("Schneier on Security",   "https://www.schneier.com/feed/atom/",                   "#3498db"),
    ("CISA Advisories",        "https://www.cisa.gov/cybersecurity-advisories/all.xml", "#27ae60"),
    ("Sophos Threat Research", "https://news.sophos.com/en-us/category/threat-research/feed/", "#9b59b6"),
    ("Microsoft Security",     "https://www.microsoft.com/security/blog/feed/",         "#0078d4"),
    ("Cloudflare Security",    "https://blog.cloudflare.com/tag/security/rss",          "#f38020"),
    ("WeLiveSecurity (ESET)",  "https://feeds.feedburner.com/eset/blog",                "#16a085"),
    ("Graham Cluley",          "https://grahamcluley.com/feed/",                        "#e67e22"),
]

USER_AGENT    = "CyberDigest/4.0 (+https://github.com/cyberdigest)"
FETCH_TIMEOUT = 15

socket.setdefaulttimeout(FETCH_TIMEOUT)

# ---------------------------------------------------------------------------
# Rotating logger  (5 MB × 3 files — never fills your disk)
# ---------------------------------------------------------------------------
def _setup_logging(level: str = "INFO") -> logging.Logger:
    fmt     = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
    handler = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(fmt)
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    console.setLevel(logging.WARNING)      # Only warnings+ to stdout
    log = logging.getLogger("cyberdigest")
    log.setLevel(getattr(logging, level.upper(), logging.INFO))
    log.addHandler(handler)
    log.addHandler(console)
    return log

_log = _setup_logging()


# ---------------------------------------------------------------------------
# Configuration  (auto-created, validated, merged with defaults)
# ---------------------------------------------------------------------------
DEFAULT_CONFIG: dict = {
    "interval_days":         3,
    "max_archived_reports":  30,
    "max_articles_per_feed": 8,
    "log_level":             "INFO",
    "critical_keywords":     ["cve-", "zero-day", "0-day", "actively exploited",
                              "rce", "ransomware", "breach", "critical vulnerability"],
    "high_keywords":         ["vulnerability", "flaw", "patch", "exploit", "malware"],

    # ── Email (optional) ─────────────────────────────────────────────────
    # Fill in to receive the digest by email every run.
    "email": {
        "enabled":  False,
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "username":  "",
        "password":  "",        # use an App Password for Gmail
        "from_addr": "",
        "to_addrs":  []         # list of recipient addresses
    },

    # ── NVD API key (optional but recommended for heavy use) ──────────────
    # Get a free key at: https://nvd.nist.gov/developers/request-an-api-key
    "nvd_api_key": ""
}

_CONFIG_REQUIRED_TYPES: dict[str, type] = {
    "interval_days":         int,
    "max_archived_reports":  int,
    "max_articles_per_feed": int,
    "log_level":             str,
}

def _validate_config(cfg: dict) -> list[str]:
    errors: list[str] = []
    for key, expected in _CONFIG_REQUIRED_TYPES.items():
        val = cfg.get(key)
        if not isinstance(val, expected):
            errors.append(f"config.json: '{key}' must be {expected.__name__}, got {type(val).__name__}")
    if cfg.get("interval_days", 1) < 1:
        errors.append("config.json: 'interval_days' must be >= 1")
    em = cfg.get("email", {})
    if em.get("enabled"):
        for f in ("smtp_host", "username", "password", "from_addr"):
            if not em.get(f):
                errors.append(f"config.json: email.{f} is required when email.enabled=true")
        if not em.get("to_addrs"):
            errors.append("config.json: email.to_addrs must have at least one address")
    return errors

def load_config() -> dict:
    if not CONFIG_FILE.exists():
        try:
            CONFIG_FILE.write_text(json.dumps(DEFAULT_CONFIG, indent=4), encoding="utf-8")
            _log.info("Created default config.json")
        except Exception as exc:
            _log.warning("Could not write config.json: %s", exc)
        return dict(DEFAULT_CONFIG)
    try:
        raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        # Deep-merge defaults
        merged: dict = dict(DEFAULT_CONFIG)
        merged.update(raw)
        merged["email"] = {**DEFAULT_CONFIG["email"], **raw.get("email", {})}
        errors = _validate_config(merged)
        if errors:
            for e in errors:
                _log.error("Config error: %s", e)
            print("\n".join(f"[CONFIG ERROR] {e}" for e in errors))
            sys.exit(1)
        # Re-apply log level from config
        _log.setLevel(getattr(logging, merged.get("log_level", "INFO").upper(), logging.INFO))
        return merged
    except json.JSONDecodeError as exc:
        _log.error("config.json is not valid JSON: %s", exc)
        print(f"[CONFIG ERROR] config.json is not valid JSON: {exc}")
        sys.exit(1)

CONFIG = load_config()


# ---------------------------------------------------------------------------
# Lock file — prevent two instances running simultaneously
# ---------------------------------------------------------------------------
_LOCK_FD: Any = None

def acquire_lock() -> bool:
    """Return True if lock acquired, False if another instance is running."""
    global _LOCK_FD
    if platform.system() == "Windows":
        # Windows: use a simple PID file approach
        if LOCK_FILE.exists():
            try:
                pid = int(LOCK_FILE.read_text().strip())
                # Check if PID is still alive
                import ctypes
                handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # type: ignore
                if handle:
                    ctypes.windll.kernel32.CloseHandle(handle)  # type: ignore
                    return False  # Still running
            except Exception:
                pass            # Stale lock — continue
        LOCK_FILE.write_text(str(os.getpid()))
        return True
    else:
        try:
            _LOCK_FD = open(LOCK_FILE, "w")
            fcntl.flock(_LOCK_FD, fcntl.LOCK_EX | fcntl.LOCK_NB)
            _LOCK_FD.write(str(os.getpid()))
            _LOCK_FD.flush()
            return True
        except (IOError, OSError):
            return False

def release_lock():
    global _LOCK_FD
    try:
        if platform.system() != "Windows" and _LOCK_FD:
            fcntl.flock(_LOCK_FD, fcntl.LOCK_UN)
            _LOCK_FD.close()
        LOCK_FILE.unlink(missing_ok=True)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Graceful shutdown (SIGTERM / SIGINT)
# ---------------------------------------------------------------------------
_SHUTDOWN = False

def _handle_signal(sig, frame):
    global _SHUTDOWN
    _SHUTDOWN = True
    _log.info("Shutdown signal received (%s). Finishing gracefully…", sig)
    release_lock()
    sys.exit(0)

signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT,  _handle_signal)


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")     # Better concurrent access
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn

def init_db():
    with get_db() as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS articles (
                url        TEXT PRIMARY KEY,
                title      TEXT,
                source     TEXT,
                first_seen TEXT
            );
            CREATE TABLE IF NOT EXISTS feed_health (
                source               TEXT PRIMARY KEY,
                consecutive_failures INTEGER DEFAULT 0,
                last_checked         TEXT
            );
            CREATE TABLE IF NOT EXISTS agent_state (
                key   TEXT PRIMARY KEY,
                value TEXT
            );
            CREATE TABLE IF NOT EXISTS cve_cache (
                cve_id   TEXT PRIMARY KEY,
                score    TEXT,
                severity TEXT,
                cached_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_articles_seen ON articles(first_seen);
        """)
        # Prune old data
        c.execute("DELETE FROM articles  WHERE first_seen  < date('now', '-30 days')")
        c.execute("DELETE FROM cve_cache WHERE cached_at   < date('now', '-7 days')")

def get_last_run() -> datetime | None:
    with get_db() as c:
        row = c.execute("SELECT value FROM agent_state WHERE key='last_run'").fetchone()
        if row:
            try:
                return datetime.fromisoformat(row["value"])
            except ValueError:
                pass
    return None

def set_last_run(dt: datetime):
    with get_db() as c:
        c.execute("INSERT OR REPLACE INTO agent_state(key,value) VALUES('last_run',?)", (dt.isoformat(),))

def load_seen() -> set[str]:
    with get_db() as c:
        return {r["url"] for r in c.execute(
            "SELECT url FROM articles WHERE first_seen >= date('now', '-30 days')"
        ).fetchall()}

def save_articles(arts: list[dict]):
    now = datetime.now().isoformat()
    with get_db() as c:
        c.executemany(
            "INSERT OR IGNORE INTO articles(url,title,source,first_seen) VALUES(?,?,?,?)",
            [(a["link"], a["title"], a["source"], now) for a in arts],
        )

def update_health(source: str, ok: bool):
    now = datetime.now().isoformat()
    with get_db() as c:
        if ok:
            c.execute(
                "INSERT OR REPLACE INTO feed_health(source,consecutive_failures,last_checked) VALUES(?,0,?)",
                (source, now),
            )
        else:
            c.execute("""
                INSERT INTO feed_health(source,consecutive_failures,last_checked) VALUES(?,1,?)
                ON CONFLICT(source) DO UPDATE
                SET consecutive_failures=consecutive_failures+1, last_checked=excluded.last_checked
            """, (source, now))

def get_health() -> dict[str, int]:
    with get_db() as c:
        return {r["source"]: r["consecutive_failures"]
                for r in c.execute("SELECT source,consecutive_failures FROM feed_health").fetchall()}


# ---------------------------------------------------------------------------
# Network helpers
# ---------------------------------------------------------------------------
def check_internet() -> bool:
    for host in ["8.8.8.8", "1.1.1.1"]:
        try:
            socket.create_connection((host, 53), timeout=3)
            return True
        except OSError:
            pass
    return False

def is_headless() -> bool:
    """Detect if running on a server/headless environment."""
    if platform.system() == "Windows":
        return False
    if platform.system() == "Darwin":
        return False
    # Linux: check for display server
    return not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))

def fetch_cve_score(cve_id: str) -> tuple[str, str] | None:
    with get_db() as c:
        row = c.execute("SELECT score,severity FROM cve_cache WHERE cve_id=?", (cve_id,)).fetchone()
        if row:
            return row["score"], row["severity"]
    try:
        headers = {"User-Agent": USER_AGENT}
        api_key = CONFIG.get("nvd_api_key", "")
        if api_key:
            headers["apiKey"] = api_key
        req = urllib.request.Request(
            f"https://services.nvd.nist.gov/rest/json/cves/2.0?cveId={cve_id}",
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read().decode())
        metrics = data.get("vulnerabilities", [{}])[0].get("cve", {}).get("metrics", {})
        for ver in ["cvssMetricV31", "cvssMetricV30", "cvssMetricV2"]:
            if ver in metrics:
                score = str(metrics[ver][0]["cvssData"]["baseScore"])
                sev   = (metrics[ver][0].get("baseSeverity")
                         or metrics[ver][0]["cvssData"].get("baseSeverity", "UNKNOWN"))
                now = datetime.now().isoformat()
                with get_db() as c:
                    c.execute(
                        "INSERT OR REPLACE INTO cve_cache(cve_id,score,severity,cached_at) VALUES(?,?,?,?)",
                        (cve_id, score, sev, now),
                    )
                # Polite delay — shorter with API key
                time.sleep(0.2 if api_key else 0.6)
                return score, sev
    except Exception as exc:
        _log.debug("CVE lookup failed for %s: %s", cve_id, exc)
    return None


# ---------------------------------------------------------------------------
# Email delivery
# ---------------------------------------------------------------------------
def send_email(html_content: str, report_date: str, n_articles: int, n_crit: int):
    em = CONFIG.get("email", {})
    if not em.get("enabled"):
        return
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"CyberDigest — {report_date} ({n_articles} articles, {n_crit} critical)"
        msg["From"]    = em["from_addr"]
        msg["To"]      = ", ".join(em["to_addrs"])
        msg.attach(MIMEText(html_content, "html", "utf-8"))

        with smtplib.SMTP(em["smtp_host"], em["smtp_port"], timeout=20) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(em["username"], em["password"])
            smtp.sendmail(em["from_addr"], em["to_addrs"], msg.as_string())

        _log.info("Email sent to: %s", em["to_addrs"])
    except Exception as exc:
        _log.error("Email delivery failed: %s", exc)


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE  = re.compile(r"\s+")

def strip_html(text: str | None) -> str:
    if not text:
        return ""
    return _WS_RE.sub(" ", unescape(_TAG_RE.sub(" ", text))).strip()

def truncate(text: str, n: int = 260) -> str:
    if len(text) <= n:
        return text
    return (text[:n].rsplit(" ", 1)[0] or text[:n]) + "…"

def h(text: str) -> str:
    return (text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;"))

def reading_time(text: str) -> str:
    return f"{max(1, round(len(text.split()) / 200))} min read"

def enrich_cve(text: str) -> str:
    text = h(text)
    def _repl(m: re.Match) -> str:
        cid  = m.group(1)
        link = (f'<a href="https://nvd.nist.gov/vuln/detail/{cid}" '
                f'target="_blank" rel="noopener noreferrer" style="color:#38bdf8;text-decoration:none">'
                f"{cid}</a>")
        info = fetch_cve_score(cid)
        if info:
            score, sev = info
            col = ("#ef4444" if sev.upper() in ("HIGH", "CRITICAL")
                   else "#f59e0b" if sev.upper() == "MEDIUM" else "#3b82f6")
            link += (f' <span style="background:{col};color:#fff;padding:1px 6px;'
                     f'border-radius:4px;font-size:10px;font-weight:700;vertical-align:middle">'
                     f"CVSS {score}</span>")
        return link
    return re.sub(r"(CVE-\d{4}-\d{4,7})", _repl, text, flags=re.IGNORECASE)


# ---------------------------------------------------------------------------
# Severity scoring
# ---------------------------------------------------------------------------
def score_severity(title: str, summary: str) -> str:
    text = (title + " " + summary).lower()
    if any(k in text for k in CONFIG["critical_keywords"]):
        return "Critical"
    if any(k in text for k in CONFIG["high_keywords"]):
        return "High"
    return "Normal"


# ---------------------------------------------------------------------------
# Feed fetching
# ---------------------------------------------------------------------------
def _fetch_with_retry(name: str, url: str) -> Any:
    delays = [2, 5, 10]
    last_exc: Exception | None = None
    for attempt, delay in enumerate(delays, 1):
        try:
            p = feedparser.parse(url, agent=USER_AGENT)
            if not getattr(p, "entries", None):
                if getattr(p, "bozo", False):
                    raise ValueError(f"Feed parse error: {p.bozo_exception}")
                return []
            return p
        except Exception as exc:
            last_exc = exc
            _log.debug("Feed %s attempt %d/%d failed: %s", name, attempt, len(delays), exc)
            if attempt < len(delays):
                time.sleep(delay)
    raise last_exc or RuntimeError("Feed fetch failed")

def fetch_feed(name: str, url: str, color: str, seen: set[str]) -> list[dict]:
    try:
        parsed = _fetch_with_retry(name, url)
        arts: list[dict] = []
        if not parsed:
            update_health(name, True)
            return arts
        for entry in parsed.entries[:CONFIG["max_articles_per_feed"]]:
            link = (entry.get("link") or "").strip()
            if not link or link in seen:
                continue
            title   = strip_html(entry.get("title") or "Untitled")
            summary = truncate(strip_html(entry.get("summary") or entry.get("description") or ""))
            pub     = strip_html(entry.get("published") or entry.get("updated") or "")
            pt      = entry.get("published_parsed") or entry.get("updated_parsed")
            try:
                ts = time.mktime(pt) if pt else time.time()
            except Exception:
                ts = time.time()
            arts.append({
                "title": title, "link": link, "summary": summary,
                "published": pub, "timestamp": ts, "color": color,
                "source": name, "severity": score_severity(title, summary),
                "other_sources": set(),
            })
        update_health(name, True)
        _log.debug("Fetched %d articles from %s", len(arts), name)
        return arts
    except Exception as exc:
        _log.warning("Feed failed — %s: %s", name, exc)
        update_health(name, False)
        return []

def cluster(arts: list[dict]) -> list[dict]:
    out: list[dict] = []
    for a in arts:
        norm  = re.sub(r"[^a-z0-9]", "", a["title"].lower())
        found = False
        for b in out:
            if SequenceMatcher(None, norm, re.sub(r"[^a-z0-9]", "", b["title"].lower())).ratio() > 0.75:
                b["other_sources"].add(a["source"])
                found = True
                break
        if not found:
            out.append(a)
    return out


# ---------------------------------------------------------------------------
# CSS (stored as plain string — avoids triple-quote f-string conflicts)
# ---------------------------------------------------------------------------
_CSS = (
    "@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800"
    "&family=JetBrains+Mono:wght@400;500&display=swap');"
    ":root{"
    "--bg:#060b14;--bg2:#0d1628;--card:rgba(255,255,255,.03);--card-h:rgba(255,255,255,.06);"
    "--border:rgba(255,255,255,.07);--bh:rgba(99,179,237,.35);"
    "--t1:#e8edf5;--t2:#7a8899;--tm:#4a5568;"
    "--cyan:#22d3ee;--purple:#a78bfa;--green:#10b981;--red:#ef4444;--amber:#f59e0b;--blue:#3b82f6;"
    "--rlg:16px;--rmd:10px;}"
    "*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}"
    "body{font-family:'Inter',-apple-system,BlinkMacSystemFont,sans-serif;"
    "background:var(--bg);"
    "background-image:radial-gradient(ellipse 80% 50% at 50% -20%,rgba(34,211,238,.08) 0%,transparent 60%),"
    "radial-gradient(ellipse 60% 40% at 80% 100%,rgba(167,139,250,.07) 0%,transparent 60%);"
    "color:var(--t1);min-height:100vh;line-height:1.6;overflow-x:hidden}"
    ".wrap{max-width:1280px;margin:0 auto;padding:40px 24px 80px}"
    ".site-header{display:flex;align-items:center;justify-content:space-between;gap:16px;"
    "margin-bottom:36px;padding:20px 26px;"
    "background:rgba(13,22,40,.7);border:1px solid var(--border);border-radius:var(--rlg);"
    "backdrop-filter:blur(12px);flex-wrap:wrap}"
    ".logo{display:flex;align-items:center;gap:12px}"
    ".logo-icon{width:42px;height:42px;background:linear-gradient(135deg,#22d3ee22,#a78bfa22);"
    "border:1px solid rgba(167,139,250,.3);border-radius:12px;"
    "display:flex;align-items:center;justify-content:center;font-size:21px;flex-shrink:0}"
    ".logo-text h1{font-size:17px;font-weight:700;"
    "background:linear-gradient(90deg,#22d3ee,#a78bfa);-webkit-background-clip:text;"
    "background-clip:text;-webkit-text-fill-color:transparent;color:transparent;letter-spacing:-.3px}"
    ".logo-text .tag{font-size:11px;color:var(--t2);margin-top:2px}"
    ".hdr-right{display:flex;align-items:center;gap:16px;flex-wrap:wrap}"
    ".run-time{font-size:11px;color:var(--tm);font-family:'JetBrains Mono',monospace}"
    ".arch-btn{font-size:12px;color:var(--cyan);text-decoration:none;padding:5px 14px;"
    "border:1px solid rgba(34,211,238,.25);border-radius:999px;transition:all .2s;white-space:nowrap}"
    ".arch-btn:hover{background:rgba(34,211,238,.1);border-color:rgba(34,211,238,.5)}"
    ".stats-bar{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:12px;margin-bottom:24px}"
    ".scard{background:var(--card);border:1px solid var(--border);border-radius:var(--rmd);"
    "padding:14px 18px;text-align:center;transition:border-color .2s}"
    ".scard:hover{border-color:rgba(34,211,238,.2)}"
    ".snum{font-size:26px;font-weight:800;line-height:1;"
    "background:linear-gradient(135deg,#22d3ee,#a78bfa);-webkit-background-clip:text;"
    "background-clip:text;-webkit-text-fill-color:transparent;color:transparent}"
    ".snum.red{background:linear-gradient(135deg,#ef4444,#f87171);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}"
    ".snum.amb{background:linear-gradient(135deg,#f59e0b,#fcd34d);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}"
    ".snum.grn{background:linear-gradient(135deg,#10b981,#6ee7b7);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}"
    ".slbl{font-size:10px;color:var(--tm);text-transform:uppercase;letter-spacing:1px;margin-top:5px}"
    ".controls{display:flex;gap:10px;margin-bottom:20px;flex-wrap:wrap;align-items:center}"
    ".search{flex:1;min-width:180px;background:rgba(255,255,255,.04);border:1px solid var(--border);"
    "border-radius:var(--rmd);padding:9px 14px 9px 38px;color:var(--t1);font-size:13px;font-family:inherit;"
    "outline:none;transition:border-color .2s,box-shadow .2s;"
    "background-image:url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='15' height='15' fill='none' viewBox='0 0 24 24'%3E%3Ccircle cx='11' cy='11' r='8' stroke='%234a5568' stroke-width='2'/%3E%3Cpath d='m21 21-4.35-4.35' stroke='%234a5568' stroke-width='2' stroke-linecap='round'/%3E%3C/svg%3E\");"
    "background-repeat:no-repeat;background-position:12px center}"
    ".search::placeholder{color:var(--tm)}"
    ".search:focus{border-color:rgba(34,211,238,.4);box-shadow:0 0 0 3px rgba(34,211,238,.07)}"
    ".tabs{display:flex;gap:5px;background:rgba(255,255,255,.03);"
    "border:1px solid var(--border);border-radius:var(--rmd);padding:4px}"
    ".tab{padding:5px 13px;border-radius:6px;font-size:11.5px;font-weight:500;cursor:pointer;"
    "border:none;background:transparent;color:var(--t2);transition:all .18s;white-space:nowrap}"
    ".tab:hover{color:var(--t1);background:rgba(255,255,255,.05)}"
    ".tab.on{background:rgba(34,211,238,.15);color:var(--cyan)}"
    ".tab[data-f=Critical].on{background:rgba(239,68,68,.15);color:#f87171}"
    ".tab[data-f=High].on{background:rgba(245,158,11,.15);color:#fcd34d}"
    ".sort{background:rgba(255,255,255,.04);border:1px solid var(--border);border-radius:var(--rmd);"
    "padding:9px 13px;color:var(--t1);font-size:12px;font-family:inherit;outline:none;cursor:pointer}"
    ".sort option{background:#1a2540}"
    ".hp{background:var(--card);border:1px solid var(--border);border-radius:var(--rmd);"
    "padding:10px 16px;margin-bottom:24px;display:flex;flex-wrap:wrap;gap:7px;align-items:center}"
    ".hp-lbl{font-size:10px;color:var(--tm);text-transform:uppercase;letter-spacing:1px;margin-right:4px}"
    ".chip{display:inline-flex;align-items:center;gap:5px;background:rgba(0,0,0,.25);"
    "border-radius:999px;padding:3px 9px 3px 7px;font-size:11px;color:var(--t1);"
    "border:1px solid transparent;transition:border-color .2s}"
    ".chip:hover{border-color:var(--bh)}"
    ".dot{width:7px;height:7px;border-radius:50%;flex-shrink:0}"
    ".dot.ok{background:var(--green);box-shadow:0 0 5px rgba(16,185,129,.5)}"
    ".dot.warn{background:var(--amber);box-shadow:0 0 5px rgba(245,158,11,.5)}"
    ".dot.fail{background:var(--red);box-shadow:0 0 5px rgba(239,68,68,.5);animation:pr 1.5s infinite}"
    "@keyframes pr{0%,100%{box-shadow:0 0 5px rgba(239,68,68,.4)}50%{box-shadow:0 0 11px rgba(239,68,68,.9)}}"
    ".alert{padding:11px 16px;border-radius:var(--rmd);margin-bottom:14px;"
    "font-size:13px;line-height:1.5;display:flex;gap:9px;align-items:flex-start}"
    ".ae{background:rgba(239,68,68,.08);border:1px solid rgba(239,68,68,.25);color:#fca5a5}"
    ".ai{background:rgba(34,211,238,.06);border:1px solid rgba(34,211,238,.2);color:#a5f3fc}"
    ".ai-ico{flex-shrink:0}"
    ".rbar{font-size:11.5px;color:var(--tm);margin-bottom:14px;height:17px}"
    ".grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(350px,1fr));gap:16px}"
    ".card{background:var(--card);border:1px solid var(--border);border-radius:var(--rlg);"
    "padding:18px;display:flex;flex-direction:column;gap:9px;"
    "transition:transform .22s cubic-bezier(.25,.8,.25,1),box-shadow .22s,border-color .22s,background .22s;"
    "animation:fiu .35s both;position:relative;overflow:hidden}"
    ".card::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;"
    "background:transparent;border-radius:var(--rlg) var(--rlg) 0 0}"
    ".card.critical::before{background:linear-gradient(90deg,#ef4444,#f87171)}"
    ".card.high::before{background:linear-gradient(90deg,#f59e0b,#fcd34d)}"
    ".card:hover{transform:translateY(-4px);background:var(--card-h);border-color:var(--bh);"
    "box-shadow:0 16px 40px rgba(0,0,0,.5)}"
    "@keyframes fiu{from{opacity:0;transform:translateY(16px)}to{opacity:1;transform:translateY(0)}}"
    ".ctop{display:flex;justify-content:space-between;align-items:flex-start;gap:7px}"
    ".bdgs{display:flex;gap:5px;flex-wrap:wrap;align-items:center}"
    ".bdg{display:inline-flex;align-items:center;padding:2px 9px;"
    "border-radius:999px;font-size:10px;font-weight:600;text-transform:uppercase;"
    "letter-spacing:.5px;color:#fff;white-space:nowrap}"
    ".bsc{background:rgba(239,68,68,.18);color:#f87171;border:1px solid rgba(239,68,68,.3);"
    "animation:pc 2s infinite}"
    "@keyframes pc{0%,100%{box-shadow:none}50%{box-shadow:0 0 7px rgba(239,68,68,.5)}}"
    ".bsh{background:rgba(245,158,11,.18);color:#fcd34d;border:1px solid rgba(245,158,11,.3)}"
    ".bsn{background:rgba(59,130,246,.14);color:#93c5fd;border:1px solid rgba(59,130,246,.25)}"
    ".rt{font-size:10px;color:var(--tm);white-space:nowrap;flex-shrink:0}"
    ".ctitle{font-size:15px;font-weight:600;line-height:1.45;color:var(--t1);letter-spacing:-.1px}"
    ".ctitle a{color:inherit;text-decoration:none;transition:color .15s}"
    ".ctitle a:hover{color:var(--cyan)}"
    ".csum{font-size:13px;line-height:1.65;color:#8090a8;flex-grow:1}"
    ".csum a{color:#38bdf8;text-decoration:none}"
    ".csum a:hover{text-decoration:underline}"
    ".cfoot{display:flex;justify-content:space-between;align-items:center;gap:7px;"
    "padding-top:9px;border-top:1px solid var(--border);flex-wrap:wrap}"
    ".cdate{font-size:11px;color:var(--tm);font-family:'JetBrains Mono',monospace}"
    ".also{font-size:10.5px;color:#5a6a80;font-style:italic}"
    ".rlink{font-size:11.5px;color:var(--cyan);text-decoration:none;opacity:.8;"
    "transition:opacity .15s;white-space:nowrap;flex-shrink:0}"
    ".rlink:hover{opacity:1}"
    ".empty{grid-column:1/-1;text-align:center;padding:80px 20px;color:var(--t2);font-size:16px}"
    ".empty .ico{font-size:46px;display:block;margin-bottom:14px}"
    ".site-footer{margin-top:56px;text-align:center;padding:18px;"
    "font-size:11.5px;color:var(--tm);border-top:1px solid var(--border)}"
    ".site-footer a{color:var(--t2);text-decoration:none}"
    ".site-footer a:hover{color:var(--cyan)}"
    "@media(max-width:700px){"
    ".wrap{padding:18px 12px 56px}"
    ".site-header{padding:14px}"
    ".grid{grid-template-columns:1fr}"
    ".stats-bar{grid-template-columns:repeat(2,1fr)}"
    ".controls{flex-direction:column;align-items:stretch}"
    ".tabs{overflow-x:auto}}"
)

_IDXCSS = (
    ".rlist{display:flex;flex-direction:column;gap:4px}"
    ".rrow{display:flex;align-items:center;gap:13px;padding:11px 16px;"
    "background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.06);"
    "border-radius:10px;text-decoration:none;color:var(--t1);"
    "transition:background .18s,border-color .18s}"
    ".rrow:hover{background:rgba(34,211,238,.06);border-color:rgba(34,211,238,.25)}"
    ".rico{font-size:17px;flex-shrink:0}"
    ".rname{flex:1;font-size:13.5px;font-weight:500}"
    ".rtime{font-size:11.5px;color:var(--tm);font-family:'JetBrains Mono',monospace}"
)

_JS = (
    "(function(){"
    "var grid=document.getElementById('grid'),"
    "si=document.getElementById('si'),"
    "rb=document.getElementById('rb'),"
    "tabs=document.querySelectorAll('.tab'),"
    "ss=document.getElementById('ss'),"
    "cards=Array.from(grid.querySelectorAll('.card')),"
    "af='All';"
    "function run(){"
    "var q=si.value.toLowerCase().trim(),v=0;"
    "cards.forEach(function(c){"
    "var sev=c.dataset.severity,txt=c.innerText.toLowerCase(),"
    "src=(c.dataset.source||'').toLowerCase(),"
    "ok=(af==='All'||sev===af)&&(!q||txt.includes(q)||src.includes(q));"
    "c.style.display=ok?'':'none';"
    "if(ok)v++;});"
    "rb.textContent=(q||af!=='All')?('Showing '+v+' of '+cards.length+' articles'):'';"
    "}"
    "tabs.forEach(function(b){"
    "b.addEventListener('click',function(){"
    "tabs.forEach(function(x){x.classList.remove('on');});"
    "b.classList.add('on');af=b.dataset.f;run();});});"
    "si.addEventListener('input',run);"
    "ss.addEventListener('change',function(){"
    "var m=ss.value,so={Critical:0,High:1,Normal:2};"
    "var s=[].slice.call(cards).sort(function(a,b){"
    "var ta=parseFloat(a.dataset.ts||0),tb=parseFloat(b.dataset.ts||0);"
    "if(m==='severity'){"
    "var sa=so[a.dataset.severity]||3,sb=so[b.dataset.severity]||3;"
    "return sa!==sb?sa-sb:tb-ta;}"
    "if(m==='newest')return tb-ta;"
    "return ta-tb;});"
    "s.forEach(function(c){grid.appendChild(c);});run();});"
    "document.querySelectorAll('.snum').forEach(function(el){"
    "var t=parseInt(el.textContent,10);if(isNaN(t)||t===0)return;"
    "var cur=0,step=Math.max(1,Math.ceil(t/30));"
    "var id=setInterval(function(){"
    "cur=Math.min(cur+step,t);el.textContent=cur;"
    "if(cur>=t)clearInterval(id);},28);});"
    "})();"
)


# ---------------------------------------------------------------------------
# Card rendering
# ---------------------------------------------------------------------------
def _card(art: dict) -> str:
    sev  = art["severity"]
    sc   = sev.lower()
    bc   = {"Critical": "bsc", "High": "bsh", "Normal": "bsn"}[sev]
    col  = art["color"]
    rt   = reading_time(art["summary"])
    also = ""
    if art.get("other_sources"):
        also = '<span class="also">Also: ' + h(", ".join(sorted(art["other_sources"]))) + "</span>"
    return (
        f'<article class="card {sc}" data-severity="{sev}"'
        f' data-source="{h(art["source"])}" data-ts="{art["timestamp"]}">'
        f'<div class="ctop">'
        f'<div class="bdgs">'
        f'<span class="bdg" style="background:{col}22;border:1px solid {col}55;color:{col}">'
        f'{h(art["source"])}</span>'
        f'<span class="bdg {bc}">{sev}</span>'
        f"</div>"
        f'<span class="rt">{rt}</span>'
        f"</div>"
        f'<h2 class="ctitle"><a href="{h(art["link"])}" target="_blank" rel="noopener noreferrer">'
        f"{enrich_cve(art['title'])}</a></h2>"
        f'<p class="csum">{enrich_cve(art["summary"]) or "No summary available."}</p>'
        f'<div class="cfoot">'
        f'<span class="cdate">{h(art["published"]) or "Recently published"}</span>'
        f"{also}"
        f'<a class="rlink" href="{h(art["link"])}" target="_blank" rel="noopener noreferrer">Read &rarr;</a>'
        f"</div></article>"
    )


# ---------------------------------------------------------------------------
# HTML generation
# ---------------------------------------------------------------------------
def _page(title: str, css: str, body: str) -> str:
    return (
        "<!DOCTYPE html><html lang='en'><head>"
        "<meta charset='UTF-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1.0'>"
        "<title>" + h(title) + "</title>"
        "<style>" + css + "</style>"
        "</head><body>" + body + "</body></html>"
    )

def generate_html(arts: list[dict], report_date: str,
                  health_data: dict[str, int], sched_warn: str) -> str:
    sev_ord = {"Critical": 0, "High": 1, "Normal": 2}
    arts.sort(key=lambda x: (sev_ord.get(x["severity"], 3), -x["timestamp"]))

    total   = len(arts)
    n_crit  = sum(1 for a in arts if a["severity"] == "Critical")
    n_high  = sum(1 for a in arts if a["severity"] == "High")
    n_norm  = sum(1 for a in arts if a["severity"] == "Normal")
    sources = sorted({a["source"] for a in arts})
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    alerts = ""
    if sched_warn:
        alerts += '<div class="alert ai"><span class="ai-ico">&#8505;</span><span>' + sched_warn + "</span></div>"
    for name, _, _ in FEEDS:
        if health_data.get(name, 0) >= 3:
            alerts += ('<div class="alert ae"><span class="ai-ico">&#9888;</span>'
                       "<span><strong>" + h(name) + "</strong> has failed "
                       + str(health_data[name]) + " consecutive times.</span></div>")

    chips = ""
    for name, _, _ in FEEDS:
        fails = health_data.get(name, 0)
        dc    = "ok" if fails == 0 else ("fail" if fails >= 3 else "warn")
        chips += f'<span class="chip" title="{"OK" if fails==0 else f"{fails} failure(s)"}"><span class="dot {dc}"></span>{h(name)}</span>'

    cards_html = ("\n".join(_card(a) for a in arts) if arts else
                  '<div class="empty"><span class="ico">&#128274;</span>No new articles since your last digest.</div>')

    body = (
        '<div class="wrap">'
        '<header class="site-header">'
        '<div class="logo">'
        '<div class="logo-icon">&#x1F6E1;</div>'
        '<div class="logo-text"><h1>CyberDigest</h1>'
        '<div class="tag">Automated threat intelligence &middot; ' + h(report_date) + "</div>"
        "</div></div>"
        '<div class="hdr-right">'
        '<span class="run-time">Generated ' + now_str + "</span>"
        '<a class="arch-btn" href="index.html">&#x1F4C1; Archive</a>'
        "</div></header>"

        '<div class="stats-bar">'
        '<div class="scard"><div class="snum">'     + str(total)       + '</div><div class="slbl">Articles</div></div>'
        '<div class="scard"><div class="snum red">' + str(n_crit)      + '</div><div class="slbl">Critical</div></div>'
        '<div class="scard"><div class="snum amb">' + str(n_high)      + '</div><div class="slbl">High</div></div>'
        '<div class="scard"><div class="snum grn">' + str(n_norm)      + '</div><div class="slbl">Normal</div></div>'
        '<div class="scard"><div class="snum">'     + str(len(sources)) + '</div><div class="slbl">Sources</div></div>'
        "</div>"
        + alerts +
        '<div class="hp"><span class="hp-lbl">&#x1F4E1; Feeds</span>' + chips + "</div>"
        '<div class="controls">'
        '<input id="si" class="search" type="search" placeholder="Search articles, CVEs, sources…" autocomplete="off">'
        '<div class="tabs">'
        '<button class="tab on" data-f="All">All ('           + str(total)  + ")</button>"
        '<button class="tab"    data-f="Critical">&#x1F534; Critical (' + str(n_crit) + ")</button>"
        '<button class="tab"    data-f="High">&#x1F7E0; High ('       + str(n_high) + ')</button>'
        '<button class="tab"    data-f="Normal">&#x1F535; Normal ('   + str(n_norm) + ')</button>'
        "</div>"
        '<select class="sort" id="ss">'
        "<option value='severity'>Sort: Severity</option>"
        "<option value='newest'>Sort: Newest</option>"
        "<option value='oldest'>Sort: Oldest</option>"
        "</select></div>"
        '<div class="rbar" id="rb"></div>'
        '<main class="grid" id="grid">' + cards_html + "</main>"
        '<footer class="site-footer">'
        "CyberDigest &mdash; self-healing &middot; next run in " + str(CONFIG["interval_days"]) + " days"
        " &nbsp;&middot;&nbsp; "
        '<a href="index.html">Past Reports</a>'
        "</footer></div>"
        "<script>" + _JS + "</script>"
    )
    return _page("CyberDigest — " + report_date, _CSS, body)


def generate_index_html():
    reports = sorted(REPORTS_DIR.glob("cybersec_report_*.html"), reverse=True)

    while len(reports) > CONFIG["max_archived_reports"]:
        try:
            reports.pop().unlink()
        except Exception:
            pass

    rows = ""
    for i, r in enumerate(reports):
        dp = r.stem.replace("cybersec_report_", "")
        try:
            dt    = datetime.strptime(dp, "%Y%m%d_%H%M")
            disp  = dt.strftime("%B %d, %Y")
            t_str = dt.strftime("%I:%M %p")
        except ValueError:
            disp, t_str = dp, ""
        latest = ('<span style="font-size:9.5px;background:rgba(34,211,238,.15);color:#22d3ee;'
                  'padding:1px 7px;border-radius:999px;margin-left:7px;border:1px solid rgba(34,211,238,.3)">Latest</span>'
                  if i == 0 else "")
        rows += (f'<a href="{r.name}" class="rrow">'
                 f'<span class="rico">&#x1F4C4;</span>'
                 f'<span class="rname">{disp}{latest}</span>'
                 f'<span class="rtime">{t_str}</span></a>')

    body = (
        '<div class="wrap">'
        '<header class="site-header"><div class="logo">'
        '<div class="logo-icon">&#x1F4C1;</div>'
        '<div class="logo-text"><h1>CyberDigest Archive</h1>'
        '<div class="tag">' + str(len(reports)) + " past report(s)</div>"
        "</div></div></header>"
        '<div class="rlist">' + (rows or "<p>No reports yet.</p>") + "</div>"
        '<footer class="site-footer"><a href="javascript:history.back()">&#x2190; Back to latest</a></footer>'
        "</div>"
    )
    idx = _page("CyberDigest Archive", _CSS + _IDXCSS, body)
    tmp = REPORTS_DIR / "index.html.tmp"
    tmp.write_text(idx, encoding="utf-8")
    tmp.rename(REPORTS_DIR / "index.html")


# ---------------------------------------------------------------------------
# OS scheduling
# ---------------------------------------------------------------------------
def register_scheduler() -> bool:
    os_name     = platform.system()
    script_path = str(Path(__file__).resolve())
    py_exec     = sys.executable
    interval    = CONFIG["interval_days"]
    try:
        if os_name == "Windows":
            subprocess.run(
                ["schtasks", "/Create", "/TN", "CyberDigest",
                 "/TR", f'"{py_exec}" "{script_path}"',
                 "/SC", "DAILY", "/MO", str(interval), "/F"],
                check=True, capture_output=True,
            )
        elif os_name == "Darwin":
            plist = (
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"'
                ' "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
                '<plist version="1.0"><dict>\n'
                "  <key>Label</key><string>com.cyberdigest</string>\n"
                "  <key>ProgramArguments</key><array>\n"
                "    <string>" + py_exec + "</string>\n"
                "    <string>" + script_path + "</string>\n"
                "  </array>\n"
                "  <key>StartInterval</key><integer>" + str(interval * 86400) + "</integer>\n"
                "  <key>RunAtLoad</key><true/>\n"
                "</dict></plist>\n"
            )
            pd = Path.home() / "Library" / "LaunchAgents"
            pd.mkdir(parents=True, exist_ok=True)
            pp = pd / "com.cyberdigest.plist"
            pp.write_text(plist)
            subprocess.run(["launchctl", "unload", str(pp)], capture_output=True)
            subprocess.run(["launchctl", "load",   str(pp)], check=True, capture_output=True)
        elif os_name == "Linux":
            try:
                cur = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
            except Exception:
                cur = ""
            lines = [l for l in cur.splitlines() if "news_agent.py" not in l and "cyberdigest" not in l.lower()]
            lines.append(f"0 10 */{interval} * * {py_exec} {script_path}")
            subprocess.run(["crontab", "-"], input="\n".join(lines) + "\n", text=True, check=True)
        else:
            return False
        return verify_scheduler()
    except Exception as exc:
        _log.error("Scheduler registration failed: %s", exc)
        return False

def verify_scheduler() -> bool:
    os_name = platform.system()
    try:
        if os_name == "Windows":
            res = subprocess.run(["schtasks", "/query", "/TN", "CyberDigest"], capture_output=True, text=True)
            return "CyberDigest" in res.stdout
        if os_name == "Darwin":
            res = subprocess.run(["launchctl", "list"], capture_output=True, text=True)
            return "com.cyberdigest" in res.stdout
        if os_name == "Linux":
            res = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
            return "news_agent.py" in res.stdout
    except Exception as exc:
        _log.warning("Scheduler verify failed: %s", exc)
    return False

def uninstall_scheduler():
    os_name = platform.system()
    try:
        if os_name == "Windows":
            subprocess.run(["schtasks", "/Delete", "/TN", "CyberDigest", "/F"], check=True, capture_output=True)
        elif os_name == "Darwin":
            pp = Path.home() / "Library" / "LaunchAgents" / "com.cyberdigest.plist"
            if pp.exists():
                subprocess.run(["launchctl", "unload", str(pp)], capture_output=True)
                pp.unlink()
        elif os_name == "Linux":
            res = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
            if res.returncode == 0:
                lines = [l for l in res.stdout.splitlines()
                         if "news_agent.py" not in l and "cyberdigest" not in l.lower()]
                subprocess.run(["crontab", "-"], input="\n".join(lines) + "\n", text=True, check=True)
        print("✔  OS scheduler removed.")
    except Exception as exc:
        print(f"Uninstall error: {exc}")


# ---------------------------------------------------------------------------
# Health check CLI
# ---------------------------------------------------------------------------
def run_healthcheck() -> int:
    ok = True
    lines = ["=== CyberDigest Health Report ==="]

    sched = verify_scheduler()
    lines.append(f"OS Scheduler  : {'✔ Registered' if sched else '✘ NOT registered'}")
    if not sched:
        ok = False

    lr = get_last_run()
    lines.append(f"Last Run      : {lr.strftime('%Y-%m-%d %H:%M:%S') if lr else 'Never'}")
    if lr:
        age = datetime.now() - lr
        overdue = age > timedelta(days=CONFIG["interval_days"] + 1)
        if overdue:
            lines.append(f"  WARNING: last run was {age.days}d ago — may be stuck")
            ok = False

    try:
        with get_db() as c:
            n = c.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        lines.append(f"Database      : ✔ OK ({n} articles)")
    except Exception as e:
        lines.append(f"Database      : ✘ ERROR — {e}")
        ok = False

    _, _, free = shutil.disk_usage(BASE_DIR)
    free_mb = free // 2**20
    lines.append(f"Disk Free     : {free_mb} MB {'✔' if free_mb > 100 else '⚠ LOW'}")
    if free_mb < 100:
        ok = False

    net = check_internet()
    lines.append(f"Internet      : {'✔ OK' if net else '✘ FAILED'}")
    if not net:
        ok = False

    lines.append(f"Lock File     : {'Present (another instance running?)' if LOCK_FILE.exists() else 'Clear'}")
    lines.append(f"Email Delivery: {'Enabled' if CONFIG.get('email',{}).get('enabled') else 'Disabled'}")
    lines.append(f"NVD API Key   : {'Set' if CONFIG.get('nvd_api_key') else 'Not set (rate-limited)'}")

    lines.append("")
    lines.append("Feed reachability:")
    for name, url, _ in FEEDS:
        try:
            urllib.request.urlopen(url, timeout=3)
            lines.append(f"  ✔  {name}")
        except Exception:
            lines.append(f"  ✘  {name}")

    lines.append("")
    lines.append("=================================")
    lines.append(f"Overall: {'✔ HEALTHY' if ok else '⚠ ISSUES DETECTED'}")
    print("\n".join(lines))
    return 0 if ok else 1


# ---------------------------------------------------------------------------
# Status & heartbeat
# ---------------------------------------------------------------------------
def write_status(ok: int, fail: int, found: int):
    STATUS_FILE.write_text(
        f"Last Run    : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"Feeds OK    : {ok}\n"
        f"Feeds Failed: {fail}\n"
        f"New Articles: {found}\n"
        f"PID         : {os.getpid()}\n",
        encoding="utf-8",
    )
    HEARTBEAT_FILE.write_text(
        f"Agent awoke at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Core run
# ---------------------------------------------------------------------------
def run_agent(is_fallback: bool = False) -> bool:
    _log.info("=== Run started (PID %d) ===", os.getpid())
    HEARTBEAT_FILE.write_text(
        f"Agent awoke at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n",
        encoding="utf-8",
    )

    if not check_internet():
        _log.warning("No internet connection — skipping run.")
        return False

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    seen = load_seen()
    all_arts: list[dict] = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(FEEDS), 9)) as ex:
        futs = {ex.submit(fetch_feed, name, url, color, seen): name
                for name, url, color in FEEDS}
        for fut in concurrent.futures.as_completed(futs):
            result = fut.result()
            if result:
                all_arts.extend(result)

    health_data = get_health()
    ok_count    = sum(1 for f in FEEDS if health_data.get(f[0], 0) == 0)
    fail_count  = len(FEEDS) - ok_count

    write_status(ok_count, fail_count, len(all_arts))
    set_last_run(datetime.now())

    if not all_arts:
        _log.info("No new articles this run.")
        return False

    clustered = cluster(all_arts)
    save_articles(all_arts)

    now       = datetime.now()
    date_long = now.strftime("%B %d, %Y")
    file_date = now.strftime("%Y%m%d_%H%M")
    report    = REPORTS_DIR / f"cybersec_report_{file_date}.html"

    sched_warn = ("Automatic scheduling could not be set up — keep this window open to stay updated."
                  if is_fallback else "")

    try:
        html_content = generate_html(clustered, date_long, health_data, sched_warn)
        tmp = report.with_suffix(".html.tmp")
        tmp.write_text(html_content, encoding="utf-8")
        tmp.rename(report)
        generate_index_html()
    except Exception as exc:
        _log.error("Report write failed: %s", exc)
        return False

    _log.info("Report saved: %s (%d articles → %d clusters)", report.name, len(all_arts), len(clustered))

    # ── Email delivery ────────────────────────────────────────────────────
    n_crit = sum(1 for a in clustered if a["severity"] == "Critical")
    send_email(html_content, date_long, len(clustered), n_crit)

    # ── Desktop notification (skip on headless) ───────────────────────────
    if not is_headless() and _HAS_PLYER:
        try:
            _plyer_notification.notify(
                title="CyberDigest",
                message=f"{len(clustered)} articles ready — {n_crit} critical",
                timeout=10,
            )
        except Exception:
            pass

    # ── Open browser (skip on headless) ──────────────────────────────────
    if not is_headless():
        try:
            webbrowser.open(report.as_uri())
        except Exception as exc:
            _log.warning("Browser open failed: %s", exc)
    else:
        print(f"Report saved: {report}")

    _log.info("=== Run complete ===")
    return True


# ---------------------------------------------------------------------------
# System Tray GUI
# ---------------------------------------------------------------------------
def _gui_open_latest(icon, item):
    reports = sorted(REPORTS_DIR.glob("cybersec_report_*.html"), reverse=True)
    if reports:
        webbrowser.open(reports[0].as_uri())
    else:
        print("No reports generated yet.")

def _gui_fetch_now(icon, item):
    _log.info("Manual fetch triggered via GUI.")
    threading.Thread(target=lambda: run_agent(is_fallback=True), daemon=True).start()

def _gui_edit_config(icon, item):
    if platform.system() == "Windows":
        os.startfile(CONFIG_FILE)
    elif platform.system() == "Darwin":
        subprocess.run(["open", str(CONFIG_FILE)])
    else:
        subprocess.run(["xdg-open", str(CONFIG_FILE)])

def _gui_quit(icon, item):
    global _SHUTDOWN
    _SHUTDOWN = True
    icon.stop()

def _background_scheduler():
    schedule.every(CONFIG["interval_days"]).days.do(lambda: run_agent(is_fallback=True))
    while not _SHUTDOWN:
        schedule.run_pending()
        time.sleep(60)

def run_tray_gui():
    img = Image.new('RGB', (64, 64), color=(34, 211, 238))
    d = ImageDraw.Draw(img)
    d.rectangle([16, 16, 48, 48], fill=(13, 22, 40))
    d.polygon([(32, 20), (44, 40), (20, 40)], fill=(167, 139, 250))

    menu = pystray.Menu(
        item("CyberDigest Agent", lambda: None, enabled=False),
        pystray.Menu.SEPARATOR,
        item("Open Latest Digest", _gui_open_latest, default=True),
        item("Fetch News Now", _gui_fetch_now),
        item("Edit Config", _gui_edit_config),
        pystray.Menu.SEPARATOR,
        item("Quit", _gui_quit)
    )

    icon = pystray.Icon("CyberDigest", img, "CyberDigest Agent", menu)
    
    threading.Thread(target=_background_scheduler, daemon=True).start()
    
    lr = get_last_run()
    if lr is None or (datetime.now() - lr) >= timedelta(days=CONFIG["interval_days"]) - timedelta(hours=2):
        threading.Thread(target=lambda: run_agent(is_fallback=True), daemon=True).start()

    _log.info("Starting System Tray GUI...")
    print("\n[GUI] System Tray mode active. Look for the icon in your taskbar!")
    icon.run()
    return True


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description="CyberDigest — Production-grade cybersecurity news agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python3 news_agent.py                # Normal run (GUI on desktop)\n"
            "  python3 news_agent.py --cli-only     # Force CLI/Server mode\n"
            "  python3 news_agent.py --force        # Force run ignoring last-run time\n"
            "  python3 news_agent.py --healthcheck  # Print full health report\n"
            "  python3 news_agent.py --uninstall    # Remove OS scheduler\n"
        ),
    )
    parser.add_argument("--healthcheck", action="store_true", help="Print health report and exit")
    parser.add_argument("--uninstall",   action="store_true", help="Remove OS scheduled task and exit")
    parser.add_argument("--force",       action="store_true", help="Force a run, bypassing last-run check")
    parser.add_argument("--cli-only",    action="store_true", help="Run without system tray GUI")
    parser.add_argument("--version",     action="version",    version="CyberDigest 4.0")
    args = parser.parse_args()

    if args.uninstall:
        uninstall_scheduler()
        return 0

    init_db()

    if args.healthcheck:
        return run_healthcheck()

    # ── Lock: prevent duplicate instances ────────────────────────────────
    if not acquire_lock():
        print("Another instance of CyberDigest is already running. Exiting.")
        _log.warning("Could not acquire lock — another instance running.")
        return 1

    try:
        if args.force:
            print("--force flag set: running immediately.")
            run_agent(is_fallback=True)
            return 0

        headless = is_headless()
        if not headless and not args.cli_only and _HAS_GUI:
            print("=" * 54)
            print("  CyberDigest — Desktop Tray Mode v4.0")
            print("=" * 54)
            register_scheduler()
            success = run_tray_gui()
            if success:
                return 0

        # Fallback to pure CLI mode (like in Docker or missing GUI packages)
        print("=" * 54)
        print("  CyberDigest — CLI / Server Mode v4.0")
        print("=" * 54)
        print()

        registered = register_scheduler()

        lr  = get_last_run()
        now = datetime.now()

        if lr is None:
            should_run = True
            print("First run detected — fetching digest now.")
        elif (now - lr) >= timedelta(days=CONFIG["interval_days"]) - timedelta(hours=2):
            should_run = True
            print(f"Due for a new digest (last run: {lr.strftime('%Y-%m-%d %H:%M')}).")
        else:
            should_run = False
            next_run   = lr + timedelta(days=CONFIG["interval_days"])
            print(f"Already ran recently ({lr.strftime('%Y-%m-%d %H:%M')}).")
            print(f"Next scheduled run: {next_run.strftime('%Y-%m-%d %H:%M')}.")

        if should_run:
            retries = 0
            while not check_internet():
                retries += 1
                wait = min(30 * retries, 120)
                _log.warning("No internet — waiting %d min (attempt %d)", wait, retries)
                print(f"No internet connection. Retrying in {wait} minutes…")
                time.sleep(wait * 60)
            try:
                run_agent(is_fallback=not registered)
            except Exception as exc:
                _log.error("Unhandled run error: %s", exc, exc_info=True)

        if not registered or args.cli_only:
            _log.warning("Running in-process fallback loop.")
            print("\nRunning in background loop — leave window open (or use screen/tmux).")
            sched_interval = CONFIG["interval_days"]
            schedule.every(sched_interval).days.do(lambda: run_agent(is_fallback=True))
            try:
                while not _SHUTDOWN:
                    schedule.run_pending()
                    time.sleep(60)
            except KeyboardInterrupt:
                print("\nStopped.")
        else:
            print()
            print("✔  Done! CyberDigest is scheduled via OS.")
            print("   Check status.txt or run --healthcheck to verify.")

    finally:
        release_lock()

    return 0


if __name__ == "__main__":
    sys.exit(main())
