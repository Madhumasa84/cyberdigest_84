import logging
import logging.handlers
import sys
from pathlib import Path
from unittest.mock import patch

from cyberdigest.logging_setup import setup_logging


def test_setup_logging_default(tmp_path: Path):
    test_log_file = tmp_path / "test.log"
    with patch("cyberdigest.logging_setup.LOG_FILE", test_log_file):
        logger = setup_logging()

        assert logger.name == "cyberdigest"
        assert logger.level == logging.INFO
        assert not logger.propagate

        assert len(logger.handlers) == 2

        handlers_types = {type(h) for h in logger.handlers}
        assert handlers_types == {logging.handlers.RotatingFileHandler, logging.StreamHandler}

        for handler in logger.handlers:
            if isinstance(handler, logging.handlers.RotatingFileHandler):
                assert handler.baseFilename == str(test_log_file.resolve())
                assert handler.maxBytes == 5 * 1024 * 1024
                assert handler.backupCount == 3
            elif isinstance(handler, logging.StreamHandler):
                assert handler.stream == sys.stdout
                assert handler.level == logging.WARNING


def test_setup_logging_custom_level(tmp_path: Path):
    with patch("cyberdigest.logging_setup.LOG_FILE", tmp_path / "test.log"):
        logger = setup_logging(level="debug")
        assert logger.level == logging.DEBUG


def test_setup_logging_invalid_level(tmp_path: Path):
    with patch("cyberdigest.logging_setup.LOG_FILE", tmp_path / "test.log"):
        # "UNKNOWN" is not in logging module, so it should default to logging.INFO
        logger = setup_logging(level="UNKNOWN")
        assert logger.level == logging.INFO
