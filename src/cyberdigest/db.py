"""SQLite persistence for articles, health, state, and CVE cache."""

from __future__ import annotations

import platform
import sqlite3
from datetime import datetime

from cyberdigest.paths import DB_FILE


def get_db() -> sqlite3.Connection:
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_FILE, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # WAL is great on Unix; on Windows it often leaves locked -wal/-shm files
    # that break pytest tmp cleanup and multi-process access.
    if platform.system() == "Windows":
        conn.execute("PRAGMA journal_mode=DELETE")
    else:
        conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db() -> None:
    with get_db() as c:
        c.executescript(
            """
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
            """
        )
        c.execute("DELETE FROM articles  WHERE first_seen  < date('now', '-30 days')")
        c.execute("DELETE FROM cve_cache WHERE cached_at   < date('now', '-7 days')")


def get_last_run() -> datetime | None:
    with get_db() as c:
        row = c.execute(
            "SELECT value FROM agent_state WHERE key='last_run'"
        ).fetchone()
        if row:
            try:
                return datetime.fromisoformat(row["value"])
            except ValueError:
                pass
    return None


def set_last_run(dt: datetime) -> None:
    with get_db() as c:
        c.execute(
            "INSERT OR REPLACE INTO agent_state(key,value) VALUES('last_run',?)",
            (dt.isoformat(),),
        )


def load_seen() -> set[str]:
    with get_db() as c:
        return {
            r["url"]
            for r in c.execute(
                "SELECT url FROM articles WHERE first_seen >= date('now', '-30 days')"
            ).fetchall()
        }


def save_articles(arts: list[dict]) -> None:
    now = datetime.now().isoformat()
    with get_db() as c:
        c.executemany(
            "INSERT OR IGNORE INTO articles(url,title,source,first_seen) VALUES(?,?,?,?)",
            [(a["link"], a["title"], a["source"], now) for a in arts],
        )


def update_health(source: str, ok: bool) -> None:
    now = datetime.now().isoformat()
    with get_db() as c:
        if ok:
            c.execute(
                "INSERT OR REPLACE INTO feed_health(source,consecutive_failures,last_checked) "
                "VALUES(?,0,?)",
                (source, now),
            )
        else:
            c.execute(
                """
                INSERT INTO feed_health(source,consecutive_failures,last_checked) VALUES(?,1,?)
                ON CONFLICT(source) DO UPDATE
                SET consecutive_failures=consecutive_failures+1, last_checked=excluded.last_checked
                """,
                (source, now),
            )


def get_health() -> dict[str, int]:
    with get_db() as c:
        return {
            r["source"]: r["consecutive_failures"]
            for r in c.execute(
                "SELECT source,consecutive_failures FROM feed_health"
            ).fetchall()
        }



def get_cve_cached_bulk(cve_ids: list[str]) -> dict[str, tuple[str, str]]:
    if not cve_ids:
        return {}
    results = {}
    with get_db() as c:
        for i in range(0, len(cve_ids), 900):
            chunk = cve_ids[i:i+900]
            placeholders = ",".join("?" for _ in chunk)
            rows = c.execute(
                f"SELECT cve_id, score, severity FROM cve_cache WHERE cve_id IN ({placeholders})",
                chunk,
            ).fetchall()
            for row in rows:
                results[row["cve_id"]] = (row["score"], row["severity"])
    return results

def get_cve_cached(cve_id: str) -> tuple[str, str] | None:

    with get_db() as c:
        row = c.execute(
            "SELECT score,severity FROM cve_cache WHERE cve_id=?", (cve_id,)
        ).fetchone()
        if row:
            return row["score"], row["severity"]
    return None


def put_cve_cache(cve_id: str, score: str, severity: str) -> None:
    now = datetime.now().isoformat()
    with get_db() as c:
        c.execute(
            "INSERT OR REPLACE INTO cve_cache(cve_id,score,severity,cached_at) VALUES(?,?,?,?)",
            (cve_id, score, severity, now),
        )
