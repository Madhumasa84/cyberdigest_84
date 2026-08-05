"""Filesystem layout for source checkouts and installed packages."""

from __future__ import annotations

import os
import platform
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent


def _source_root() -> Path | None:
    """Return the repository root when running from a source checkout."""
    candidate = PACKAGE_DIR.parent.parent
    if (candidate / "news_agent.py").is_file() and (candidate / "pyproject.toml").is_file():
        return candidate
    return None


def _user_data_dir() -> Path:
    """Choose an OS-appropriate writable data directory for wheel installs."""
    system = platform.system()
    if system == "Windows":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        return Path(base).expanduser() / "CyberDigest" if base else Path.home() / "CyberDigest"
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "CyberDigest"
    base = os.environ.get("XDG_DATA_HOME", "").strip()
    return (
        Path(base).expanduser() / "cyberdigest"
        if base
        else Path.home() / ".local" / "share" / "cyberdigest"
    )


SOURCE_ROOT = _source_root()

# Allow Docker / advanced users to relocate all runtime data
_DATA_OVERRIDE = os.environ.get("CYBERDIGEST_DATA_DIR", "").strip()
DATA_DIR = (
    Path(_DATA_OVERRIDE).expanduser().resolve()
    if _DATA_OVERRIDE
    else SOURCE_ROOT or _user_data_dir()
)

# Config normally lives beside the checkout. Installed packages keep it with
# writable application data unless an explicit config directory is supplied.
_CONFIG_OVERRIDE = os.environ.get("CYBERDIGEST_CONFIG_DIR", "").strip()
CONFIG_DIR = (
    Path(_CONFIG_OVERRIDE).expanduser().resolve() if _CONFIG_OVERRIDE else SOURCE_ROOT or DATA_DIR
)
PROJECT_ROOT = SOURCE_ROOT or CONFIG_DIR

REPORTS_DIR = DATA_DIR / "reports"
DB_FILE = DATA_DIR / "state.db"
LOG_FILE = DATA_DIR / "agent_log.txt"
STATUS_FILE = DATA_DIR / "status.txt"
HEARTBEAT_FILE = DATA_DIR / "heartbeat.txt"
LOCK_FILE = DATA_DIR / "agent.lock"
RUN_LOCK_FILE = DATA_DIR / "run.lock"

CONFIG_FILE = CONFIG_DIR / "config.json"
CONFIG_LOCAL_FILE = CONFIG_DIR / "config.local.json"
CONFIG_EXAMPLE_FILE = CONFIG_DIR / "config.example.json"
FEEDS_FILE = CONFIG_DIR / "feeds.yaml"

ASSETS_DIR = PACKAGE_DIR / "assets"
