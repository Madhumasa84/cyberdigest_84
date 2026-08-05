from pathlib import Path
from unittest.mock import Mock

import pytest

from cyberdigest.reports import first_available_report


def create_mock_path(exists_val: bool) -> Mock:
    mock_path = Mock(spec=Path)
    mock_path.exists.return_value = exists_val
    return mock_path


def test_first_available_report_empty():
    """Test with an empty list of paths."""
    assert first_available_report([]) is None


def test_first_available_report_none_exist():
    """Test with a list where no paths exist."""
    p1 = create_mock_path(False)
    p2 = create_mock_path(False)

    assert first_available_report([p1, p2]) is None


def test_first_available_report_some_exist():
    """Test with a list where some paths exist, should return the first existing one."""
    p1 = create_mock_path(False)
    p2 = create_mock_path(True)
    p3 = create_mock_path(True)

    result = first_available_report([p1, p2, p3])

    assert result is p2


def test_first_available_report_with_nones():
    """Test with a list containing None elements, should skip them safely."""
    p1 = None
    p2 = create_mock_path(False)
    p3 = create_mock_path(True)

    result = first_available_report([p1, p2, p3])

    assert result is p3
