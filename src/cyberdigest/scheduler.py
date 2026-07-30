"""OS-native scheduling (cron / schtasks / launchd) with verification."""

from __future__ import annotations

import platform
import subprocess
import sys
from pathlib import Path

from cyberdigest.config import get_config
from cyberdigest.logging_setup import log


def _script_path() -> str:
    # Prefer thin launcher so cron works after package split
    root = Path(__file__).resolve().parent.parent
    launcher = root / "news_agent.py"
    if launcher.exists():
        return str(launcher)
    return str(Path(__file__).resolve().parent / "__main__.py")


def _register_windows(script_path: str, py_exec: str, interval: int) -> bool:
    res = subprocess.run(
        [
            "schtasks",
            "/Create",
            "/TN",
            "CyberDigest",
            "/TR",
            f'"{py_exec}" "{script_path}"',
            "/SC",
            "DAILY",
            "/MO",
            str(interval),
            "/F",
        ],
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
        log.error(
            "schtasks failed (%s): stdout=%s stderr=%s",
            res.returncode,
            res.stdout.strip(),
            res.stderr.strip(),
        )
        return False
    return True


def _register_macos(script_path: str, py_exec: str, interval: int) -> bool:
    plist = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"'
        ' "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0"><dict>\n'
        "  <key>Label</key><string>com.cyberdigest</string>\n"
        "  <key>ProgramArguments</key><array>\n"
        f"    <string>{py_exec}</string>\n"
        f"    <string>{script_path}</string>\n"
        "  </array>\n"
        f"  <key>StartInterval</key><integer>{interval * 86400}</integer>\n"
        "  <key>RunAtLoad</key><true/>\n"
        "  <key>WorkingDirectory</key>\n"
        f"  <string>{Path(script_path).parent}</string>\n"
        "</dict></plist>\n"
    )
    pd = Path.home() / "Library" / "LaunchAgents"
    pd.mkdir(parents=True, exist_ok=True)
    pp = pd / "com.cyberdigest.plist"
    pp.write_text(plist)
    subprocess.run(["launchctl", "unload", str(pp)], capture_output=True)
    subprocess.run(["launchctl", "load", str(pp)], check=True, capture_output=True)
    return True


def _register_linux(script_path: str, py_exec: str, interval: int) -> bool:
    try:
        cur = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
    except Exception:
        cur = ""
    lines = [
        line
        for line in cur.splitlines()
        if "news_agent.py" not in line and "cyberdigest" not in line.lower()
    ]
    workdir = str(Path(script_path).parent)
    lines.append(
        f"0 10 */{interval} * * cd {workdir} && {py_exec} {script_path} --cli-only"
    )
    subprocess.run(
        ["crontab", "-"],
        input="\n".join(lines) + "\n",
        text=True,
        check=True,
    )
    return True


def register_scheduler() -> bool:
    os_name = platform.system()
    script_path = _script_path()
    py_exec = sys.executable
    interval = get_config()["interval_days"]
    try:
        if os_name == "Windows":
            if not _register_windows(script_path, py_exec, interval):
                return False
        elif os_name == "Darwin":
            _register_macos(script_path, py_exec, interval)
        elif os_name == "Linux":
            _register_linux(script_path, py_exec, interval)
        else:
            return False
        return verify_scheduler()
    except Exception as exc:
        log.error("Scheduler registration failed: %s", exc)
        return False


def verify_scheduler() -> bool:
    os_name = platform.system()
    try:
        if os_name == "Windows":
            res = subprocess.run(
                ["schtasks", "/query", "/TN", "CyberDigest"],
                capture_output=True,
                text=True,
            )
            return "CyberDigest" in res.stdout
        if os_name == "Darwin":
            res = subprocess.run(
                ["launchctl", "list"], capture_output=True, text=True
            )
            return "com.cyberdigest" in res.stdout
        if os_name == "Linux":
            res = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
            return "news_agent.py" in res.stdout or "cyberdigest" in res.stdout.lower()
    except Exception as exc:
        log.warning("Scheduler verify failed: %s", exc)
    return False


def uninstall_scheduler() -> None:
    os_name = platform.system()
    try:
        if os_name == "Windows":
            subprocess.run(
                ["schtasks", "/Delete", "/TN", "CyberDigest", "/F"],
                check=True,
                capture_output=True,
            )
        elif os_name == "Darwin":
            pp = Path.home() / "Library" / "LaunchAgents" / "com.cyberdigest.plist"
            if pp.exists():
                subprocess.run(["launchctl", "unload", str(pp)], capture_output=True)
                pp.unlink()
        elif os_name == "Linux":
            res = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
            if res.returncode == 0:
                lines = [
                    line
                    for line in res.stdout.splitlines()
                    if "news_agent.py" not in line and "cyberdigest" not in line.lower()
                ]
                subprocess.run(
                    ["crontab", "-"],
                    input="\n".join(lines) + "\n",
                    text=True,
                    check=True,
                )
        print("✔  OS scheduler removed.")
    except Exception as exc:
        print(f"Uninstall error: {exc}")
