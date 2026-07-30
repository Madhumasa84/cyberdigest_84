"""Core digest run pipeline."""

from __future__ import annotations

import concurrent.futures
import os
from datetime import datetime
from pathlib import Path

from cyberdigest.config import get_config
from cyberdigest.db import get_health, load_seen, save_articles, set_last_run
from cyberdigest.emailer import send_email
from cyberdigest.enrich import enrich_articles
from cyberdigest.feeds import fetch_feed, load_feeds
from cyberdigest.logging_setup import log
from cyberdigest.network import check_internet, is_headless
from cyberdigest.paths import HEARTBEAT_FILE, REPORTS_DIR, STATUS_FILE
from cyberdigest.reports import (
    first_available_report,
    generate_html,
    generate_index_html,
    open_local_html,
)
from cyberdigest.scoring import cluster

try:
    from plyer import notification as _plyer_notification  # type: ignore

    _HAS_PLYER = True
except Exception:
    _HAS_PLYER = False


def write_status(ok: int, fail: int, found: int) -> None:
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATUS_FILE.write_text(
        f"Last Run    : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"Feeds OK    : {ok}\n"
        f"Feeds Failed: {fail}\n"
        f"New Articles: {found}\n"
        f"PID         : {os.getpid()}\n",
        encoding="utf-8",
    )
    HEARTBEAT_FILE.write_text(
        f"Agent awoke at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n",
        encoding="utf-8",
    )


def run_agent(*, is_fallback: bool = False) -> bool:
    """Fetch feeds, score, enrich, write reports. Returns True if new articles found."""
    cfg = get_config()
    log.info("=== Run started (PID %d) ===", os.getpid())
    HEARTBEAT_FILE.parent.mkdir(parents=True, exist_ok=True)
    HEARTBEAT_FILE.write_text(
        f"Agent awoke at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n",
        encoding="utf-8",
    )

    if not check_internet():
        log.warning("No internet connection — skipping run.")
        return False

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    seen = load_seen()
    feeds = load_feeds()
    all_feeds = feeds["cyber"] + feeds["network"] + feeds["cisco"] + feeds["fortinet"]
    all_arts: list[dict] = []

    caps = {
        "cyber": cfg["max_articles_per_feed"],
        "network": cfg.get("max_articles_per_network_feed", 5),
        "cisco": 20,
        "fortinet": 20,
    }

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(all_feeds), 16)) as ex:
        futs: dict = {}
        for category in ["cyber", "network", "cisco", "fortinet"]:
            for name, url, color in feeds[category]:
                futs[ex.submit(fetch_feed, name, url, color, seen, category, caps[category])] = name
        for fut in concurrent.futures.as_completed(futs):
            if result := fut.result():
                all_arts.extend(result)

    health_data = get_health()
    ok_count = sum(1 for f in all_feeds if health_data.get(f[0], 0) == 0)
    fail_count = len(all_feeds) - ok_count

    write_status(ok_count, fail_count, len(all_arts))
    set_last_run(datetime.now())

    if not all_arts:
        log.info("No new articles this run.")
        generate_index_html()
        from cyberdigest.reports import latest_report_path

        lp = latest_report_path()
        if lp and not is_headless():
            try:
                open_local_html(lp)
            except Exception as exc:
                log.warning("Browser open failed: %s", exc)
        elif lp:
            print(f"Report: {lp.resolve()}")
        else:
            print("No previous reports to open. Try again after feeds return news.")
        return False

    categories = ["cyber", "network", "cisco", "fortinet"]
    arts = {cat: [a for a in all_arts if a.get("category") == cat] for cat in categories}
    clustered = {cat: cluster(arts[cat]) for cat in categories}

    # Enrich CVEs once before HTML (not during render)
    all_clustered = sum(clustered.values(), [])
    enrich_articles(all_clustered)

    save_articles(all_arts)

    now = datetime.now()
    date_long = now.strftime("%B %d, %Y")
    file_date = now.strftime("%Y%m%d_%H%M")

    sched_warn = (
        "Automatic scheduling could not be set up — keep this window open to stay updated."
        if is_fallback
        else ""
    )

    prefixes = {
        "cyber": "cybersec_report_",
        "network": "network_report_",
        "cisco": "cisco_report_",
        "fortinet": "fortinet_report_",
    }
    reports = {cat: REPORTS_DIR / f"{prefixes[cat]}{file_date}.html" for cat in categories}

    def _nav_name(clustered: list, report: Path, prefix: str) -> str:
        if clustered:
            return report.name
        from cyberdigest.reports import latest_report_name
        return latest_report_name(prefix) or "index.html"

    nav_targets = {cat: _nav_name(clustered[cat], reports[cat], prefixes[cat]) for cat in categories}

    htmls = {}
    names = {
        "cyber": "Cyber",
        "network": "Network",
        "cisco": "Cisco PSIRT",
        "fortinet": "Fortinet PSIRT",
    }

    try:
        for cat in categories:
            if clustered[cat]:
                html = generate_html(
                    clustered[cat],
                    file_date,
                    health_data,
                    sched_warn,
                    feeds[cat],
                    cat,
                    nav_targets,
                )
                htmls[cat] = html
                _atomic_write(reports[cat], html)
                log.info(
                    "%s report saved: %s (%d arts → %d clusters)",
                    names[cat],
                    reports[cat].name,
                    len(arts[cat]),
                    len(clustered[cat]),
                )

        generate_index_html()
    except Exception as exc:
        log.error("Report write failed: %s", exc)
        return False

    total_clustered = clustered["cyber"] + clustered["network"]
    n_crit = sum(1 for a in total_clustered if a["severity"] == "Critical")
    if htmls.get("cyber"):
        send_email(htmls["cyber"], date_long, len(total_clustered), n_crit)

    if not is_headless() and _HAS_PLYER:
        try:
            _plyer_notification.notify(
                title="CyberDigest",
                message=(
                    f"{len(clustered['cyber'])} cyber + {len(clustered['network'])} network articles"
                    f" — {n_crit} critical"
                ),
                timeout=10,
            )
        except Exception:
            pass

    report_paths = [reports["cyber"], reports["network"], reports["cisco"], reports["fortinet"]]
    rpt = first_available_report(report_paths)
    if rpt:
        if is_headless():
            print(f"Report: {rpt.resolve()}")
        else:
            try:
                open_local_html(rpt)
            except Exception as exc:
                log.warning("Browser open failed: %s", exc)
                print(f"\n  📄 Open this report manually:\n     {rpt.resolve()}\n")
    else:
        log.warning("Run finished but no report files were written.")

    log.info("=== Run complete ===")
    return True


def _atomic_write(path: Path, content: str) -> None:
    """Write via temp file. Use replace() so Windows can overwrite existing targets."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)
