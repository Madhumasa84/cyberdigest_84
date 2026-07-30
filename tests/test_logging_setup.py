import logging
import logging.handlers

from cyberdigest.logging_setup import setup_logging


def test_setup_logging_default(isolated_app):
    """Test setup_logging with default level (INFO)."""
    log = setup_logging()

    assert log.name == "cyberdigest"
    assert log.level == logging.INFO
    assert not log.propagate

    # Verify handlers
    assert len(log.handlers) == 2

    file_handler = next(
        h for h in log.handlers if isinstance(h, logging.handlers.RotatingFileHandler)
    )
    console_handler = next(
        h
        for h in log.handlers
        if isinstance(h, logging.StreamHandler)
        and not isinstance(h, logging.handlers.RotatingFileHandler)
    )

    assert file_handler.maxBytes == 5 * 1024 * 1024
    assert file_handler.backupCount == 3
    assert console_handler.level == logging.WARNING


def test_setup_logging_custom_level(isolated_app):
    """Test setup_logging with a custom level."""
    log = setup_logging("DEBUG")
    assert log.level == logging.DEBUG


def test_setup_logging_clears_existing_handlers(isolated_app):
    """Test that setting up logging clears any existing handlers."""
    log = setup_logging()
    assert len(log.handlers) == 2

    # Add a dummy handler to simulate existing handlers
    dummy_handler = logging.NullHandler()
    log.addHandler(dummy_handler)
    assert len(log.handlers) == 3

    # Call setup_logging again, which should clear handlers and re-add the 2 default ones
    log = setup_logging()
    assert len(log.handlers) == 2
    assert dummy_handler not in log.handlers
