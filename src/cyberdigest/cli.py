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
from cyberdigest.lock import acquire_lock, lock_is_active, release_lock
from cyberdigest.logging_setup import log
from cyberdigest.network import check_internet, is_headless
from cyberdigest.paths import LOCK_FILE, RUN_LOCK_FILE
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
        mode = (
            "expected (headless/fallback OK)"
            if headless and not require_scheduler
            else "NOT registered"
        )
        lines.append(f"OS Scheduler  : ✘ {mode}")
        if require_scheduler or not headless:
            # Desktop installs expect a scheduler; headless Docker does not.
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

    try:
        _, _, free = shutil.disk_usage(DATA_DIR)
        free_mb = free // 2**20
        lines.append(f"Disk Free     : {free_mb} MB {'✔' if free_mb > 100 else '⚠ LOW'}")
    except OSError as exc:
        free_mb = 0
        lines.append(f"Disk Free     : ✘ ERROR — {exc}")
    if free_mb < 100:
        ok = False

    net = check_internet()
    lines.append(f"Internet      : {'✔ OK' if net else '✘ FAILED'}")
    if not net:
        ok = False

    active_locks = [
        name for name, path in (("app", LOCK_FILE), ("run", RUN_LOCK_FILE)) if lock_is_active(path)
    ]
    lines.append(f"Lock Files    : {', '.join(active_locks) if active_locks else 'Clear'}")
    lines.append(
        f"Email Delivery: {'Enabled' if cfg.get('email', {}).get('enabled') else 'Disabled'}"
    )
    lines.append(f"NVD API Key   : {'Set' if cfg.get('nvd_api_key') else 'Not set (rate-limited)'}")
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
    total_feeds = sum(len(feed_list) for _, feed_list in sections)
    reachable_feeds = 0
    if total_feeds == 0:
        lines.append("  ✘  No feeds configured")
        ok = False
    for label, flist in sections:
        lines.append(f"  --- {label} ---")
        for name, url, _ in flist:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(req, timeout=10):
                    pass
                lines.append(f"  ✔  {name}")
                reachable_feeds += 1
            except Exception:
                lines.append(f"  ✘  {name}")
    if total_feeds and reachable_feeds == 0:
        ok = False

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


def _register_signal_handlers() -> None:
    """Register graceful shutdown handlers where the runtime allows it."""
    for sig_name in ("SIGTERM", "SIGINT"):
        sig = getattr(signal, sig_name, None)
        if sig is None:
            continue
        try:
            signal.signal(sig, _handle_signal)
        except (OSError, RuntimeError, ValueError):
            pass


def _build_parser() -> argparse.ArgumentParser:
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
    parser.add_argument(
        "--uninstall", action="store_true", help="Remove OS scheduled task and exit"
    )
    parser.add_argument(
        "--force", action="store_true", help="Force a run, bypassing last-run check"
    )
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
    return parser


def _digest_is_due(last_run: datetime | None, interval_days: int) -> bool:
    if last_run is None:
        return True
    tolerance = timedelta(hours=2)
    return datetime.now() - last_run >= timedelta(days=interval_days) - tolerance


def _run_agent_safely(*, fallback: bool, context: str) -> bool:
    try:
        return bool(run_agent(is_fallback=fallback))
    except Exception as exc:
        log.error("%s failed: %s", context, exc, exc_info=True)
        return False


def _wait_until_online(*, one_shot: bool) -> bool:
    retries = 0
    while not check_internet():
        if one_shot:
            print("No internet connection. One-shot run was not started.")
            return False
        retries += 1
        wait_seconds = min(30 * retries, 120)
        log.warning("No internet — waiting %d seconds (attempt %d)", wait_seconds, retries)
        print(f"No internet connection. Retrying in {wait_seconds} seconds…")
        time.sleep(wait_seconds)
    return True


def _run_desktop_mode(cfg: dict) -> bool:
    print("=" * 54)
    print(f"  CyberDigest — Desktop Tray Mode v{__version__}")
    print("=" * 54)
    registered = register_scheduler()

    last_run = get_last_run()
    if _digest_is_due(last_run, cfg["interval_days"]):
        print("Fetching your digest (browser will open when ready)…")
        _run_agent_safely(fallback=not registered, context="Startup fetch")
    else:
        print("Opening your latest digest…")
        if not open_latest_report():
            print("No digest yet — fetching now…")
            _run_agent_safely(fallback=not registered, context="Startup fetch")

    return run_tray_gui(scheduler_registered=registered, skip_startup_fetch=True)


def _scheduler_state(*, headless: bool, cli_only: bool, one_shot: bool) -> bool:
    if headless or cli_only:
        log.info("OS scheduler registration skipped in headless/CLI-only mode.")
        mode = "Headless/server" if headless else "CLI-only"
        suffix = "one-shot execution" if one_shot else "the in-process scheduler"
        print(f"{mode} mode — using {suffix}.")
        return False
    if one_shot:
        return verify_scheduler()
    return register_scheduler()


def _print_run_timing(last_run: datetime | None, interval_days: int, headless: bool) -> bool:
    if last_run is None:
        print("First run detected — fetching digest now.")
        return True
    if _digest_is_due(last_run, interval_days):
        print(f"Due for a new digest (last run: {last_run.strftime('%Y-%m-%d %H:%M')}).")
        return True

    next_run = last_run + timedelta(days=interval_days)
    print(f"Already ran recently ({last_run.strftime('%Y-%m-%d %H:%M')}).")
    print(f"Next scheduled run: {next_run.strftime('%Y-%m-%d %H:%M')}.")
    if not headless and open_latest_report():
        print("Opened the latest digest in your browser.")
    return False


def _run_fallback_loop(interval_days: int) -> None:
    log.warning("Running in-process fallback loop.")
    print("\nRunning in background loop — leave window open (or use Docker/systemd).")
    print("Tip: use --once for a single run that exits immediately.")

    def run_if_due() -> bool:
        if not _digest_is_due(get_last_run(), interval_days):
            return True
        return _run_agent_safely(fallback=True, context="Scheduled fallback run")

    # Check hourly so a failed startup cycle retries promptly. The successful
    # run timestamp still enforces interval_days and prevents extra digests.
    schedule.every().hour.do(run_if_due)
    try:
        while not _SHUTDOWN:
            schedule.run_pending()
            time.sleep(60)
    except KeyboardInterrupt:
        print("\nStopped.")


def _run_cli_mode(args: argparse.Namespace, cfg: dict, *, headless: bool) -> int:
    print("=" * 54)
    print(f"  CyberDigest — CLI / Server Mode v{__version__}")
    print("=" * 54)
    print()

    registered = _scheduler_state(headless=headless, cli_only=args.cli_only, one_shot=args.once)
    interval = cfg["interval_days"]
    should_run = _print_run_timing(get_last_run(), interval, headless)
    if should_run:
        if not _wait_until_online(one_shot=args.once):
            return 1
        succeeded = _run_agent_safely(
            fallback=not args.once and not registered and not headless,
            context="Digest run",
        )
        if args.once and not succeeded:
            return 1

    need_loop = not args.once and (headless or args.cli_only or not registered)
    if need_loop:
        _run_fallback_loop(interval)
    elif args.once:
        print("\n✔  One-shot run finished (--once).")
    else:
        print("\n✔  Done! CyberDigest is scheduled via OS.")
        print("   Check status.txt or run --healthcheck to verify.")
    return 0


def _handle_lock_contention() -> int:
    print("Another persistent CyberDigest instance is already running. Exiting.")
    log.warning("Could not acquire application lock — another instance is running.")
    if not is_headless() and open_latest_report():
        print("Opened the latest digest in your browser.")
        return 0
    return 1


def main(argv: list[str] | None = None) -> int:
    global _SHUTDOWN
    _SHUTDOWN = False
    _configure_stdio()
    _register_signal_handlers()
    args = _build_parser().parse_args(argv)

    if args.uninstall:
        return 1 if uninstall_scheduler() is False else 0

    reload_config()
    init_db()
    if args.healthcheck:
        return run_healthcheck(require_scheduler=args.require_scheduler)

    owns_app_lock = False
    if not args.once and not args.force:
        if not acquire_lock():
            return _handle_lock_contention()
        owns_app_lock = True

    try:
        cfg = get_config()
        if args.force:
            print("--force flag set: running immediately.")
            if not _wait_until_online(one_shot=True):
                return 1
            fallback = not is_headless() and not verify_scheduler()
            return 0 if _run_agent_safely(fallback=fallback, context="Forced run") else 1

        headless = is_headless()
        if not args.once and not headless and not args.cli_only and has_gui():
            if _run_desktop_mode(cfg):
                return 0
        return _run_cli_mode(args, cfg, headless=headless)
    finally:
        if owns_app_lock:
            release_lock()
