from __future__ import annotations

import platform
import sqlite3

from cyberdigest.db import get_db


def test_get_db_windows(tmp_path, monkeypatch):
    """Test get_db uses DELETE journal_mode on Windows."""
    # Do not use isolated_app because isolated_app calls init_db(), which opens a connection.
    # If a WAL connection was open in the same thread but we then try to switch to DELETE in another connection or same file, sqlite might get confused or lock.
    # So let's isolate DB_FILE just for this test using tmp_path directly.
    import cyberdigest.db as db
    import cyberdigest.paths as paths

    db_file = tmp_path / "state.db"
    monkeypatch.setattr(db, "DB_FILE", db_file)

    monkeypatch.setattr(platform, "system", lambda: "Windows")

    conn = get_db()

    # Check journal_mode
    journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert journal_mode.lower() == "delete"

    # Check row_factory
    assert conn.row_factory == sqlite3.Row

    # Check synchronous mode
    synchronous = conn.execute("PRAGMA synchronous").fetchone()[0]
    # NORMAL is 1 in sqlite pragmas
    assert synchronous == 1 or synchronous == "1"

    conn.close()

def test_get_db_unix(tmp_path, monkeypatch):
    """Test get_db uses WAL journal_mode on Unix/Linux."""
    import cyberdigest.db as db
    import cyberdigest.paths as paths

    db_file = tmp_path / "state.db"
    monkeypatch.setattr(db, "DB_FILE", db_file)

    monkeypatch.setattr(platform, "system", lambda: "Linux")

    conn = get_db()

    # Check journal_mode
    journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert journal_mode.lower() == "wal"

    # Check synchronous mode
    synchronous = conn.execute("PRAGMA synchronous").fetchone()[0]
    assert synchronous == 1 or synchronous == "1"

    conn.close()

def test_get_db_mkdir(tmp_path, monkeypatch):
    """Test get_db creates the parent directory if it doesn't exist."""
    import shutil

    import cyberdigest.db as db
    import cyberdigest.paths as paths

    data_dir = tmp_path / "data"
    db_file = data_dir / "state.db"
    monkeypatch.setattr(db, "DB_FILE", db_file)

    # Delete the directory if it exists
    if data_dir.exists():
        shutil.rmtree(data_dir)

    assert not data_dir.exists()

    # get_db should recreate the directory
    conn = get_db()

    assert data_dir.exists()
    assert data_dir.is_dir()

    conn.close()
