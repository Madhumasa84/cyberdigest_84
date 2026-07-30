"""System tray GUI (optional — requires pystray + Pillow)."""

from __future__ import annotations

import platform
import subprocess
import threading
import time
from datetime import datetime, timedelta

import schedule

from cyberdigest.agent import run_agent
from cyberdigest.config import get_config
from cyberdigest.db import get_last_run
from cyberdigest.logging_setup import log
from cyberdigest.paths import CONFIG_FILE
from cyberdigest.reports import open_latest_report

try:
    import pystray
    from PIL import Image, ImageDraw
    from pystray import MenuItem as item

    _HAS_GUI = True
except Exception:
    _HAS_GUI = False

_SHUTDOWN = False
_FETCH_LOCK = threading.Lock()


def has_gui() -> bool:
    return _HAS_GUI


def _gui_open_latest(icon=None, item_=None):
    if open_latest_report():
        return
    print("No reports generated yet.")


def _gui_fetch_now(icon=None, item_=None):
    log.info("Manual fetch triggered via GUI.")

    def _job():
        if not _FETCH_LOCK.acquire(blocking=False):
            log.warning("Fetch already in progress — ignoring tray request.")
            return
        try:
            run_agent(is_fallback=False)
        finally:
            _FETCH_LOCK.release()

    threading.Thread(target=_job, daemon=True).start()


def _gui_edit_config(icon=None, item_=None):
    if platform.system() == "Windows":
        import os

        os.startfile(str(CONFIG_FILE))  # type: ignore[attr-defined]
    elif platform.system() == "Darwin":
        subprocess.run(["open", str(CONFIG_FILE)])
    else:
        subprocess.run(["xdg-open", str(CONFIG_FILE)])


def _gui_quit(icon, item_):
    global _SHUTDOWN
    _SHUTDOWN = True
    icon.stop()


def _background_scheduler_only_when_needed(need_fallback: bool):
    """In-process schedule only if OS scheduler is NOT registered."""
    if not need_fallback:
        log.info("OS scheduler active — skipping in-process interval loop.")
        while not _SHUTDOWN:
            time.sleep(60)
        return

    log.warning("No OS scheduler — starting in-process fallback loop.")
    schedule.every(get_config()["interval_days"]).days.do(lambda: run_agent(is_fallback=True))
    while not _SHUTDOWN:
        schedule.run_pending()
        time.sleep(60)


def run_tray_gui(
    *,
    scheduler_registered: bool = False,
    skip_startup_fetch: bool = False,
) -> bool:
    if not _HAS_GUI:
        return False

    global _SHUTDOWN
    _SHUTDOWN = False

    img = Image.new("RGB", (64, 64), color=(34, 211, 238))
    d = ImageDraw.Draw(img)
    d.rectangle([16, 16, 48, 48], fill=(13, 22, 40))
    d.polygon([(32, 20), (44, 40), (20, 40)], fill=(167, 139, 250))

    menu = pystray.Menu(
        item("CyberDigest Agent", lambda: None, enabled=False),
        pystray.Menu.SEPARATOR,
        item("Open Latest Digest", _gui_open_latest, default=True),
        item("Fetch News Now", _gui_fetch_now),
        item("Edit Config", _gui_edit_config),
        pystray.Menu.SEPARATOR,
        item("Quit", _gui_quit),
    )

    icon = pystray.Icon("CyberDigest", img, "CyberDigest Agent", menu)

    # Single owner: only run in-process schedule when OS registration failed
    threading.Thread(
        target=lambda: _background_scheduler_only_when_needed(not scheduler_registered),
        daemon=True,
    ).start()

    if not skip_startup_fetch:
        # Caller did not pre-fetch on main thread (e.g. tests / advanced use)
        _gui_open_latest()
        lr = get_last_run()
        interval = get_config()["interval_days"]
        if lr is None or (datetime.now() - lr) >= timedelta(days=interval) - timedelta(hours=2):

            def _startup_fetch():
                if not _FETCH_LOCK.acquire(blocking=False):
                    return
                try:
                    run_agent(is_fallback=not scheduler_registered)
                finally:
                    _FETCH_LOCK.release()

            print("[GUI] Fetching latest news — browser opens when ready…")
            threading.Thread(target=_startup_fetch, daemon=True).start()

    log.info("Starting System Tray GUI...")
    print("\n[GUI] System Tray mode active. Look for the tray icon (taskbar).")
    print("      Right-click: Open Latest Digest | Fetch News Now | Quit")
    icon.run()
    return True
