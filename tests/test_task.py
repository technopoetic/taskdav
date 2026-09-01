import os
import json
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from task import Task, TodoList, recurrence_to_rrule, rrule_to_recurrence

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

SAMPLE_VTODO_RECURRING = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//test//EN
BEGIN:VTODO
UID:test-uid-3
SUMMARY:Job pipeline update
STATUS:NEEDS-ACTION
DUE;VALUE=DATE:20260904
RRULE:FREQ=WEEKLY;INTERVAL=1
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


def test_cache_miss_writes_file(monkeypatch, tmp_path):
    cache_file = tmp_path / "tasks.json"
    monkeypatch.setattr(TodoList, "_cache_path", lambda self: str(cache_file))
    tdl, _ = make_fake_todo_list([SAMPLE_VTODO_FULL])
    assert cache_file.exists()
    data = json.loads(cache_file.read_text())
    assert data["calendar"] == "test_cal"
    assert data["include_completed"] is False
    assert len(data["raw_todos"]) == 1
    assert "Buy milk" in data["raw_todos"][0]


def test_cache_hit_avoids_server_call(monkeypatch, tmp_path):
    cache_file = tmp_path / "tasks.json"
    monkeypatch.setattr(TodoList, "_cache_path", lambda self: str(cache_file))
    tdl, fake_cal = make_fake_todo_list([SAMPLE_VTODO_FULL])
    call_count_after_init = fake_cal.todos.call_count
    tdl.get_tasks()
    assert fake_cal.todos.call_count == call_count_after_init
    assert tdl.todos[0].summary == "Buy milk"


def test_cache_expired_triggers_miss(monkeypatch, tmp_path):
    cache_file = tmp_path / "tasks.json"
    monkeypatch.setattr(TodoList, "_cache_path", lambda self: str(cache_file))
    tdl, fake_cal = make_fake_todo_list([SAMPLE_VTODO_FULL])
    call_count = fake_cal.todos.call_count
    data = json.loads(cache_file.read_text())
    data["fetched_at"] = (datetime.now() - timedelta(seconds=660)).isoformat()
    cache_file.write_text(json.dumps(data))
    tdl.get_tasks()
    assert fake_cal.todos.call_count == call_count + 1


def test_cache_key_mismatch_triggers_miss(monkeypatch, tmp_path):
    cache_file = tmp_path / "tasks.json"
    monkeypatch.setattr(TodoList, "_cache_path", lambda self: str(cache_file))
    tdl, fake_cal = make_fake_todo_list([SAMPLE_VTODO_FULL])
    call_count = fake_cal.todos.call_count
    tdl.get_tasks(include_completed=True)
    assert fake_cal.todos.call_count == call_count + 1
    call_count_after_miss = fake_cal.todos.call_count
    tdl.get_tasks(include_completed=True)
    assert fake_cal.todos.call_count == call_count_after_miss
    assert tdl.todos[0].summary == "Buy milk"


def test_cache_corrupt_file_triggers_miss(monkeypatch, tmp_path):
    cache_file = tmp_path / "tasks.json"
    cache_file.write_text("not valid json {{{")
    monkeypatch.setattr(TodoList, "_cache_path", lambda self: str(cache_file))
    tdl, fake_cal = make_fake_todo_list([SAMPLE_VTODO_FULL])
    assert fake_cal.todos.call_count == 1
    assert tdl.todos[0].summary == "Buy milk"
    data = json.loads(cache_file.read_text())
    assert "Buy milk" in data["raw_todos"][0]


def test_cache_nondict_json_triggers_miss(monkeypatch, tmp_path):
    cache_file = tmp_path / "tasks.json"
    cache_file.write_text("[]")
    monkeypatch.setattr(TodoList, "_cache_path", lambda self: str(cache_file))
    tdl, fake_cal = make_fake_todo_list([SAMPLE_VTODO_FULL])
    assert fake_cal.todos.call_count == 1
    assert tdl.todos[0].summary == "Buy milk"


def test_create_task_invalidates_cache(monkeypatch, tmp_path):
    cache_file = tmp_path / "tasks.json"
    monkeypatch.setattr(TodoList, "_cache_path", lambda self: str(cache_file))
    tdl, fake_cal = make_fake_todo_list([SAMPLE_VTODO_FULL])
    calls_after_init = fake_cal.todos.call_count
    tdl.create_task("(A) new task +test")
    assert fake_cal.todos.call_count == calls_after_init + 1


def test_delete_task_invalidates_cache(monkeypatch, tmp_path):
    cache_file = tmp_path / "tasks.json"
    monkeypatch.setattr(TodoList, "_cache_path", lambda self: str(cache_file))
    tdl, _ = make_fake_todo_list([SAMPLE_VTODO_FULL])
    assert cache_file.exists()
    tdl.delete_task(1)
    assert not cache_file.exists()


def test_task_view_with_description(capsys):
    task = Task(SAMPLE_VTODO_FULL)
    task.view()
    out = capsys.readouterr().out
    assert "Buy milk" in out
    assert "Status" in out
    assert "HIGH" in out
    assert "Due" in out
    assert "2% milk" in out
    assert "groceries" in out
    assert "errands" in out


def test_task_view_without_description(capsys):
    task = Task(SAMPLE_VTODO_NO_DESC)
    task.view()
    out = capsys.readouterr().out
    assert "No description task" in out
    assert "Status" in out
    assert "—" in out


def test_view_task_resolves_correct_index(monkeypatch, tmp_path):
    cache_file = tmp_path / "tasks.json"
    monkeypatch.setattr(TodoList, "_cache_path", lambda self: str(cache_file))
    tdl, _ = make_fake_todo_list([SAMPLE_VTODO_FULL, SAMPLE_VTODO_NO_DESC])

    viewed_uids = []

    def capture_view(self):
        viewed_uids.append(self.uid)

    monkeypatch.setattr(Task, "view", capture_view)

    tdl.view_task("1")
    assert viewed_uids == ["test-uid-1"]

    tdl.view_task("2")
    assert viewed_uids == ["test-uid-1", "test-uid-2"]

    spy = MagicMock(wraps=tdl.get_tasks)
    monkeypatch.setattr(tdl, "get_tasks", spy)
    tdl.view_task("1")
    spy.assert_called_once()


def test_recurrence_to_rrule_maps_units_and_intervals():
    assert recurrence_to_rrule("w") == "FREQ=WEEKLY"
    assert recurrence_to_rrule("1w") == "FREQ=WEEKLY"
    assert recurrence_to_rrule("+1w") == "FREQ=WEEKLY"
    assert recurrence_to_rrule("d") == "FREQ=DAILY"
    assert recurrence_to_rrule("2m") == "FREQ=MONTHLY;INTERVAL=2"
    assert recurrence_to_rrule("1y") == "FREQ=YEARLY"


def test_recurrence_to_rrule_rejects_invalid():
    with pytest.raises(ValueError, match="Invalid recurrence"):
        recurrence_to_rrule("weekly")
    with pytest.raises(ValueError, match="Invalid recurrence"):
        recurrence_to_rrule("1x")


def test_rrule_to_recurrence_round_trips():
    assert rrule_to_recurrence("FREQ=WEEKLY") == "w"
    assert rrule_to_recurrence("FREQ=MONTHLY;INTERVAL=2") == "2m"
    assert rrule_to_recurrence("FREQ=DAILY") == "d"


def test_rrule_to_recurrence_falls_back_to_raw_for_unsupported_parts():
    assert rrule_to_recurrence("FREQ=WEEKLY;BYDAY=FR") == "FREQ=WEEKLY;BYDAY=FR"
    assert rrule_to_recurrence(None) is None


def test_task_parses_recurrence_from_vtodo():
    task = Task(SAMPLE_VTODO_RECURRING)
    assert task.recurrence == "FREQ=WEEKLY;INTERVAL=1"


def test_task_without_recurrence_returns_none():
    task = Task(SAMPLE_VTODO_NO_DESC)
    assert task.recurrence is None


def test_task_view_shows_recurrence(capsys):
    Task(SAMPLE_VTODO_RECURRING).view()
    out = capsys.readouterr().out
    assert "Recurrence" in out
    assert "rec:w" in out


def test_parse_captures_recurrence():
    tdl = TodoList.__new__(TodoList)
    data = tdl.parse("(A) Job pipeline update +career rec:1w due:2026-09-04")
    assert data["recurrence"] == "1w"
    assert data["summary"] == "Job pipeline update"
    assert data["due_date"] == datetime(2026, 9, 4)


def test_create_task_writes_rrule(monkeypatch, tmp_path):
    cache_file = tmp_path / "tasks.json"
    monkeypatch.setattr(TodoList, "_cache_path", lambda self: str(cache_file))
    tdl, fake_cal = make_fake_todo_list([])

    tdl.create_task("(A) Job pipeline update +career rec:1w due:2026-09-04")

    saved = fake_cal.save_todo.call_args[0][0]
    assert "RRULE:FREQ=WEEKLY" in saved
    assert "DUE" in saved


def test_priority_to_int_maps_letters_and_digits():
    from task import priority_to_int

    assert priority_to_int("A") == 1
    assert priority_to_int("a") == 1
    assert priority_to_int("B") == 3
    assert priority_to_int("C") == 5
    assert priority_to_int("D") == 7
    assert priority_to_int("Z") == 9
    assert priority_to_int("5") == 5
    assert priority_to_int(None) == 9


def test_create_task_writes_numeric_priority(monkeypatch, tmp_path):
    cache_file = tmp_path / "tasks.json"
    monkeypatch.setattr(TodoList, "_cache_path", lambda self: str(cache_file))
    tdl, fake_cal = make_fake_todo_list([])

    tdl.create_task("(A) priority test")
    saved = fake_cal.save_todo.call_args[0][0]
    assert "PRIORITY:1" in saved

    tdl.create_task("no priority test")
    saved = fake_cal.save_todo.call_args[0][0]
    assert "PRIORITY:9" in saved
