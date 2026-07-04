import os
import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from task import Task, TodoList

SAMPLE_VTODO_FULL = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//test//EN
BEGIN:VTODO
UID:test-uid-1
SUMMARY:Buy milk
DESCRIPTION:Pick up **2% milk** from the store.
PRIORITY:1
STATUS:NEEDS-ACTION
CATEGORIES:groceries,errands
DUE;VALUE=DATE:20260710
DTSTART;VALUE=DATE:20260705
CREATED:20260701T120000Z
LAST-MODIFIED:20260703T140000Z
PERCENT-COMPLETE:50
END:VTODO
END:VCALENDAR
"""

SAMPLE_VTODO_NO_DESC = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//test//EN
BEGIN:VTODO
UID:test-uid-2
SUMMARY:No description task
END:VTODO
END:VCALENDAR
"""


def make_fake_todo_list(raw_vtodo_strings):
    """Build a TodoList backed by a fake CalDAV client + calendar.

    raw_vtodo_strings: list of VCALENDAR-wrapped VTODO string blobs.
    Returns (tdl, fake_cal) where fake_cal is the MagicMock calendar.
    """
    fake_todos = [MagicMock(data=s) for s in raw_vtodo_strings]
    fake_cal = MagicMock()
    fake_cal.name = "test_cal"
    fake_cal.todos.return_value = fake_todos
    client = MagicMock()
    client.principal().calendars.return_value = [fake_cal]
    with patch.dict(os.environ, {"TASK_CALENDAR": "test_cal"}):
        tdl = TodoList(client)
    return tdl, fake_cal


def test_cache_path_uses_xdg(monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", "/tmp/fake-xdg")
    tdl = TodoList.__new__(TodoList)
    assert tdl._cache_path() == "/tmp/fake-xdg/taskdav/tasks.json"


def test_cache_path_defaults_to_home(monkeypatch):
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    tdl = TodoList.__new__(TodoList)
    expected = os.path.join(os.path.expanduser("~/.cache"), "taskdav", "tasks.json")
    assert tdl._cache_path() == expected


def test_invalidate_cache_deletes_file(monkeypatch, tmp_path):
    cache_file = tmp_path / "tasks.json"
    cache_file.write_text(
        '{"calendar": "test_cal", "include_completed": false, "fetched_at": "2026-07-04T12:00:00", "raw_todos": []}'
    )
    tdl = TodoList.__new__(TodoList)
    monkeypatch.setattr(TodoList, "_cache_path", lambda self: str(cache_file))
    tdl._invalidate_cache()
    assert not cache_file.exists()


def test_invalidate_cache_idempotent(monkeypatch, tmp_path):
    cache_file = tmp_path / "tasks.json"
    tdl = TodoList.__new__(TodoList)
    monkeypatch.setattr(TodoList, "_cache_path", lambda self: str(cache_file))
    tdl._invalidate_cache()
    assert not cache_file.exists()
