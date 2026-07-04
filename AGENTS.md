# AGENTS.md — taskdav

CLI bridge between [todo.txt](https://github.com/todotxt/todo.txt)-style task syntax and a CalDAV server's VTODO calendar. Not a package — run as a script.

## Run

```bash
uv run taskdav.py list                       # list open tasks (todo.txt-style output)
uv run taskdav.py list -i                     # include completed
uv run taskdav.py create "(A) buy milk +groceries due:2026-07-10"
uv run taskdav.py delete 2                     # 1-indexed position from `list`
```

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
- **Test**: `uv run pytest` (dev dep — **no tests exist yet**)
- No lint/typecheck configured. Run `uv run black --check .` as a minimal gate.

## Architecture

- `taskdav.py` — Click CLI group (`cli`) with `list`, `create`, `delete`. Instantiates a CalDAV client and `TodoList` **at module import time** (module-level side effects), so merely importing `taskdav` opens a network connection to the CalDAV server. Testing requires mocking `caldav.DAVClient` / the `TodoList` constructor.
- `task.py` — `Task` wraps a parsed `vobject` VTODO and exposes todo.txt-style fields; `TodoList` owns the CalDAV client + calendar and the input parser (`TodoList.parse`). `TodoList.__init__` also calls `get_tasks()`, so construction hits the server too.
- `old_task.py` — legacy pure-todo.txt `Task` parser. **Not imported anywhere.** Treat as reference/dead code; don't wire new features through it.

## Gotchas

- **`vobject` is an explicit dep** (`vobject>=0.9.9` in `pyproject.toml`). caldav 3.x dropped vobject internally in favor of `icalendar`, but `task.py` uses `vobject.readOne()` / `vobject.newFromBehavior()` directly — so it must be declared separately. Removing it will `ImportError` at runtime.
- **`delete_task` is a stub** in `task.py:229` — the real `task.delete()` call is commented out. Don't assume `delete` works end-to-end.
- Priority input is a single char `(A)`–`(Z)` in the CLI string; `Task._parse_priority` maps numeric CalDAV priority (1–9) to `HIGH`/`MEDIUM`/`LOW` for display.
- `requirements/` and `.tool-versions` are **legacy artifacts** from the old asdf/direnv/pip-tools toolchain. Obsolete under uv+mise. Safe to delete once you've confirmed the migration works.
