#!/usr/bin/env python3
"""
CyberDigest launcher (backward-compatible entry point).

Implementation lives in the `cyberdigest` package. This file remains so that:
  - existing start.sh / start.bat / cron / docs keep working
  - `python news_agent.py` behaves as before
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on sys.path when launched as a script
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from cyberdigest.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
