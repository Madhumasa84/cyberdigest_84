"""Core digest run pipeline."""

from __future__ import annotations

import concurrent.futures
import os
from datetime import datetime
from pathlib import Path

from cyberdigest.config import get_config
from cyberdigest.db import get_health, load_seen, record_success, update_health
from cyberdigest.emailer import send_email
from cyberdigest.enrich import enrich_articles
from cyberdigest.feeds import fetch_feed, load_feeds
from cyberdigest.lock import acquire_run_lock, release_run_lock
from cyberdigest.logging_setup import log
from cyberdigest.network import check_internet, is_headless
from cyberdigest.paths import HEARTBEAT_FILE, REPORTS_DIR, STATUS_FILE
from cyberdigest.reports import (
    first_available_report,
    generate_html,
    generate_index_html,
    latest_report_path,
    open_local_html,
)
from cyberdigest.scoring import cluster

try:
    from plyer import notification as _plyer_notification  # type: ignore

    _HAS_PLYER = True
except Exception:  # pragma: no cover - depends on desktop packages
    _HAS_PLYER = False


_CATEGORY_SPECS = {
    "cyber": ("cybersec_report_", "Cyber"),
    "network": ("network_report_", "Network"),
    "cisco": ("cisco_report_", "Cisco PSIRT"),
    "fortinet": ("fortinet_report_", "Fortinet PSIRT"),
}


def _atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def write_status(ok: int, fail: int, found: int) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _atomic_text(
        STATUS_FILE,
        f"Last Attempt: {now}\n"
        f"Feeds OK    : {ok}\n"
        f"Feeds Failed: {fail}\n"
        f"New Articles: {found}\n"
        f"PID         : {os.getpid()}\n",
    )
    _atomic_text(HEARTBEAT_FILE, f"Agent awoke at: {now}\n")


def _touch_heartbeat() -> None:
    _atomic_text(
        HEARTBEAT_FILE,
        f"Agent awoke at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n",
    )


def _submit_feeds(executor, feeds: dict, seen: set[str], cfg: dict) -> dict:
    futures: dict = {}
    caps = {
        "cyber": cfg["max_articles_per_feed"],
        "network": cfg.get("max_articles_per_network_feed", 5),
        "cisco": 20,
        "fortinet": 20,
    }
    for category in _CATEGORY_SPECS:
        for name, url, color in feeds[category]:
            future = executor.submit(
                fetch_feed,
                name,
                url,
                color,
                seen,
                category,
                caps[category],
            )
            futures[future] = name
    return futures


def _fetch_articles(feeds: dict, seen: set[str], cfg: dict) -> tuple[list[dict], dict, int, int]:
    all_feeds = [feed for category in _CATEGORY_SPECS for feed in feeds[category]]
    if not all_feeds:
        return [], {}, 0, 0

    articles: list[dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(all_feeds), 16)) as executor:
        futures = _submit_feeds(executor, feeds, seen, cfg)
        for future in concurrent.futures.as_completed(futures):
            try:
                articles.extend(future.result() or [])
            except Exception as exc:  # defensive: fetch_feed normally contains failures
                source = futures[future]
                log.error("Unexpected feed worker failure for %s: %s", source, exc)
                try:
                    update_health(source, False)
                except Exception:
                    log.debug("Could not update failed feed health for %s", source, exc_info=True)

    health = get_health()
    # Health is keyed by feed name, so count each distinct source once even
    # when the same feed appears in several categories.
    names = {name for name, _, _ in all_feeds}
    ok_count = sum(1 for name in names if health.get(name, 0) == 0)
    return articles, health, ok_count, len(names) - ok_count


def _cluster_by_category(articles: list[dict]) -> dict[str, list[dict]]:
    return {
        category: cluster([a for a in articles if a.get("category") == category])
        for category in _CATEGORY_SPECS
    }


def _report_paths(file_date: str) -> dict[str, Path]:
    return {
        category: REPORTS_DIR / f"{prefix}{file_date}.html"
        for category, (prefix, _) in _CATEGORY_SPECS.items()
    }


def _nav_targets(clustered: dict[str, list[dict]], paths: dict[str, Path]) -> dict[str, str]:
    from cyberdigest.reports import latest_report_name

    targets: dict[str, str] = {}
    for category, (prefix, _) in _CATEGORY_SPECS.items():
        targets[category] = (
            paths[category].name
            if clustered[category]
            else latest_report_name(prefix) or "index.html"
        )
    return targets


def _write_reports(
    clustered: dict[str, list[dict]],
    feeds: dict,
    health: dict[str, int],
    file_date: str,
    scheduling_warning: str,
) -> tuple[dict[str, Path], dict[str, str]]:
    paths = _report_paths(file_date)
    nav = _nav_targets(clustered, paths)
    rendered: dict[str, str] = {}

    for category, (_, label) in _CATEGORY_SPECS.items():
        category_articles = clustered[category]
        if not category_articles:
            continue
        html = generate_html(
            category_articles,
            file_date,
            health,
            scheduling_warning,
            feeds[category],
            category,
            nav,
        )
        _atomic_text(paths[category], html)
        rendered[category] = html
        log.info(
            "%s report saved: %s (%d clusters)", label, paths[category].name, len(category_articles)
        )

    generate_index_html()
    return paths, rendered


def _open_report(path: Path | None) -> None:
    if not path:
        log.warning("Run finished but no report files were written.")
        return
    if is_headless():
        print(f"Report: {path.resolve()}")
        return
    try:
        open_local_html(path)
    except Exception as exc:
        log.warning("Browser open failed: %s", exc)
        print(f"\n  Open this report manually:\n     {path.resolve()}\n")


def _notify_and_email(
    clustered: dict[str, list[dict]], rendered: dict[str, str], date: str
) -> None:
    all_articles = [article for values in clustered.values() for article in values]
    critical = sum(1 for article in all_articles if article["severity"] == "Critical")
    cyber_articles = clustered["cyber"]
    if "cyber" in rendered:
        cyber_critical = sum(1 for article in cyber_articles if article["severity"] == "Critical")
        send_email(rendered["cyber"], date, len(cyber_articles), cyber_critical)

    if not is_headless() and _HAS_PLYER:
        try:
            _plyer_notification.notify(
                title="CyberDigest",
                message=f"{len(all_articles)} new articles — {critical} critical",
                timeout=10,
            )
        except Exception:
            log.debug("Desktop notification failed", exc_info=True)


def _handle_no_articles(ok_count: int, total_feeds: int) -> bool:
    if total_feeds == 0:
        log.error("No feeds are configured; leaving last_run unchanged.")
        return False
    if ok_count == 0:
        log.error("Every configured feed failed; leaving last_run unchanged for a prompt retry.")
        return False
    try:
        generate_index_html()
        record_success([], datetime.now())
    except Exception as exc:
        log.error("Could not finalize an empty run: %s", exc, exc_info=True)
        return False

    report = latest_report_path()
    if report:
        _open_report(report)
    else:
        print("No previous reports to open. Try again after feeds return news.")
    log.info("No new articles this run.")
    return True


def _run_agent(*, is_fallback: bool = False) -> bool:
    cfg = get_config()
    log.info("=== Run started (PID %d) ===", os.getpid())
    _touch_heartbeat()

    if not check_internet():
        log.warning("No internet connection — skipping run.")
        return False

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    feeds = load_feeds()
    articles, health, ok_count, fail_count = _fetch_articles(feeds, load_seen(), cfg)
    total_feeds = ok_count + fail_count
    write_status(ok_count, fail_count, len(articles))

    if not articles:
        return _handle_no_articles(ok_count, total_feeds)

    clustered = _cluster_by_category(articles)
    all_clustered = [article for values in clustered.values() for article in values]
    try:
        enrich_articles(all_clustered)
        now = datetime.now()
        file_date = now.strftime("%Y%m%d_%H%M")
        warning = (
            "Automatic scheduling could not be set up — keep this window open to stay updated."
            if is_fallback
            else ""
        )
        paths, rendered = _write_reports(clustered, feeds, health, file_date, warning)
        record_success(articles, now)
    except Exception as exc:
        log.error("Digest generation failed; state was not committed: %s", exc, exc_info=True)
        return False

    _notify_and_email(clustered, rendered, now.strftime("%B %d, %Y"))
    _open_report(first_available_report(list(paths.values())))
    log.info("=== Run complete ===")
    return True


def run_agent(*, is_fallback: bool = False) -> bool:
    """Run one digest cycle, protected against cross-process overlap."""
    if not acquire_run_lock():
        log.warning("Another digest fetch is already running; skipping this cycle.")
        return False
    try:
        return _run_agent(is_fallback=is_fallback)
    finally:
        release_run_lock()


def _atomic_write(path: Path, content: str) -> None:
    """Backward-compatible report writer used by existing integrations/tests."""
    _atomic_text(path, content)
