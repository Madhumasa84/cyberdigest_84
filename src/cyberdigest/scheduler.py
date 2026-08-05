"""OS-native scheduling (cron / schtasks / launchd) with verification."""

from __future__ import annotations

import platform
import plistlib
import shlex
import subprocess
import sys
from pathlib import Path

from cyberdigest.logging_setup import log
from cyberdigest.paths import PROJECT_ROOT, SOURCE_ROOT

TASK_NAME = "CyberDigest"
LAUNCHD_LABEL = "com.cyberdigest"
CRON_MARKER = "# cyberdigest-managed"
_SUBPROCESS_TIMEOUT = 20


def _script_path() -> str | None:
    """Return the source-checkout launcher, or None for an installed wheel."""
    if SOURCE_ROOT is None:
        return None
    launcher = SOURCE_ROOT / "news_agent.py"
    return str(launcher) if launcher.is_file() else None


def _scheduled_command() -> list[str]:
    """Build a one-shot command that performs its own configured due check."""
    script_path = _script_path()
    target = [script_path] if script_path else ["-m", "cyberdigest"]
    return [sys.executable, *target, "--once", "--cli-only"]


def _legacy_cron_line(line: str) -> bool:
    lowered = line.lower()
    return "news_agent.py" in lowered or "-m cyberdigest" in lowered


def register_scheduler() -> bool:
    os_name = platform.system()
    command = _scheduled_command()
    try:
        if os_name == "Windows":
            task_command = subprocess.list2cmdline(command)
            res = subprocess.run(
                [
                    "schtasks",
                    "/Create",
                    "/TN",
                    TASK_NAME,
                    "/TR",
                    task_command,
                    "/SC",
                    "DAILY",
                    "/MO",
                    "1",
                    "/F",
                ],
                capture_output=True,
                text=True,
                timeout=_SUBPROCESS_TIMEOUT,
            )
            if res.returncode != 0:
                log.error(
                    "schtasks failed (%s): stdout=%s stderr=%s",
                    res.returncode,
                    res.stdout.strip(),
                    res.stderr.strip(),
                )
                return False
        elif os_name == "Darwin":
            payload = {
                "Label": LAUNCHD_LABEL,
                "ProgramArguments": command,
                "StartInterval": 86400,
                "WorkingDirectory": str(PROJECT_ROOT),
            }
            launch_agents = Path.home() / "Library" / "LaunchAgents"
            launch_agents.mkdir(parents=True, exist_ok=True)
            plist_path = launch_agents / f"{LAUNCHD_LABEL}.plist"
            plist_path.write_bytes(plistlib.dumps(payload, sort_keys=False))
            subprocess.run(
                ["launchctl", "unload", str(plist_path)],
                capture_output=True,
                timeout=_SUBPROCESS_TIMEOUT,
            )
            subprocess.run(
                ["launchctl", "load", str(plist_path)],
                check=True,
                capture_output=True,
                timeout=_SUBPROCESS_TIMEOUT,
            )
        elif os_name == "Linux":
            current = subprocess.run(
                ["crontab", "-l"],
                capture_output=True,
                text=True,
                timeout=_SUBPROCESS_TIMEOUT,
            )
            lines = [
                line
                for line in current.stdout.splitlines()
                if CRON_MARKER not in line and not _legacy_cron_line(line)
            ]
            command_text = " ".join(shlex.quote(part) for part in command)
            # Run a cheap due check every day. ``*/N`` in cron's day-of-month
            # field resets each month and is not a true N-day interval.
            lines.append(f"0 10 * * * {command_text} {CRON_MARKER}")
            subprocess.run(
                ["crontab", "-"],
                input="\n".join(lines) + "\n",
                text=True,
                check=True,
                timeout=_SUBPROCESS_TIMEOUT,
            )
        else:
            return False
        return verify_scheduler()
    except (OSError, subprocess.SubprocessError) as exc:
        log.error("Scheduler registration failed: %s", exc)
        return False


def verify_scheduler() -> bool:
    os_name = platform.system()
    try:
        if os_name == "Windows":
            res = subprocess.run(
                ["schtasks", "/query", "/TN", TASK_NAME],
                capture_output=True,
                text=True,
                timeout=_SUBPROCESS_TIMEOUT,
            )
            return res.returncode == 0 and TASK_NAME in res.stdout
        if os_name == "Darwin":
            res = subprocess.run(
                ["launchctl", "list"],
                capture_output=True,
                text=True,
                timeout=_SUBPROCESS_TIMEOUT,
            )
            return res.returncode == 0 and LAUNCHD_LABEL in res.stdout
        if os_name == "Linux":
            res = subprocess.run(
                ["crontab", "-l"],
                capture_output=True,
                text=True,
                timeout=_SUBPROCESS_TIMEOUT,
            )
            return res.returncode == 0 and (
                CRON_MARKER in res.stdout or _legacy_cron_line(res.stdout)
            )
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("Scheduler verify failed: %s", exc)
    return False


def uninstall_scheduler() -> bool:
    os_name = platform.system()
    try:
        if os_name == "Windows":
            res = subprocess.run(
                ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"],
                capture_output=True,
                timeout=_SUBPROCESS_TIMEOUT,
            )
            if res.returncode != 0:
                return False
        elif os_name == "Darwin":
            plist_path = Path.home() / "Library" / "LaunchAgents" / f"{LAUNCHD_LABEL}.plist"
            if plist_path.exists():
                subprocess.run(
                    ["launchctl", "unload", str(plist_path)],
                    capture_output=True,
                    timeout=_SUBPROCESS_TIMEOUT,
                )
                plist_path.unlink()
        elif os_name == "Linux":
            res = subprocess.run(
                ["crontab", "-l"],
                capture_output=True,
                text=True,
                timeout=_SUBPROCESS_TIMEOUT,
            )
            if res.returncode == 0:
                lines = [
                    line
                    for line in res.stdout.splitlines()
                    if CRON_MARKER not in line and not _legacy_cron_line(line)
                ]
                subprocess.run(
                    ["crontab", "-"],
                    input="\n".join(lines) + "\n",
                    text=True,
                    check=True,
                    timeout=_SUBPROCESS_TIMEOUT,
                )
        else:
            return False
        print("✔  OS scheduler removed.")
        return True
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"Uninstall error: {exc}")
        return False
