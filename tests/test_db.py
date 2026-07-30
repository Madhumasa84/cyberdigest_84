from cyberdigest.db import get_db, load_seen, save_articles


def test_save_articles(isolated_app):
    arts = [
        {"link": "https://example.com/1", "title": "Article 1", "source": "Source A"},
        {"link": "https://example.com/2", "title": "Article 2", "source": "Source B"},
    ]

    assert len(load_seen()) == 0

    save_articles(arts)

    seen = load_seen()
    assert "https://example.com/1" in seen
    assert "https://example.com/2" in seen
    assert len(seen) == 2

    # Insert a duplicate link
    arts_dup = [
        {"link": "https://example.com/1", "title": "Article 1 dup", "source": "Source A"},
        {"link": "https://example.com/3", "title": "Article 3", "source": "Source C"},
    ]
    save_articles(arts_dup)

    seen_after = load_seen()
    assert len(seen_after) == 3
    assert "https://example.com/3" in seen_after

    # Check that title wasn't updated for the duplicate
    with get_db() as c:
        row = c.execute("SELECT title FROM articles WHERE url='https://example.com/1'").fetchone()
        assert row["title"] == "Article 1"
