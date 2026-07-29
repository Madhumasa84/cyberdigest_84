"""Rotating file + console logging."""

from __future__ import annotations

import logging
import logging.handlers
import sys

from cyberdigest.paths import LOG_FILE


def setup_logging(level: str = "INFO") -> logging.Logger:
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
    log = logging.getLogger("cyberdigest")
    log.handlers.clear()
    log.setLevel(getattr(logging, level.upper(), logging.INFO))
    log.propagate = False

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(fmt)
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    console.setLevel(logging.WARNING)
    log.addHandler(handler)
    log.addHandler(console)
    return log


log = setup_logging()
