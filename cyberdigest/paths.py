"""Filesystem layout for CyberDigest."""

from __future__ import annotations

import os
from pathlib import Path

# Package root (cyberdigest/) and project root (repo / install dir)
PACKAGE_DIR = Path(__file__).resolve().parent
# Prefer project root (parent of package) so state lives next to news_agent.py
PROJECT_ROOT = PACKAGE_DIR.parent

# Allow Docker / advanced users to relocate all runtime data
_DATA_OVERRIDE = os.environ.get("CYBERDIGEST_DATA_DIR", "").strip()
DATA_DIR = Path(_DATA_OVERRIDE).expanduser().resolve() if _DATA_OVERRIDE else PROJECT_ROOT

REPORTS_DIR = DATA_DIR / "reports"
DB_FILE = DATA_DIR / "state.db"
LOG_FILE = DATA_DIR / "agent_log.txt"
STATUS_FILE = DATA_DIR / "status.txt"
HEARTBEAT_FILE = DATA_DIR / "heartbeat.txt"
LOCK_FILE = DATA_DIR / "agent.lock"

# Config: project root first, then data dir (secrets-friendly local override)
CONFIG_FILE = PROJECT_ROOT / "config.json"
CONFIG_LOCAL_FILE = PROJECT_ROOT / "config.local.json"
CONFIG_EXAMPLE_FILE = PROJECT_ROOT / "config.example.json"
FEEDS_FILE = PROJECT_ROOT / "feeds.yaml"

ASSETS_DIR = PACKAGE_DIR / "assets"
