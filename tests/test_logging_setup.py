from __future__ import annotations

import logging
import logging.handlers
import sys

import cyberdigest.paths as paths
from cyberdigest.logging_setup import setup_logging


def test_setup_logging_defaults(isolated_app):
    log = setup_logging()
    assert log.name == "cyberdigest"
    assert log.level == logging.INFO
    assert log.propagate is False
    assert len(log.handlers) == 2

    file_handler = None
    stream_handler = None
    for handler in log.handlers:
        if isinstance(handler, logging.handlers.RotatingFileHandler):
            file_handler = handler
        elif isinstance(handler, logging.StreamHandler):
            stream_handler = handler

    assert file_handler is not None
    assert str(paths.LOG_FILE) in file_handler.baseFilename
    assert file_handler.maxBytes == 5 * 1024 * 1024
    assert file_handler.backupCount == 3

    assert stream_handler is not None
    assert stream_handler.stream == sys.stdout
    assert stream_handler.level == logging.WARNING


def test_setup_logging_custom_level(isolated_app):
    log = setup_logging("DEBUG")
    assert log.level == logging.DEBUG
    # stream handler level is always WARNING
    stream_handler = [
        h
        for h in log.handlers
        if isinstance(h, logging.StreamHandler)
        and not isinstance(h, logging.handlers.RotatingFileHandler)
    ][0]
    assert stream_handler.level == logging.WARNING


def test_setup_logging_clears_existing_handlers(isolated_app):
    log1 = setup_logging()
    assert len(log1.handlers) == 2

    # Add a dummy handler to see if it gets cleared
    log1.addHandler(logging.NullHandler())
    assert len(log1.handlers) == 3

    log2 = setup_logging()
    assert log1 is log2
    assert len(log2.handlers) == 2


def test_setup_logging_creates_parent_dir(isolated_app, tmp_path, monkeypatch):
    import cyberdigest.paths as paths

    # Override LOG_FILE to be in a nested non-existent directory
    test_log_file = tmp_path / "deep" / "nested" / "dir" / "test.log"
    monkeypatch.setattr(paths, "LOG_FILE", test_log_file)

    assert not test_log_file.parent.exists()

    import cyberdigest.logging_setup as logging_setup

    monkeypatch.setattr(logging_setup, "LOG_FILE", test_log_file)

    setup_logging()

    assert test_log_file.parent.exists()
    assert test_log_file.parent.is_dir()
