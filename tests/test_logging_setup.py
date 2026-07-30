"""Tests for the logging setup module."""

from __future__ import annotations

import logging
import sys

from cyberdigest.logging_setup import setup_logging


def test_setup_logging_defaults(isolated_app):
    """Test setup_logging configures exactly two handlers with expected defaults."""
    log = setup_logging()

    assert log.name == "cyberdigest"
    assert not log.propagate
    assert log.level == logging.INFO

    handlers = log.handlers
    assert len(handlers) == 2

    file_handler = next(
        (h for h in handlers if isinstance(h, logging.handlers.RotatingFileHandler)), None
    )
    assert file_handler is not None
    assert file_handler.maxBytes == 5 * 1024 * 1024
    assert file_handler.backupCount == 3
    assert file_handler.encoding == "utf-8"

    stream_handler = next((h for h in handlers if type(h) is logging.StreamHandler), None)
    assert stream_handler is not None
    assert stream_handler.stream is sys.stdout
    assert stream_handler.level == logging.WARNING


def test_setup_logging_custom_level(isolated_app):
    """Test setup_logging configures correct logging level based on input."""
    log = setup_logging("DEBUG")
    assert log.level == logging.DEBUG

    log = setup_logging("error")
    assert log.level == logging.ERROR
