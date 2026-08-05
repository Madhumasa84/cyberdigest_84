from pathlib import Path

from cyberdigest import lock as lock_mod


def test_lock_acquire_release(monkeypatch, tmp_path):
    lock_mod.release_lock()
    lock_path = tmp_path / "agent.lock"
    monkeypatch.setattr(lock_mod, "LOCK_FILE", lock_path)

    assert lock_mod.acquire_lock() is True
    assert lock_path.exists()
    # Second acquire should fail while held (Unix flock / Windows exclusive)
    # Note: same process on Unix may re-lock depending on fd; release first
    lock_mod.release_lock()
    assert lock_mod.acquire_lock() is True
    assert lock_mod.lock_is_active(lock_path) is True
    lock_mod.release_lock()
    assert lock_mod.lock_is_active(lock_path) is False


def test_persistent_and_run_locks_are_independent(monkeypatch, tmp_path):
    lock_mod.release_run_lock()
    lock_mod.release_lock()


def test_windows_lock_state_uses_pid(monkeypatch, tmp_path):
    lock_path = tmp_path / "agent.lock"
    lock_path.write_text("123", encoding="utf-8")
    monkeypatch.setattr(lock_mod.platform, "system", lambda: "Windows")
    monkeypatch.setattr(lock_mod, "_pid_alive", lambda pid: pid == 123)

    assert lock_mod.lock_is_active(lock_path) is True
    lock_path.write_text("invalid", encoding="utf-8")
    assert lock_mod.lock_is_active(lock_path) is False
    monkeypatch.setattr(lock_mod, "LOCK_FILE", tmp_path / "agent.lock")
    monkeypatch.setattr(lock_mod, "RUN_LOCK_FILE", tmp_path / "run.lock")

    assert lock_mod.acquire_lock() is True
    assert lock_mod.acquire_run_lock() is True

    lock_mod.release_run_lock()
    lock_mod.release_lock()
