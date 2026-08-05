"""Cross-platform process locks for the app and individual digest runs."""

from __future__ import annotations

import os
import platform
import time
from dataclasses import dataclass
from pathlib import Path
from typing import IO

from cyberdigest.logging_setup import log
from cyberdigest.paths import LOCK_FILE, RUN_LOCK_FILE

try:
    import fcntl
except ImportError:  # pragma: no cover - unavailable on Windows
    fcntl = None  # type: ignore[assignment]


@dataclass
class _LockState:
    fd: IO[str] | None = None
    owned: bool = False


_APP_LOCK = _LockState()
_RUN_LOCK = _LockState()


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if platform.system() == "Windows":
        try:
            import ctypes

            handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # type: ignore[attr-defined]
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)  # type: ignore[attr-defined]
                return True
            return ctypes.get_last_error() == 5  # access denied still means the PID exists
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def _acquire(path: Path, state: _LockState) -> bool:
    """Acquire *path* without truncating another process's PID file."""
    if state.owned:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)

    if platform.system() == "Windows" or fcntl is None:
        for _ in range(3):
            try:
                fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                try:
                    os.write(fd, str(os.getpid()).encode())
                finally:
                    os.close(fd)
                state.owned = True
                return True
            except FileExistsError:
                try:
                    pid = int(path.read_text(encoding="utf-8").strip() or "0")
                except (OSError, ValueError):
                    pid = 0
                if _pid_alive(pid):
                    return False
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    time.sleep(0.05)
        return False

    fd = None
    try:
        fd = path.open("a+", encoding="utf-8")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fd.seek(0)
        fd.truncate()
        fd.write(str(os.getpid()))
        fd.flush()
        state.fd = fd
        state.owned = True
        return True
    except OSError as exc:
        if fd is not None:
            fd.close()
        log.debug("Lock acquire failed for %s: %s", path, exc)
        return False


def _release(path: Path, state: _LockState) -> None:
    if not state.owned:
        return
    try:
        if fcntl is not None and state.fd is not None:
            try:
                fcntl.flock(state.fd, fcntl.LOCK_UN)
            finally:
                state.fd.close()
            # Keep the inode in place. Unlinking an advisory lock file creates
            # a race where another process can lock the old inode while a third
            # process creates and locks a new file at the same path.
        else:
            path.unlink(missing_ok=True)
    except OSError as exc:
        log.debug("Lock release failed for %s: %s", path, exc)
    finally:
        state.fd = None
        state.owned = False


def lock_is_active(path: Path) -> bool:
    """Return whether *path* is currently held, ignoring harmless stale files."""
    if not path.exists():
        return False
    if platform.system() == "Windows" or fcntl is None:
        try:
            pid = int(path.read_text(encoding="utf-8").strip() or "0")
        except (OSError, ValueError):
            return False
        return _pid_alive(pid)

    fd: IO[str] | None = None
    try:
        fd = path.open("a+", encoding="utf-8")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    except BlockingIOError:
        return True
    except OSError:
        # Failure to inspect should not falsely declare a running process clear.
        return True
    finally:
        if fd is not None:
            fd.close()


def acquire_lock() -> bool:
    """Acquire the persistent application-instance lock."""
    return _acquire(LOCK_FILE, _APP_LOCK)


def release_lock() -> None:
    _release(LOCK_FILE, _APP_LOCK)


def acquire_run_lock() -> bool:
    """Prevent overlapping feed/report runs across processes and tray threads."""
    return _acquire(RUN_LOCK_FILE, _RUN_LOCK)


def release_run_lock() -> None:
    _release(RUN_LOCK_FILE, _RUN_LOCK)
