"""Cross-platform process lock to prevent duplicate agents."""

from __future__ import annotations

import os
import platform
import time
from typing import Any

from cyberdigest.logging_setup import log
from cyberdigest.paths import LOCK_FILE

try:
    import fcntl
except ImportError:
    fcntl = None  # type: ignore

_LOCK_FD: Any = None


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if platform.system() == "Windows":
        try:
            import ctypes

            handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # type: ignore
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)  # type: ignore
                return True
            return False
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def acquire_lock() -> bool:
    """Return True if lock acquired, False if another instance is running."""
    global _LOCK_FD
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)

    if platform.system() == "Windows" or fcntl is None:
        # Atomic-ish create: exclusive create fails if file exists
        for _ in range(3):
            try:
                fd = os.open(str(LOCK_FILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                try:
                    os.write(fd, str(os.getpid()).encode())
                finally:
                    os.close(fd)
                return True
            except FileExistsError:
                try:
                    pid = int(LOCK_FILE.read_text(encoding="utf-8").strip() or "0")
                except Exception:
                    pid = 0
                if _pid_alive(pid):
                    return False
                # Stale lock — remove and retry
                try:
                    LOCK_FILE.unlink(missing_ok=True)
                except Exception:
                    time.sleep(0.05)
        return False

    try:
        _LOCK_FD = open(LOCK_FILE, "w", encoding="utf-8")
        fcntl.flock(_LOCK_FD, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _LOCK_FD.write(str(os.getpid()))
        _LOCK_FD.flush()
        return True
    except OSError as exc:
        log.debug("Lock acquire failed: %s", exc)
        return False


def release_lock() -> None:
    global _LOCK_FD
    try:
        if fcntl is not None and _LOCK_FD is not None:
            try:
                fcntl.flock(_LOCK_FD, fcntl.LOCK_UN)
            except Exception:
                pass
            try:
                _LOCK_FD.close()
            except Exception:
                pass
            _LOCK_FD = None
        LOCK_FILE.unlink(missing_ok=True)
    except Exception:
        pass
