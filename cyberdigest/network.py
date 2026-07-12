"""Network / environment helpers."""

from __future__ import annotations

import os
import platform
import socket


def check_internet() -> bool:
    for host in ("8.8.8.8", "1.1.1.1"):
        try:
            socket.create_connection((host, 53), timeout=3)
            return True
        except OSError:
            pass
    return False


def is_headless() -> bool:
    """Detect server/headless environment (no browser/tray)."""
    if os.environ.get("CYBERDIGEST_HEADLESS", "").lower() in ("1", "true", "yes"):
        return True
    if platform.system() == "Windows":
        return False
    if platform.system() == "Darwin":
        return False
    return not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
