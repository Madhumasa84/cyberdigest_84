"""Windows-style lock path (O_EXCL) works on all OSes."""

from __future__ import annotations


def test_windows_branch_acquire_release(isolated_app, monkeypatch):
    import cyberdigest.lock as lock_mod

    # Force Windows PID-file path even on Linux
    monkeypatch.setattr(lock_mod.platform, "system", lambda: "Windows")
    monkeypatch.setattr(lock_mod, "fcntl", None)
    lock_mod._LOCK_FD = None
    lock_mod.LOCK_FILE.unlink(missing_ok=True)

    assert lock_mod.acquire_lock() is True
    assert lock_mod.LOCK_FILE.exists()
    # Second exclusive create fails while file exists and pid "alive"
    monkeypatch.setattr(lock_mod, "_pid_alive", lambda pid: True)
    assert lock_mod.acquire_lock() is False

    monkeypatch.setattr(lock_mod, "_pid_alive", lambda pid: False)
    # Stale lock should be reclaimable
    lock_mod.LOCK_FILE.write_text("999999", encoding="utf-8")
    assert lock_mod.acquire_lock() is True
    lock_mod.release_lock()
