from datetime import datetime

import cyberdigest.network as net
from cyberdigest.db import get_cve_cached, get_last_run, put_cve_cache, set_last_run
from cyberdigest.lock import acquire_lock, release_lock


def test_is_headless_env(monkeypatch):
    monkeypatch.setenv("CYBERDIGEST_HEADLESS", "1")
    assert net.is_headless() is True
    monkeypatch.setenv("CYBERDIGEST_HEADLESS", "0")
    monkeypatch.setenv("DISPLAY", ":0")
    # With headless env false and DISPLAY set on Linux → not headless
    # (Windows/Darwin always false without env)
    monkeypatch.setattr(net.platform, "system", lambda: "Linux")
    assert net.is_headless() is False


def test_check_internet_mocked(monkeypatch):
    monkeypatch.setattr(net.socket, "create_connection", lambda *a, **k: (_ for _ in ()).throw(OSError()))
    assert net.check_internet() is False

    class Conn:
        def close(self):
            pass

    monkeypatch.setattr(net.socket, "create_connection", lambda *a, **k: Conn())
    assert net.check_internet() is True


def test_db_cve_and_last_run(isolated_app):
    assert get_last_run() is None
    set_last_run(datetime(2024, 6, 1, 12, 0, 0))
    lr = get_last_run()
    assert lr is not None
    assert lr.year == 2024

    assert get_cve_cached("CVE-2024-1") is None
    put_cve_cache("CVE-2024-1", "7.5", "HIGH")
    assert get_cve_cached("CVE-2024-1") == ("7.5", "HIGH")


def test_lock_blocks_second_acquire(isolated_app, monkeypatch):
    # Ensure clean
    release_lock()
    assert acquire_lock() is True
    # On Unix, second flock from another fd should fail
    import cyberdigest.lock as lock_mod

    # Simulate by trying to open another exclusive flock
    if lock_mod.fcntl is not None:
        import fcntl

        from cyberdigest.paths import LOCK_FILE

        fd = open(LOCK_FILE, "w")
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                second = True
            except OSError:
                second = False
        finally:
            fd.close()
        assert second is False
    release_lock()
