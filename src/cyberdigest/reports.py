"""HTML digest and archive generation."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from cyberdigest.config import get_config
from cyberdigest.enrich import format_with_cves
from cyberdigest.logging_setup import log
from cyberdigest.paths import ASSETS_DIR, REPORTS_DIR
from cyberdigest.textutil import h, reading_time, safe_http_url


def _load_asset(name: str) -> str:
    path = ASSETS_DIR / name
    return path.read_text(encoding="utf-8")


_CSS = _load_asset("css.txt")
_IDXCSS = _load_asset("idxcss.txt")
_JS = _load_asset("js.txt")


_BADGE_CLASSES = {"Critical": "bsc", "High": "bsh", "Normal": "bsn"}


def normalize_severity(severity: object) -> str:
    """Map any severity onto one of the three rendered buckets."""
    return str(severity) if severity in _BADGE_CLASSES else "Normal"


def _card(art: dict) -> str:
    sev = normalize_severity(art.get("severity"))
    sc = sev.lower()
    bc = _BADGE_CLASSES[sev]
    col = re_safe_color(art.get("color") or "#3b82f6")
    rt = reading_time(art["summary"])
    also = ""
    if art.get("other_sources"):
        also = '<span class="also">Also: ' + h(", ".join(sorted(art["other_sources"]))) + "</span>"
    link = safe_http_url(art.get("link"))
    cve_scores = art.get("cve_scores") or {}
    return (
        f'<article class="card {sc}" data-severity="{h(sev)}"'
        f' data-source="{h(art["source"])}" data-ts="{art["timestamp"]}">'
        f'<div class="ctop">'
        f'<div class="bdgs">'
        f'<span class="bdg" style="background:{col}22;border:1px solid {col}55;color:{col}">'
        f"{h(art['source'])}</span>"
        f'<span class="bdg {bc}">{h(sev)}</span>'
        f"</div>"
        f'<span class="rt">{h(rt)}</span>'
        f"</div>"
        f'<h2 class="ctitle"><a href="{h(link)}" target="_blank" rel="noopener noreferrer">'
        f"{format_with_cves(art['title'], cve_scores)}</a></h2>"
        f'<p class="csum">{format_with_cves(art["summary"], cve_scores) or "No summary available."}</p>'
        f'<div class="cfoot">'
        f'<span class="cdate">{h(art["published"]) or "Recently published"}</span>'
        f"{also}"
        f'<a class="rlink" href="{h(link)}" target="_blank" rel="noopener noreferrer">Read &rarr;</a>'
        f"</div></article>"
    )


def re_safe_color(color: str) -> str:
    """Allow only simple CSS hex colors from feed config."""
    c = (color or "").strip()
    if (
        len(c) in (4, 7)
        and c.startswith("#")
        and all(ch in "0123456789abcdefABCDEF" for ch in c[1:])
    ):
        return c
    return "#3b82f6"


def _page(title: str, css: str, body: str) -> str:
    return (
        "<!DOCTYPE html><html lang='en'><head>"
        "<meta charset='UTF-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1.0'>"
        "<title>" + h(title) + "</title>"
        "<style>" + css + "</style>"
        "</head><body>" + body + "</body></html>"
    )


def latest_report_name(prefix: str) -> str | None:
    reports = sorted(REPORTS_DIR.glob(f"{prefix}*.html"), reverse=True)
    return reports[0].name if reports else None


# Back-compat alias
_latest_report_name = latest_report_name


def first_available_report(report_paths: list[Path | None]) -> Path | None:
    for rpt in report_paths:
        if rpt and rpt.exists():
            return rpt
    return None


def _report_sort_key(path: Path) -> tuple[float, str]:
    match = re.search(r"(\d{8}_\d{4})$", path.stem)
    if match:
        try:
            return datetime.strptime(match.group(1), "%Y%m%d_%H%M").timestamp(), path.name
        except ValueError:
            pass
    try:
        return path.stat().st_mtime, path.name
    except OSError:
        return 0.0, path.name


def latest_report_path() -> Path | None:
    reports: list[Path] = []
    for prefix in (
        "cybersec_report_",
        "network_report_",
        "cisco_report_",
        "fortinet_report_",
    ):
        reports.extend(REPORTS_DIR.glob(f"{prefix}*.html"))
    return max(reports, key=_report_sort_key, default=None)


def _open_windows(path_str: str) -> None:
    """
    Open a file on Windows in a way that works from *any* thread.

    os.startfile() often fails or does nothing when called from a
    background thread (tray fetch). `cmd /c start` is reliable.
    """
    import os
    import subprocess

    errors: list[Exception] = []

    # 1) cmd start — works from worker threads; empty title arg is required
    try:
        subprocess.Popen(
            ["cmd", "/c", "start", "", path_str],
            close_fds=True,
            shell=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return
    except Exception as exc:
        errors.append(exc)

    # 2) os.startfile (main-thread friendly)
    try:
        if hasattr(os, "startfile"):
            os.startfile(path_str)  # type: ignore[attr-defined]
            return
    except Exception as exc:
        errors.append(exc)

    # 3) webbrowser last resort
    import webbrowser

    try:
        if webbrowser.open(Path(path_str).resolve().as_uri(), new=2):
            return
        raise RuntimeError("webbrowser did not accept the URL")
    except Exception as exc:
        errors.append(exc)

    raise RuntimeError("; ".join(str(e) for e in errors))


def open_local_html(p: Path) -> bool:
    """
    Open a local HTML report in the default browser.

    Tries platform-native openers first (most reliable for file:// pages),
    then falls back to the webbrowser module. Always prints the path so the
    user can open it manually if every opener fails.
    """
    import platform
    import subprocess
    import webbrowser

    path = p.resolve()
    if not path.exists():
        log.warning("Cannot open missing report: %s", path)
        print(f"Report not found: {path}")
        return False

    path_str = str(path)
    uri = path.as_uri()
    errors: list[str] = []
    system = platform.system()

    def _try(label: str, fn) -> bool:
        try:
            fn()
            log.info("Opened report via %s: %s", label, path_str)
            return True
        except Exception as exc:
            errors.append(f"{label}: {exc}")
            log.warning("Open via %s failed: %s", label, exc)
            return False

    opened = False
    if system == "Windows":
        opened = _try("windows-start", lambda: _open_windows(path_str))
    elif system == "Darwin":
        opened = _try(
            "open",
            lambda: subprocess.run(["open", path_str], check=True, timeout=15),
        )
    else:
        for cmd in (["xdg-open", path_str], ["gio", "open", path_str]):
            if opened:
                break

            def _xdg(c=cmd):
                subprocess.Popen(
                    c,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )

            opened = _try(cmd[0], _xdg)

    if not opened:

        def _open_webbrowser() -> None:
            if not webbrowser.open(uri, new=2):
                raise RuntimeError("webbrowser did not accept the URL")

        opened = _try(
            "webbrowser",
            _open_webbrowser,
        )

    # ASCII-friendly markers (Windows consoles often mishandle emoji)
    print(f"\n  Report ready: {path_str}")
    if opened:
        print("  Browser open requested (default app for .html).\n")
    else:
        print("  Could not auto-open the browser. Double-click the file above.")
        if errors:
            log.warning("Browser open attempts failed: %s", "; ".join(errors))
            print("  Errors: " + " | ".join(errors))
        print()
    return opened


def open_latest_report() -> bool:
    rpt = latest_report_path()
    if not rpt:
        print("No reports generated yet — run a fetch first.")
        return False
    return open_local_html(rpt)


def generate_html(
    arts: list[dict],
    report_date: str,
    health_data: dict[str, int],
    sched_warn: str,
    feeds_list: list[tuple[str, str, str]],
    page_type: str = "cyber",
    nav_targets: dict[str, str] | None = None,
) -> str:
    cfg = get_config()
    sev_ord = {"Critical": 0, "High": 1, "Normal": 2}
    arts = sorted(arts, key=lambda x: (-x["timestamp"], sev_ord[normalize_severity(x["severity"])]))

    total = len(arts)
    severities = [normalize_severity(a["severity"]) for a in arts]
    n_crit = severities.count("Critical")
    n_high = severities.count("High")
    n_norm = severities.count("Normal")
    sources = sorted({a["source"] for a in arts})
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    type_meta = {
        "cyber": ("&#x1F6E1;", "Cybersecurity Intelligence", "CyberDigest"),
        "network": ("&#x1F310;", "Networking &amp; Infrastructure", "NetDigest"),
        "cisco": ("&#x1F4CB;", "Cisco PSIRT Advisories", "CiscoAdvisories"),
        "fortinet": ("&#x1F6E1;", "Fortinet PSIRT Advisories", "FortiAdvisories"),
    }
    page_icon, page_label, page_title = type_meta.get(page_type, type_meta["cyber"])
    nav_targets = nav_targets or {}

    def _nav_href(page: str, prefix: str) -> str:
        target = nav_targets.get(page)
        if target:
            return h(target)
        exact = REPORTS_DIR / f"{prefix}{report_date}.html"
        if exact.exists():
            return h(exact.name)
        return h(_latest_report_name(prefix) or "index.html")

    nav_cyber = _nav_href("cyber", "cybersec_report_")
    nav_network = _nav_href("network", "network_report_")
    nav_cisco = _nav_href("cisco", "cisco_report_")
    nav_fortinet = _nav_href("fortinet", "fortinet_report_")

    alerts = ""
    if sched_warn:
        alerts += (
            '<div class="alert ai"><span class="ai-ico">&#8505;</span><span>'
            + h(sched_warn)
            + "</span></div>"
        )
    for name, _, _ in feeds_list:
        if health_data.get(name, 0) >= 5:
            alerts += (
                '<div class="alert ae"><span class="ai-ico">&#9888;</span>'
                "<span><strong>"
                + h(name)
                + "</strong> has failed "
                + str(health_data[name])
                + " consecutive times.</span></div>"
            )

    chips = ""
    for name, _, _ in feeds_list:
        fails = health_data.get(name, 0)
        dc = "ok" if fails == 0 else ("fail" if fails >= 3 else "warn")
        tip = "OK" if fails == 0 else f"{fails} failure(s)"
        chips += (
            f'<span class="chip" title="{h(tip)}"><span class="dot {dc}"></span>{h(name)}</span>'
        )

    cards_html = (
        "\n".join(_card(a) for a in arts)
        if arts
        else '<div class="empty"><span class="ico">&#128274;</span>No new articles since your last digest.</div>'
    )

    nav_links = (
        (
            ""
            if page_type == "cyber"
            else f'<a class="arch-btn" href="{nav_cyber}">&#x1F6E1; Cyber</a>'
        )
        + (
            ""
            if page_type == "network"
            else f'<a class="arch-btn" href="{nav_network}">&#x1F310; Network</a>'
        )
        + (
            ""
            if page_type == "cisco"
            else f'<a class="arch-btn" href="{nav_cisco}">&#x1F4CB; Cisco PSIRT</a>'
        )
        + (
            ""
            if page_type == "fortinet"
            else f'<a class="arch-btn" href="{nav_fortinet}">&#x1F6E1; Fortinet PSIRT</a>'
        )
    )
    footer_links = (
        (
            ""
            if page_type == "cyber"
            else f' &nbsp;&middot;&nbsp; <a href="{nav_cyber}">&#x1F6E1; Cyber</a>'
        )
        + (
            ""
            if page_type == "network"
            else f' &nbsp;&middot;&nbsp; <a href="{nav_network}">&#x1F310; Network</a>'
        )
        + (
            ""
            if page_type == "cisco"
            else f' &nbsp;&middot;&nbsp; <a href="{nav_cisco}">&#x1F4CB; Cisco PSIRT</a>'
        )
        + (
            ""
            if page_type == "fortinet"
            else f' &nbsp;&middot;&nbsp; <a href="{nav_fortinet}">&#x1F6E1; Fortinet PSIRT</a>'
        )
    )

    hdr_right = (
        f'<div class="hdr-right">'
        f'<span class="run-time">Generated {h(now_str)}</span>'
        + nav_links
        + '<a class="arch-btn" href="index.html">&#x1F4C1; Archive</a>'
        + "</div></header>"
    )

    body = (
        '<div class="wrap">'
        + '<header class="site-header"><div class="logo">'
        + f'<div class="logo-icon">{page_icon}</div>'
        + '<div class="logo-text"><h1>CyberDigest</h1>'
        + f'<div class="tag">{page_label} &middot; {h(report_date)}</div>'
        + "</div></div>"
        + hdr_right
        + '<div class="stats-bar">'
        + '<div class="scard"><div class="snum">'
        + str(total)
        + '</div><div class="slbl">Articles</div></div>'
        + '<div class="scard"><div class="snum red">'
        + str(n_crit)
        + '</div><div class="slbl">Critical</div></div>'
        + '<div class="scard"><div class="snum amb">'
        + str(n_high)
        + '</div><div class="slbl">High</div></div>'
        + '<div class="scard"><div class="snum grn">'
        + str(n_norm)
        + '</div><div class="slbl">Normal</div></div>'
        + '<div class="scard"><div class="snum">'
        + str(len(sources))
        + '</div><div class="slbl">Sources</div></div>'
        + "</div>"
        + alerts
        + '<div class="hp"><span class="hp-lbl">&#x1F4E1; Feeds</span>'
        + chips
        + "</div>"
        + '<div class="controls">'
        + '<input id="si" class="search" type="search" placeholder="Search articles, CVEs, sources…" autocomplete="off">'
        + '<div class="tabs">'
        + '<button class="tab on" data-f="All">All ('
        + str(total)
        + ")</button>"
        + '<button class="tab"    data-f="Critical">&#x1F534; Critical ('
        + str(n_crit)
        + ")</button>"
        + '<button class="tab"    data-f="High">&#x1F7E0; High ('
        + str(n_high)
        + ")</button>"
        + '<button class="tab"    data-f="Normal">&#x1F535; Normal ('
        + str(n_norm)
        + ")</button>"
        + "</div>"
        + '<select class="sort" id="ss">'
        + "<option value='newest' selected>Sort: Newest</option>"
        + "<option value='severity'>Sort: Severity</option>"
        + "<option value='oldest'>Sort: Oldest</option>"
        + "</select></div>"
        + '<div class="rbar" id="rb"></div>'
        + '<main class="grid" id="grid">'
        + cards_html
        + "</main>"
        + '<footer class="site-footer">'
        + "CyberDigest &mdash; self-healing &middot; next run in "
        + str(cfg["interval_days"])
        + " days"
        + " &nbsp;&middot;&nbsp; "
        + '<a href="index.html">Past Reports</a>'
        + footer_links
        + "</footer></div>"
        + "<script>"
        + _JS
        + "</script>"
    )
    return _page(page_title + " \u2014 " + report_date, _CSS, body)


def _prune_reports(groups: list[list[Path]], max_arch: int, archive_global: bool) -> None:
    if archive_global:
        all_reports: list[Path] = []
        for g in groups:
            all_reports.extend(g)
        all_reports.sort(key=_report_sort_key, reverse=True)
        for old in all_reports[max_arch:]:
            try:
                old.unlink()
            except OSError:
                pass
    else:
        for rpts in groups:
            ordered = sorted(rpts, key=lambda p: p.name, reverse=True)
            for old in ordered[max_arch:]:
                try:
                    old.unlink()
                except OSError:
                    pass


def generate_index_html() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    cfg = get_config()
    cyber_reports = sorted(REPORTS_DIR.glob("cybersec_report_*.html"), reverse=True)
    network_reports = sorted(REPORTS_DIR.glob("network_report_*.html"), reverse=True)
    cisco_reports = sorted(REPORTS_DIR.glob("cisco_report_*.html"), reverse=True)
    fortinet_reports = sorted(REPORTS_DIR.glob("fortinet_report_*.html"), reverse=True)

    max_arch = cfg["max_archived_reports"]
    archive_global = bool(cfg.get("archive_global", True))
    _prune_reports(
        [cyber_reports, network_reports, cisco_reports, fortinet_reports],
        max_arch,
        archive_global,
    )
    cyber_reports = sorted(REPORTS_DIR.glob("cybersec_report_*.html"), reverse=True)
    network_reports = sorted(REPORTS_DIR.glob("network_report_*.html"), reverse=True)
    cisco_reports = sorted(REPORTS_DIR.glob("cisco_report_*.html"), reverse=True)
    fortinet_reports = sorted(REPORTS_DIR.glob("fortinet_report_*.html"), reverse=True)

    def _make_rows(reports: list[Path], prefix: str, icon: str) -> str:
        rows = ""
        for i, r in enumerate(reports):
            dp = r.stem.replace(prefix, "")
            try:
                dt = datetime.strptime(dp, "%Y%m%d_%H%M")
                disp = dt.strftime("%B %d, %Y")
                t_str = dt.strftime("%I:%M %p")
            except ValueError:
                disp, t_str = dp, ""
            latest = (
                (
                    '<span style="font-size:9.5px;background:rgba(34,211,238,.15);color:#22d3ee;'
                    "padding:1px 7px;border-radius:999px;margin-left:7px;"
                    'border:1px solid rgba(34,211,238,.3)">Latest</span>'
                )
                if i == 0
                else ""
            )
            rows += (
                f'<a href="{h(r.name)}" class="rrow">'
                f'<span class="rico">{icon}</span>'
                f'<span class="rname">{h(disp)}{latest}</span>'
                f'<span class="rtime">{h(t_str)}</span></a>'
            )
        return rows

    cyber_rows = _make_rows(cyber_reports, "cybersec_report_", "&#x1F6E1;")
    network_rows = _make_rows(network_reports, "network_report_", "&#x1F310;")
    cisco_rows = _make_rows(cisco_reports, "cisco_report_", "&#x1F4CB;")
    fortinet_rows = _make_rows(fortinet_reports, "fortinet_report_", "&#x1F6E1;")

    latest_candidates: list[Path] = []
    for reports in (cyber_reports, network_reports, cisco_reports, fortinet_reports):
        if reports:
            latest_candidates.append(reports[0])
    latest_report = max(latest_candidates, key=_report_sort_key, default=None)
    latest_href = h(latest_report.name if latest_report else "index.html")
    total = len(cyber_reports) + len(network_reports) + len(cisco_reports) + len(fortinet_reports)

    body = (
        '<div class="wrap">'
        '<header class="site-header"><div class="logo">'
        '<div class="logo-icon">&#x1F4C1;</div>'
        '<div class="logo-text"><h1>CyberDigest Archive</h1>'
        f'<div class="tag">{total} past report(s)</div>'
        "</div></div></header>"
        '<div class="arch-section">'
        '<div class="arch-heading"><span class="arch-ico">&#x1F6E1;</span>Cybersecurity Intelligence</div>'
        '<div class="rlist">'
        + (cyber_rows or "<p class='no-rep'>No cybersecurity reports yet.</p>")
        + "</div></div>"
        '<div class="arch-section">'
        '<div class="arch-heading"><span class="arch-ico">&#x1F310;</span>Networking &amp; Infrastructure</div>'
        '<div class="rlist">'
        + (network_rows or "<p class='no-rep'>No networking reports yet.</p>")
        + "</div></div>"
        '<div class="arch-section">'
        '<div class="arch-heading"><span class="arch-ico">&#x1F4CB;</span>Cisco PSIRT Advisories</div>'
        '<div class="rlist">'
        + (cisco_rows or "<p class='no-rep'>No Cisco PSIRT reports yet.</p>")
        + "</div></div>"
        '<div class="arch-section">'
        '<div class="arch-heading"><span class="arch-ico">&#x1F6E1;</span>Fortinet PSIRT Advisories</div>'
        '<div class="rlist">'
        + (fortinet_rows or "<p class='no-rep'>No Fortinet PSIRT reports yet.</p>")
        + "</div></div>"
        f'<footer class="site-footer"><a href="{latest_href}">&#x2190; Back to latest</a></footer>'
        "</div>"
    )
    idx = _page("CyberDigest Archive", _CSS + _IDXCSS, body)
    dest = REPORTS_DIR / "index.html"
    tmp = REPORTS_DIR / "index.html.tmp"
    tmp.write_text(idx, encoding="utf-8")
    tmp.replace(dest)
