"""CLI entry point and healthcheck."""

from __future__ import annotations

import argparse
import shutil
import signal
import sys
import time
import urllib.request
from datetime import datetime, timedelta

import schedule

from cyberdigest import __version__
from cyberdigest.agent import run_agent
from cyberdigest.config import get_config, reload_config
from cyberdigest.db import get_db, get_last_run, init_db
from cyberdigest.feeds import USER_AGENT, load_feeds
from cyberdigest.lock import acquire_lock, release_lock
from cyberdigest.logging_setup import log
from cyberdigest.network import check_internet, is_headless
from cyberdigest.paths import LOCK_FILE
from cyberdigest.reports import open_latest_report
from cyberdigest.scheduler import register_scheduler, uninstall_scheduler, verify_scheduler
from cyberdigest.tray import has_gui, run_tray_gui

_SHUTDOWN = False


def _handle_signal(sig, frame):
    global _SHUTDOWN
    _SHUTDOWN = True
    log.info("Shutdown signal received (%s). Finishing gracefully…", sig)
    release_lock()
    sys.exit(0)


def run_healthcheck(*, require_scheduler: bool = False) -> int:
    """
    Print health report.
    Scheduler absence only fails overall when require_scheduler=True
    (not for Docker / intentional fallback).
    """
    ok = True
    lines = ["=== CyberDigest Health Report ==="]

    sched = verify_scheduler()
    headless = is_headless()
    if sched:
        lines.append("OS Scheduler  : ✔ Registered")
    else:
        mode = "expected (headless/fallback OK)" if headless and not require_scheduler else "NOT registered"
        lines.append(f"OS Scheduler  : ✘ {mode}")
        if require_scheduler or not headless:
            # Desktop installs expect a scheduler; headless Docker does not.
            if not headless:
                ok = False

    lr = get_last_run()
    lines.append(f"Last Run      : {lr.strftime('%Y-%m-%d %H:%M:%S') if lr else 'Never'}")
    cfg = get_config()
    if lr:
        age = datetime.now() - lr
        overdue = age > timedelta(days=cfg["interval_days"] + 1)
        if overdue:
            lines.append(f"  WARNING: last run was {age.days}d ago — may be stuck")
            ok = False

    try:
        with get_db() as c:
            n = c.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        lines.append(f"Database      : ✔ OK ({n} articles)")
    except Exception as e:
        lines.append(f"Database      : ✘ ERROR — {e}")
        ok = False

    from cyberdigest.paths import DATA_DIR

    _, _, free = shutil.disk_usage(DATA_DIR)
    free_mb = free // 2**20
    lines.append(f"Disk Free     : {free_mb} MB {'✔' if free_mb > 100 else '⚠ LOW'}")
    if free_mb < 100:
        ok = False

    net = check_internet()
    lines.append(f"Internet      : {'✔ OK' if net else '✘ FAILED'}")
    if not net:
        ok = False

    lines.append(
        f"Lock File     : {'Present (another instance running?)' if LOCK_FILE.exists() else 'Clear'}"
    )
    lines.append(
        f"Email Delivery: {'Enabled' if cfg.get('email', {}).get('enabled') else 'Disabled'}"
    )
    lines.append(
        f"NVD API Key   : {'Set' if cfg.get('nvd_api_key') else 'Not set (rate-limited)'}"
    )
    lines.append(f"GUI packages  : {'✔ Available' if has_gui() else '✘ Not installed (CLI only)'}")
    lines.append(f"Version       : {__version__}")

    feeds = load_feeds()
    sections = [
        ("Cybersecurity", feeds["cyber"]),
        ("Networking & Infrastructure", feeds["network"]),
        ("Cisco PSIRT", feeds["cisco"]),
        ("Fortinet PSIRT", feeds["fortinet"]),
    ]
    lines.append("")
    lines.append("Feed reachability:")
    for label, flist in sections:
        lines.append(f"  --- {label} ---")
        for name, url, _ in flist:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
                urllib.request.urlopen(req, timeout=10)
                lines.append(f"  ✔  {name}")
            except Exception:
                lines.append(f"  ✘  {name}")

    lines.append("")
    lines.append("=================================")
    lines.append(f"Overall: {'✔ HEALTHY' if ok else '⚠ ISSUES DETECTED'}")
    print("\n".join(lines))
    return 0 if ok else 1


def _configure_stdio() -> None:
    """Best-effort UTF-8 stdio so ✔/✘ status lines work on Windows consoles."""
    for stream in (sys.stdout, sys.stderr):
        reconf = getattr(stream, "reconfigure", None)
        if callable(reconf):
            try:
                reconf(encoding="utf-8", errors="replace")
            except Exception:
                pass


def main(argv: list[str] | None = None) -> int:
    global _SHUTDOWN
    _SHUTDOWN = False
    _configure_stdio()

    # Signal registration can fail on Windows / non-main threads — never crash for it
    for sig_name in ("SIGTERM", "SIGINT"):
        sig = getattr(signal, sig_name, None)
        if sig is None:
            continue
        try:
            signal.signal(sig, _handle_signal)
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        description="CyberDigest — Production-grade cybersecurity news agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python3 news_agent.py                # Normal run (GUI on desktop)\n"
            "  python3 news_agent.py --cli-only     # Force CLI/Server mode\n"
            "  python3 news_agent.py --force        # Force run ignoring last-run time\n"
            "  python3 news_agent.py --healthcheck  # Print full health report\n"
            "  python3 news_agent.py --uninstall    # Remove OS scheduler\n"
        ),
    )
    parser.add_argument("--healthcheck", action="store_true", help="Print health report and exit")
    parser.add_argument("--uninstall", action="store_true", help="Remove OS scheduled task and exit")
    parser.add_argument("--force", action="store_true", help="Force a run, bypassing last-run check")
    parser.add_argument("--cli-only", action="store_true", help="Run without system tray GUI")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run at most one digest cycle then exit (no background loop)",
    )
    parser.add_argument(
        "--require-scheduler",
        action="store_true",
        help="With --healthcheck, fail if OS scheduler is not registered",
    )
    parser.add_argument("--version", action="version", version=f"CyberDigest {__version__}")
    args = parser.parse_args(argv)

    reload_config()

    if args.uninstall:
        uninstall_scheduler()
        return 0

    init_db()

    if args.healthcheck:
        return run_healthcheck(require_scheduler=args.require_scheduler)

    if not acquire_lock():
        print("Another instance of CyberDigest is already running. Exiting.")
        log.warning("Could not acquire lock — another instance running.")
        if not is_headless() and open_latest_report():
            print("Opened the latest digest in your browser.")
            return 0
        return 1

    try:
        cfg = get_config()
        if args.force:
            print("--force flag set: running immediately.")
            registered = verify_scheduler()
            run_agent(is_fallback=not registered)
            return 0

        headless = is_headless()
        if not headless and not args.cli_only and has_gui():
            print("=" * 54)
            print(f"  CyberDigest — Desktop Tray Mode v{__version__}")
            print("=" * 54)
            registered = register_scheduler()

            # Fetch + open browser on the *main* thread first.
            # On Windows, opening HTML from a tray worker thread often does nothing.
            cfg = get_config()
            lr = get_last_run()
            now = datetime.now()
            interval = cfg["interval_days"]
            due = lr is None or (now - lr) >= timedelta(days=interval) - timedelta(
                hours=2
            )
            if due:
                print("Fetching your digest (browser will open when ready)…")
                try:
                    run_agent(is_fallback=not registered)
                except Exception as exc:
                    log.error("Startup fetch failed: %s", exc, exc_info=True)
            else:
                print("Opening your latest digest…")
                if not open_latest_report():
                    print("No digest yet — fetching now…")
                    try:
                        run_agent(is_fallback=not registered)
                    except Exception as exc:
                        log.error("Startup fetch failed: %s", exc, exc_info=True)

            # Tray for background use; skip duplicate startup fetch
            success = run_tray_gui(
                scheduler_registered=registered,
                skip_startup_fetch=True,
            )
            if success:
                return 0

        print("=" * 54)
        print(f"  CyberDigest — CLI / Server Mode v{__version__}")
        print("=" * 54)
        print()

        registered = False
        if not headless:
            registered = register_scheduler()
        else:
            # Docker/server: skip OS cron; use in-process loop or external orchestrator
            log.info("Headless mode — skipping OS scheduler registration.")
            print("Headless/server mode — using in-process scheduler.")

        lr = get_last_run()
        now = datetime.now()
        interval = cfg["interval_days"]

        if lr is None:
            should_run = True
            print("First run detected — fetching digest now.")
        elif (now - lr) >= timedelta(days=interval) - timedelta(hours=2):
            should_run = True
            print(f"Due for a new digest (last run: {lr.strftime('%Y-%m-%d %H:%M')}).")
        else:
            should_run = False
            next_run = lr + timedelta(days=interval)
            print(f"Already ran recently ({lr.strftime('%Y-%m-%d %H:%M')}).")
            print(f"Next scheduled run: {next_run.strftime('%Y-%m-%d %H:%M')}.")
            if not headless and open_latest_report():
                print("Opened the latest digest in your browser.")

        if should_run:
            retries = 0
            while not check_internet():
                retries += 1
                wait = min(30 * retries, 120)
                log.warning("No internet — waiting %d min (attempt %d)", wait, retries)
                print(f"No internet connection. Retrying in {wait} minutes…")
                time.sleep(wait * 60)
            try:
                run_agent(is_fallback=not registered and not headless)
            except Exception as exc:
                log.error("Unhandled run error: %s", exc, exc_info=True)

        # Single owner: in-process loop only when OS scheduler missing OR forced CLI
        # --once always exits after the (optional) run above.
        need_loop = (headless or not registered or args.cli_only) and not args.once
        if need_loop:
            log.warning("Running in-process fallback loop.")
            print("\nRunning in background loop — leave window open (or use Docker/systemd).")
            print("Tip: use --once for a single run that exits immediately.")
            schedule.every(interval).days.do(lambda: run_agent(is_fallback=True))
            try:
                while not _SHUTDOWN:
                    schedule.run_pending()
                    time.sleep(60)
            except KeyboardInterrupt:
                print("\nStopped.")
        else:
            print()
            if registered and not args.once:
                print("✔  Done! CyberDigest is scheduled via OS.")
                print("   Check status.txt or run --healthcheck to verify.")
            elif args.once:
                print("✔  One-shot run finished (--once).")
            else:
                print("✔  Done! CyberDigest is scheduled via OS.")
                print("   Check status.txt or run --healthcheck to verify.")

    finally:
        release_lock()

    return 0
