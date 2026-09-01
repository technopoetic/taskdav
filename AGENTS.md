# AGENTS.md — taskdav

CLI bridge between [todo.txt](https://github.com/todotxt/todo.txt)-style task syntax and a CalDAV server's VTODO calendar. Not a package — run as a script.

## Run

```bash
uv run taskdav.py list                       # list open tasks (todo.txt-style output)
uv run taskdav.py list -i                     # include completed
uv run taskdav.py view 1                      # detailed view of task 1 (Rich panel + Markdown)
uv run taskdav.py create "(A) buy milk +groceries due:2026-07-10"
uv run taskdav.py create "(A) weekly review +career rec:1w due:2026-09-04"   # recurring
uv run taskdav.py delete 2                     # 1-indexed position from `list`
```

**Recurrence** (added 2026-09): `rec:` tag in create strings, todo.txt-style —
optional count + `d`/`w`/`m`/`y` (`w`, `1w`, `+2m`). Stored as a VTODO `RRULE`
(FREQ/INTERVAL). Recurring VTODOs anchor on `due:` — always set a due date.
Display round-trips (`list`/`view` show `rec:w`); RRULEs with parts other than
FREQ/INTERVAL (e.g. BYDAY created elsewhere) display as the raw RRULE.
Helpers live in `task.py`: `recurrence_to_rrule`, `rrule_to_recurrence`.
**Server limitation (Mailbox.org/Open-Xchange): the CalDAV server silently
strips RRULE from VTODOs on PUT** — recurring VTODOs are not persisted there.
VTODO recurrence works against RFC-compliant servers only. For server-side
recurring items on Mailbox.org, use a VEVENT with RRULE (verified working
2026-09) — e.g. the weekly job-pipeline-update event on the Calendar.

Requires env vars: `CALDAV_URL`, `TASK_USERNAME`, `TASK_PWORD`, `TASK_CALENDAR`. Provisioned via credproxy — never hardcode or commit credentials.

## Toolchain

- **mise**: `mise.toml` pins Python 3.12. mise auto-activates on dir entry.
- **uv**: `pyproject.toml` declares deps; `uv.lock` is the lockfile. `uv sync` creates `.venv/`.
  ```bash
  uv sync                   # create/update .venv + install all deps (incl. dev)
  uv add <package>          # add a runtime dep
  uv add --group dev <pkg>  # add a dev dep
  ```
- No `setup.py` / `Makefile`. No packaging. Script-only — `uv run taskdav.py ...`.

## Verify

- **Format**: `uv run black .` (formatter; dev dep). Config in `pyproject.toml` `[tool.black]`.
- **Test**: `uv run python -m pytest` (dev dep — 24 tests in `tests/test_task.py`). Config: `[tool.pytest.ini_options]` with `pythonpath = ["."]`. Gotcha (2026-09): bare `uv run pytest` resolves to the global `~/.local/bin/pytest`, which lacks project deps (vobject ImportError). Always use `uv run python -m pytest`.
- No lint/typecheck configured. Run `uv run black --check .` as a minimal gate.

## Architecture

- `taskdav.py` — Click CLI group (`cli`) with `list`, `create`, `delete`, `view`. Instantiates a CalDAV client and `TodoList` **at module import time** (module-level side effects), so merely importing `taskdav` opens a network connection to the CalDAV server. Testing requires mocking `caldav.DAVClient` / the `TodoList` constructor.
- `task.py` — `Task` wraps a parsed `vobject` VTODO and exposes todo.txt-style fields; `TodoList` owns the CalDAV client + calendar and the input parser (`TodoList.parse`). `TodoList.__init__` also calls `get_tasks()`, so construction hits the server too. `TodoList` also owns the read cache (`_cache_path`, `_read_cache`, `_write_cache`, `_invalidate_cache`) — see "Read cache" below.
- `old_task.py` — legacy pure-todo.txt `Task` parser. **Not imported anywhere.** Treat as reference/dead code; don't wire new features through it.

## Read cache

`TodoList.get_tasks()` caches raw VTODO strings (the `todo.data` blobs from `calendar.todos()`) to a JSON file at `$XDG_CACHE_HOME/taskdav/tasks.json` (or `~/.cache/taskdav/tasks.json`). Keyed on `(calendar, include_completed)` with a 600s TTL (`CACHE_TTL_SECONDS`). Invalidated on `create_task` and `delete_task`. Miss/expiry/mismatch/corrupt all fall through to a fresh fetch and overwrite. Caching the raw strings (not parsed dicts) avoids a second `Task` constructor — `Task.__init__` just re-parses the stored VDATA.

## Gotchas

- **`vobject` is an explicit dep** (`vobject>=0.9.9` in `pyproject.toml`). caldav 3.x dropped vobject internally in favor of `icalendar`, but `task.py` uses `vobject.readOne()` / `vobject.newFromBehavior()` directly — so it must be declared separately. Removing it will `ImportError` at runtime.
- **`delete_task` is a stub** in `task.py` — the real `task.delete()` call is commented out. Don't assume `delete` works end-to-end. The cache invalidation is wired for correctness when the stub is replaced.
- Priority input is a single char `(A)`–`(Z)` in the CLI string; `Task._parse_priority` maps numeric CalDAV priority (1–9) to `HIGH`/`MEDIUM`/`LOW` for display. In `Task.view()`, priority appears in the Panel subtitle (not the field table).
- **Testing pattern**: `TodoList.__init__` calls `get_task_cal()` + `get_tasks()` and hits the network on construction. Two patterns in `tests/test_task.py`: (1) stateless methods (`_cache_path`, `_invalidate_cache`) use `TodoList.__new__` to skip `__init__` entirely; (2) full construction uses `make_fake_todo_list(raw_vtodo_strings)` which builds a MagicMock CalDAV client + calendar. Monkeypatch `_cache_path` to `tmp_path` before construction to avoid writing to the real cache.
- `requirements/` and `.tool-versions` are **legacy artifacts** from the old asdf/direnv/pip-tools toolchain. Obsolete under uv+mise. Safe to delete once you've confirmed the migration works.
