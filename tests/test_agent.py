import os
import re

from cyberdigest import paths
from cyberdigest.agent import write_status


def test_write_status(isolated_app, monkeypatch):
    """Test that write_status correctly formats and writes to STATUS_FILE and HEARTBEAT_FILE."""
    monkeypatch.setattr(os, "getpid", lambda: 12345)

    ok, fail, found = 10, 2, 5

    write_status(ok, fail, found)

    status_content = paths.STATUS_FILE.read_text(encoding="utf-8")
    heartbeat_content = paths.HEARTBEAT_FILE.read_text(encoding="utf-8")

    # Assert contents
    assert re.search(r"Last Attempt: \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", status_content)
    assert f"Feeds OK    : {ok}\n" in status_content
    assert f"Feeds Failed: {fail}\n" in status_content
    assert f"New Articles: {found}\n" in status_content
    assert "PID         : 12345\n" in status_content

    assert re.search(r"Agent awoke at: \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", heartbeat_content)
