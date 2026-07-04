# View Subcommand & Read Cache Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `view N` subcommand that renders a single task's full field set (with Markdown DESCRIPTION) and a 10-minute read cache inside `get_tasks()` to avoid redundant CalDAV fetches.

**Architecture:** Cache stores raw VTODO data strings (not parsed objects) in a JSON file keyed on `(calendar, include_completed)` with a 600s TTL. Cache is invalidated on `create_task` and `delete_task`. The `view` command calls the cache-aware `get_tasks()` then renders a Rich panel for the task at the given 1-indexed position.

**Tech Stack:** Python 3.12, Click, Rich (Panel/Table/Markdown/Group), vobject, caldav, pytest, unittest.mock

**Spec:** `docs/specs/2026-07-04-view-and-read-cache-design.md`

---

## File Structure

| File | Responsibility | Action |
|------|---------------|--------|
| `task.py` | `Task` class (parsing + presentation) and `TodoList` class (CalDAV client + cache). Add cache helpers, cache-aware `get_tasks()`, invalidation on writes, `Task.view()`, `TodoList.view_task()`. | Modify |
| `taskdav.py` | Click CLI group. Add `view` subcommand + register it. | Modify |
| `tests/test_task.py` | All unit tests for cache logic, `Task.view()`, `view_task()`. Uses fake CalDAV client (MagicMock) — no network. | Create |
| `pyproject.toml` | Add `[tool.pytest.ini_options]` with `pythonpath = ["."]` so `from task import ...` resolves from `tests/`. | Modify |

---

## Task 1: Test infrastructure + cache path + invalidation helpers

**Files:**
- Modify: `pyproject.toml`
- Create: `tests/test_task.py`
- Modify: `task.py:1-9` (imports), `task.py:169-175` (TodoList class constants)

- [ ] **Step 1: Add pytest pythonpath config**

Add to `pyproject.toml` after the `[tool.black]` section:

```toml
[tool.pytest.ini_options]
pythonpath = ["."]
```

- [ ] **Step 2: Create test file with fixtures and helper**

Create `tests/test_task.py`:

```python
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
```

- [ ] **Step 3: Write tests for _cache_path and _invalidate_cache**

Append to `tests/test_task.py`:

```python
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
    cache_file.write_text('{"calendar": "test_cal", "include_completed": false, "fetched_at": "2026-07-04T12:00:00", "raw_todos": []}')
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
```

**Note:** These tests use `TodoList.__new__` (bypass `__init__`) because `_cache_path` and `_invalidate_cache` don't depend on instance state set by `__init__` — `_cache_path` reads only env vars. This avoids constructing a TodoList (which would call `get_tasks()` and, after Task 2, write to the real cache path). Tests in Tasks 2-5 that need a fully-constructed TodoList use `make_fake_todo_list` with `_cache_path` monkeypatched to `tmp_path` first.

- [ ] **Step 4: Run tests to verify they fail**

Run: `uv run pytest tests/test_task.py -v`
Expected: FAIL with `AttributeError: 'TodoList' object has no attribute '_cache_path'`

- [ ] **Step 5: Implement _cache_path, _invalidate_cache, and add imports**

In `task.py`, add `from datetime import datetime` to the imports block at the top. The full imports section should read:

```python
import os

import vobject
import json
import re
import dateutil
from datetime import datetime

from rich import print
from rich.columns import Columns
```

Add `CACHE_TTL_SECONDS = 600` to the `TodoList` class constants (after `DATE_FMT` on line 175):

```python
class TodoList:
    PRIORITY_RE = re.compile(r"^\s*\(([0-9])\)")
    PROJECT_RE = re.compile(r"(\s+|^)\+([^\s]+)")
    CONTEXT_RE = re.compile(r"(\s+|^)@([^\s]+)")
    KEYVALUE_RE = re.compile(r"(\s+|^)([^\s]+):([^\s$]+)")
    DATE_RE = re.compile(r"^\s*([\d]{4}-[\d]{2}-[\d]{2})", re.ASCII)
    DATE_FMT = "%Y-%m-%d"
    CACHE_TTL_SECONDS = 600
```

Add `_cache_path` and `_invalidate_cache` methods to `TodoList`, between `get_task_cal` and `get_tasks`:

```python
    def _cache_path(self):
        cache_dir = os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache"))
        return os.path.join(cache_dir, "taskdav", "tasks.json")

    def _invalidate_cache(self):
        path = self._cache_path()
        if os.path.exists(path):
            os.remove(path)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_task.py -v`
Expected: 4 PASS

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml tests/test_task.py task.py
git commit -m "Add cache path and invalidation helpers with tests

Introduces _cache_path() (XDG_CACHE_HOME or ~/.cache/taskdav/)
and _invalidate_cache() (idempotent file deletion). Adds pytest
pythonpath config and test infrastructure with fake CalDAV client."
```

---

## Task 2: Cache read/write in get_tasks()

**Files:**
- Modify: `task.py:199-205` (`get_tasks` method)
- Modify: `tests/test_task.py` (append tests)

- [ ] **Step 1: Write cache behavior tests**

Append to `tests/test_task.py`:

```python
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


def test_cache_corrupt_file_triggers_miss(monkeypatch, tmp_path):
    cache_file = tmp_path / "tasks.json"
    cache_file.write_text("not valid json {{{")
    monkeypatch.setattr(TodoList, "_cache_path", lambda self: str(cache_file))
    tdl, fake_cal = make_fake_todo_list([SAMPLE_VTODO_FULL])
    assert fake_cal.todos.call_count >= 1
    assert tdl.todos[0].summary == "Buy milk"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_task.py -v -k "cache_miss or cache_hit or cache_expired or cache_key or cache_corrupt"`
Expected: FAIL — `get_tasks()` does not yet read or write cache; cache hit test fails because `todos` is called again; cache miss test fails because no file written.

- [ ] **Step 3: Implement _read_cache and _write_cache helpers**

Add these methods to `TodoList` between `_invalidate_cache` and `get_tasks`:

```python
    def _read_cache(self, path, include_completed):
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return None
        if data.get("calendar") != self.task_calendar:
            return None
        if data.get("include_completed") != include_completed:
            return None
        try:
            fetched_at = datetime.fromisoformat(data["fetched_at"])
        except (ValueError, KeyError):
            return None
        age = (datetime.now() - fetched_at).total_seconds()
        if age >= TodoList.CACHE_TTL_SECONDS:
            return None
        return data.get("raw_todos")

    def _write_cache(self, path, include_completed, raw_strings):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        data = {
            "calendar": self.task_calendar,
            "include_completed": include_completed,
            "fetched_at": datetime.now().isoformat(),
            "raw_todos": raw_strings,
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
```

- [ ] **Step 4: Modify get_tasks to use cache**

Replace the existing `get_tasks` method (lines 199-205) with:

```python
    def get_tasks(self, include_completed=False):
        if self.calendar is None:
            raise ValueError("No Calendar specified for Tasks.")

        cache_path = self._cache_path()
        cached = self._read_cache(cache_path, include_completed)
        if cached is not None:
            self.raw_todos = cached
            self.todos = [Task(s) for s in cached]
            return None

        self.raw_todos = self.calendar.todos(include_completed=include_completed)
        raw_strings = [todo.data for todo in self.raw_todos]
        self.todos = [Task(s) for s in raw_strings]
        self._write_cache(cache_path, include_completed, raw_strings)
        return None
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_task.py -v`
Expected: 9 PASS (4 from Task 1 + 5 cache tests)

- [ ] **Step 6: Commit**

```bash
git add task.py tests/test_task.py
git commit -m "Add 10-minute read cache to get_tasks()

Caches raw VTODO strings keyed on (calendar, include_completed)
with a 600s TTL. Cache hit reconstructs Task objects from stored
strings — no server call. Miss/expire/mismatch/corrupt all fall
through to a fresh fetch and overwrite the cache file."
```

---

## Task 3: Cache invalidation on create and delete

**Files:**
- Modify: `task.py:207-229` (`create_task`), `task.py:231-236` (`delete_task`)
- Modify: `tests/test_task.py` (append tests)

- [ ] **Step 1: Write invalidation tests**

Append to `tests/test_task.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_task.py -v -k "create_task_invalidates or delete_task_invalidates"`
Expected: FAIL — `create_task` does not call `_invalidate_cache` (call count doesn't increase); `delete_task` does not delete the cache file.

- [ ] **Step 3: Add invalidation to create_task and delete_task**

In `create_task`, add `self._invalidate_cache()` between `save_todo` and `get_tasks`:

```python
    def create_task(self, data):
        task_data = self.parse(data)

        task = vobject.newFromBehavior("vtodo")
        task.add("vtodo")
        task.add("summary").value = task_data.get("summary")
        if task_data.get("categories") is not None:
            task.add("categories").value = task_data.get("categories")
        if task_data.get("class") is not None:
            task.add("class").value = task_data.get("class")
        if task_data.get("description") is not None:
            task.add("description").value = task_data.get("description")
        if task_data.get("due_date") is not None:
            task.add("due").value = task_data.get("due_date")
        task.add("priority").value = task_data.get("priority", 9)
        if task_data.get("start_date") is not None:
            task.add("dtstart").value = task_data.get("start_date")
        if task_data.get("status") is not None:
            task.add("status").value = task_data.get("status")

        self.calendar.save_todo(task.serialize())
        self._invalidate_cache()
        self.get_tasks()
        return task
```

In `delete_task`, add `self._invalidate_cache()`:

```python
    def delete_task(self, id):
        task = self.todos[int(id) - 1]
        # print(task.serialize())
        # task.delete()
        self._invalidate_cache()
        ttype = type(task.data_dict)
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_task.py -v`
Expected: 11 PASS (9 from previous + 2 new)

- [ ] **Step 5: Commit**

```bash
git add task.py tests/test_task.py
git commit -m "Invalidate cache on create and delete

create_task busts cache before its post-save refetch so the
next get_tasks() repopulates from the server. delete_task busts
cache even though task.delete() is still stubbed — wired for
correctness when the stub is replaced."
```

---

## Task 4: Task.view() presentation

**Files:**
- Modify: `task.py:1-9` (Rich imports), `task.py:56-68` (add `view` after `to_todo_txt`)
- Modify: `tests/test_task.py` (append tests)

- [ ] **Step 1: Write view tests**

Append to `tests/test_task.py`:

```python
def test_task_view_with_description(capsys):
    task = Task(SAMPLE_VTODO_FULL)
    task.view()
    out = capsys.readouterr().out
    assert "Buy milk" in out
    assert "Status" in out
    assert "Priority" in out
    assert "Due" in out
    assert "2% milk" in out


def test_task_view_without_description(capsys):
    task = Task(SAMPLE_VTODO_NO_DESC)
    task.view()
    out = capsys.readouterr().out
    assert "No description task" in out
    assert "Status" in out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_task.py -v -k "task_view"`
Expected: FAIL with `AttributeError: 'Task' object has no attribute 'view'`

- [ ] **Step 3: Add Rich imports and implement Task.view()**

In `task.py`, add the Rich imports. The full imports block should read:

```python
import os

import vobject
import json
import re
import dateutil
from datetime import datetime

from rich import print
from rich.columns import Columns
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown
from rich.console import Group
```

Add the `view` method to the `Task` class, after `to_todo_txt` (after line 68):

```python
    def view(self):
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column(style="bold cyan", no_wrap=True)
        table.add_column()

        def fmt_date(d):
            if d is None:
                return "—"
            return d.strftime("%Y-%m-%d")

        table.add_row("Status", self.status or "—")
        table.add_row("Priority", self.priority or "—")
        table.add_row("Due", fmt_date(self.due_date))
        table.add_row("Start", fmt_date(self.start_date))
        table.add_row("Completed", fmt_date(self.completed_date))
        table.add_row("Created", fmt_date(self.created))
        table.add_row("Last Modified", fmt_date(self.last_modified))
        table.add_row("Percent Complete", self.percent or "—")
        table.add_row(
            "Categories",
            ", ".join(self.categories) if self.categories else "—",
        )
        table.add_row("Class", self.task_class or "—")
        table.add_row("UID", self.uid or "—")

        elements = [table]
        if self.description is not None:
            elements.append(Markdown(self.description))

        panel = Panel(
            Group(*elements), title=self.summary, subtitle=self.priority or ""
        )
        print(panel)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_task.py -v -k "task_view"`
Expected: 2 PASS

- [ ] **Step 5: Commit**

```bash
git add task.py tests/test_task.py
git commit -m "Add Task.view() for detailed single-task display

Renders a Rich Panel with a field table (status, priority, due,
start, completed, created, last-modified, percent, categories,
class, uid) and the DESCRIPTION as Markdown below the table.
Dates format as %Y-%m-%d; None values show as em dash."
```

---

## Task 5: TodoList.view_task() + CLI view command

**Files:**
- Modify: `task.py` (add `view_task` to `TodoList`)
- Modify: `taskdav.py:46-55` (add `view` command + register)
- Modify: `tests/test_task.py` (append test)

- [ ] **Step 1: Write view_task test**

Append to `tests/test_task.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_task.py -v -k "view_task_resolves"`
Expected: FAIL with `AttributeError: 'TodoList' object has no attribute 'view_task'`

- [ ] **Step 3: Implement TodoList.view_task()**

Add `view_task` method to `TodoList`, after `delete_task`:

```python
    def view_task(self, id):
        self.get_tasks()
        task = self.todos[int(id) - 1]
        task.view()
```

- [ ] **Step 4: Add view command to taskdav.py**

In `taskdav.py`, add the `view` command after the `create` command (after line 50) and register it. The full set of commands + registrations should read:

```python
@click.command(help="Delete a task")
@click.argument("id")
def delete_task(id):
    tdl.get_tasks()
    tdl.delete_task(id)
    tdl.serialize()


@click.command(help="List all open Tasks")
@click.option(
    "--include-completed",
    "-i",
    is_flag=True,
    help="Include completed Tasks in the task list.",
)
def list_tasks(include_completed):
    try:
        tdl.get_tasks(include_completed)
        tdl.serialize()
    except ValueError as e:
        print(e)


@click.command(help="Create a new Task")
@click.argument("line")
def create(line):
    tdl.create_task(line)
    tdl.serialize()


@click.command(help="Show detailed view of a single task")
@click.argument("id")
def view(id):
    tdl.view_task(id)


cli.add_command(list_tasks, name="list")
cli.add_command(create)
cli.add_command(delete_task, name="delete")
cli.add_command(view)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_task.py -v`
Expected: 14 PASS (all tests)

- [ ] **Step 6: Commit**

```bash
git add task.py taskdav.py tests/test_task.py
git commit -m "Add view subcommand and TodoList.view_task()

view N calls the cache-aware get_tasks() then renders the task
at 1-indexed position N via Task.view(). The CLI command is a
thin wrapper over TodoList.view_task()."
```

---

## Task 6: Final verification

**Files:** None modified — verification only.

- [ ] **Step 1: Run black formatter**

Run: `uv run black .`
Expected: reformats if needed; no errors.

- [ ] **Step 2: Run black check**

Run: `uv run black --check .`
Expected: `All files already formatted` or no diff.

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: 14 PASS, 0 FAIL.

- [ ] **Step 4: Manual smoke test (optional, requires live CalDAV)**

If a CalDAV server is configured via credproxy env vars:

```bash
uv run taskdav.py list                    # should list tasks (cache miss, writes cache)
uv run taskdav.py list                    # should list tasks (cache hit, faster)
uv run taskdav.py view 1                  # should show Rich panel for task 1
```

- [ ] **Step 5: Commit if black reformatted anything**

```bash
git add -A
git commit -m "Format with black"
```

(Only if Step 1 changed files. If black made no changes, skip this step.)
