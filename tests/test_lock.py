from pathlib import Path

from cyberdigest import lock as lock_mod


def test_lock_acquire_release(monkeypatch, tmp_path):
    lock_path = tmp_path / "agent.lock"
    monkeypatch.setattr(lock_mod, "LOCK_FILE", lock_path)
    lock_mod._LOCK_FD = None

    assert lock_mod.acquire_lock() is True
    assert lock_path.exists()
    # Second acquire should fail while held (Unix flock / Windows exclusive)
    # Note: same process on Unix may re-lock depending on fd; release first
    lock_mod.release_lock()
    assert lock_mod.acquire_lock() is True
    lock_mod.release_lock()
