"""Network / environment helpers."""

from __future__ import annotations

import os
import platform
import socket


def check_internet() -> bool:
    # Try HTTPS first because corporate networks commonly block direct DNS
    # probes even when normal web access is available.
    for endpoint in (("1.1.1.1", 443), ("8.8.8.8", 53)):
        try:
            with socket.create_connection(endpoint, timeout=3):
                pass
            return True
        except OSError:
            pass
    return False


def is_headless() -> bool:
    """
    Detect server/headless environment (no browser/tray).

    Desktop OSes always count as non-headless unless CYBERDIGEST_HEADLESS=1.
    Linux without DISPLAY/WAYLAND is treated as headless (servers/SSH).
    """
    flag = os.environ.get("CYBERDIGEST_HEADLESS", "").strip().lower()
    if flag in ("1", "true", "yes", "on"):
        return True
    if flag in ("0", "false", "no", "off"):
        return False
    if platform.system() in ("Windows", "Darwin"):
        return False
    # Linux: allow WSL with GUI / remote desktop if DISPLAY is set
    return not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
