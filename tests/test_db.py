from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from cyberdigest import db


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Fixture to provide a temporary, isolated database for testing."""
    test_db_file = tmp_path / "test_state.db"
    monkeypatch.setattr("cyberdigest.db.DB_FILE", test_db_file)
    db.init_db()
    return test_db_file


def test_db_state_last_run(temp_db):
    """Test get_last_run and set_last_run functionality."""
    # Initially should be None
    assert db.get_last_run() is None

    # Set a valid date
    now = datetime.now()
    db.set_last_run(now)

    last_run = db.get_last_run()
    assert last_run is not None
    # Compare ISO format strings to avoid microsecond precision issues or tzinfo differences
    assert last_run.isoformat() == now.isoformat()

    # Test invalid date string in DB doesn't crash but returns None
    with db.get_db() as c:
        c.execute("UPDATE agent_state SET value='not-a-date' WHERE key='last_run'")
    assert db.get_last_run() is None


def test_db_health(temp_db):
    """Test updating and retrieving feed health status."""
    source1 = "feed_1"
    source2 = "feed_2"

    # Initially empty
    health = db.get_health()
    assert health == {}

    # Successful update
    db.update_health(source1, ok=True)
    health = db.get_health()
    assert health[source1] == 0

    # Failure update
    db.update_health(source2, ok=False)
    health = db.get_health()
    assert health[source2] == 1

    # Consecutive failures
    db.update_health(source2, ok=False)
    health = db.get_health()
    assert health[source2] == 2

    # Recovery
    db.update_health(source2, ok=True)
    health = db.get_health()
    assert health[source2] == 0


def test_db_articles(temp_db):
    """Test saving articles and retrieving seen URLs."""
    articles = [
        {"link": "http://example.com/1", "title": "Article 1", "source": "Source A"},
        {"link": "http://example.com/2", "title": "Article 2", "source": "Source B"},
    ]

    # Initially no seen articles
    seen = db.load_seen()
    assert len(seen) == 0

    # Save articles
    db.save_articles(articles)

    # Check seen articles
    seen = db.load_seen()
    assert len(seen) == 2
    assert "http://example.com/1" in seen
    assert "http://example.com/2" in seen

    # Saving duplicates should be ignored (no crash)
    db.save_articles(articles)
    seen = db.load_seen()
    assert len(seen) == 2


def test_db_cve_cache(temp_db):
    """Test storing and retrieving from CVE cache."""
    cve_id = "CVE-2023-12345"
    score = "9.8"
    severity = "CRITICAL"

    # Initially not in cache
    assert db.get_cve_cached(cve_id) is None

    # Add to cache
    db.put_cve_cache(cve_id, score, severity)

    # Retrieve from cache
    cached = db.get_cve_cached(cve_id)
    assert cached is not None
    assert cached[0] == score
    assert cached[1] == severity

    # Update cache
    db.put_cve_cache(cve_id, "5.0", "MEDIUM")
    cached = db.get_cve_cached(cve_id)
    assert cached is not None
    assert cached[0] == "5.0"
    assert cached[1] == "MEDIUM"


def test_init_db_cleanup(temp_db):
    """Test that init_db cleans up old articles and CVE caches."""
    now = datetime.now()
    old_article_date = (now - timedelta(days=35)).isoformat()
    recent_article_date = (now - timedelta(days=10)).isoformat()
    old_cve_date = (now - timedelta(days=10)).isoformat()
    recent_cve_date = (now - timedelta(days=2)).isoformat()

    # Insert test data manually
    with db.get_db() as c:
        c.executemany(
            "INSERT INTO articles (url, title, source, first_seen) VALUES (?, ?, ?, ?)",
            [
                ("http://old.com", "Old", "Src", old_article_date),
                ("http://recent.com", "Recent", "Src", recent_article_date),
            ]
        )
        c.executemany(
            "INSERT INTO cve_cache (cve_id, score, severity, cached_at) VALUES (?, ?, ?, ?)",
            [
                ("CVE-OLD", "1.0", "LOW", old_cve_date),
                ("CVE-RECENT", "9.0", "HIGH", recent_cve_date),
            ]
        )

    # Call init_db, which should trigger cleanup
    db.init_db()

    # Check articles
    with db.get_db() as c:
        articles = [r["url"] for r in c.execute("SELECT url FROM articles").fetchall()]
        assert "http://old.com" not in articles
        assert "http://recent.com" in articles

        cves = [r["cve_id"] for r in c.execute("SELECT cve_id FROM cve_cache").fetchall()]
        assert "CVE-OLD" not in cves
        assert "CVE-RECENT" in cves


def test_get_db_pragmas(tmp_path, monkeypatch):
    """Test get_db sets correct journal mode based on platform."""
    test_db_file = tmp_path / "test_pragmas.db"
    monkeypatch.setattr("cyberdigest.db.DB_FILE", test_db_file)

    # Test Windows behavior
    monkeypatch.setattr("platform.system", lambda: "Windows")
    with db.get_db() as c:
        mode = c.execute("PRAGMA journal_mode").fetchone()[0]
        # SQLite returns lower case for pragma results
        assert mode.lower() == "delete"

    # Test Unix behavior
    monkeypatch.setattr("platform.system", lambda: "Linux")
    with db.get_db() as c:
        mode = c.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode.lower() == "wal"
