# View Subcommand & Read Cache — Design

**Status:** Approved (brainstorming), awaiting implementation plan
**Date:** 2026-07-04
**Scope:** Two related improvements to `taskdav` — a `view N` subcommand for a richer single-task display, and a 10-minute read cache to avoid redundant CalDAV fetches.

## Motivation

The `list` output is a single-line todo.txt rendering; the DESCRIPTION field (which may hold Markdown prose) is not shown. Users want to "open" a task to see everything CalDAV stores about it — including a rendered description.

Separately, every `taskdav` invocation calls `TodoList.get_tasks()`, which issues a REPORT query against the CalDAV server and returns every VTODO. For a read-mostly workflow (list, view, list, view), this round-trip dominates latency. A short-lived read cache removes the fetch on repeated reads.

## Decisions (from brainstorming)

1. **`view N` shows the full detail set** — every parsed field from `Task`, with the DESCRIPTION rendered as **Markdown** via Rich's `Markdown` renderer.
2. **Cache is TTL-only, no bypass flag.** Lifetime is 10 minutes. Invalidation is automatic on writes. No `--refresh` flag, no `refresh` subcommand (YAGNI).
3. **Approach A** (chosen over B/C): cache the raw VTODO data strings inside `get_tasks()`. Do not cache parsed dicts or the calendar URL.
4. **`view N` uses 1-indexed position** from `list`, matching `delete`.
5. **Cache key = `{calendar, include_completed}`** so `list` and `list -i` don't contaminate each other, and switching `TASK_CALENDAR` doesn't serve stale tasks from a different calendar.
6. **Invalidation on create and delete.** There is no edit command yet; delete is currently a stub (task.py:231) but will be wired to bust the cache so it's correct when implemented.
7. **Cache location:** `XDG_CACHE_HOME` if set, else `~/.cache/taskdav/`.

## Architecture

### What changes

| File | Change |
|------|--------|
| `taskdav.py` | Add `view` subcommand; route `list`/`view` through cache. |
| `task.py` | Add `TodoList.view_task(n)` and `Task.view()` presentation methods; add cache read/write/invalidate inside `get_tasks()` and `create_task`/`delete_task`. |

No new modules. `Task.__init__` signature is unchanged (still takes raw VDATA string), so the cache path can reconstruct `Task` objects without a second constructor.

### What does NOT change

- `Task` parsing logic — all `_parse_*` methods untouched.
- The module-level side effect in `taskdav.py` (client + `TodoList` constructed at import) remains. Caching `get_tasks()` reduces but does not eliminate import cost; `get_task_cal()` still runs two PROPFINDs on every import. This is a known limitation (see **Tradeoffs**); if it proves too slow, Approach B (cache the calendar URL) extends cleanly from this design.
- `old_task.py` — still dead reference code; not touched.

## Component design

### `view` subcommand

New Click command in `taskdav.py`:

```
@click.command(help="Show detailed view of a single task")
@click.argument("id")
def view(id):
    tdl.view_task(id)
```

Registered via `cli.add_command(view, name="view")`.

`TodoList.view_task(self, id)` (new, task.py):
- Calls `self.get_tasks()` (now cache-aware — see below).
- Resolves the task: `self.todos[int(id) - 1]`.
- Calls `task.view()`.

`Task.view(self)` (new, task.py):
- Prints a Rich `Panel` with the task SUMMARY as the title and `(A)`–`(Z)`/`HIGH`/`MEDIUM`/`LOW`/`None` priority as a subtitle.
- Inside the panel, a Rich `Table` (two columns: label, value) shows every parsed field: `status`, `due_date`, `start_date`, `completed_date`, `created`, `last_modified`, `percent`, `categories`, `task_class`, `uid`.
- The DESCRIPTION is rendered separately, below the table, via `rich.markdown.Markdown(self.description, ...)` — only if `description` is non-None. If absent, the section is omitted (not a blank placeholder).
- Dates are formatted `%Y-%m-%d` for display (matching `to_todo_txt`); `None` values render as `—` (em dash) so the table stays aligned.

### Read cache

**Cache file:** JSON at `{cache_dir}/tasks.json`, where `cache_dir` is:
- `$XDG_CACHE_HOME/taskdav/` if `XDG_CACHE_HOME` is set, else
- `~/.cache/taskdav/`

**File format:**
```json
{
  "calendar": "personal",
  "include_completed": false,
  "fetched_at": "2026-07-04T12:00:00",
  "raw_todos": ["BEGIN:VTODO ... END:VTODO", "..."]
}
```

`raw_todos` is the list of `todo.data` strings (exactly what `Task.__init__` consumes), preserving round-trip fidelity without serializing `vobject` objects.

**Cache lifecycle — `TodoList.get_tasks(self, include_completed=False)`:**
```
cache_path = <computed>
if cache exists and matches (calendar, include_completed) and age < 10 min:
    raw = json.load(cache_path)["raw_todos"]
    self.raw_todos = raw
    self.todos = [Task(s) for s in raw]
    return            # NO server call
# miss (expired, missing, or key mismatch):
self.raw_todos = self.calendar.todos(include_completed=include_completed)
self.todos = [Task(todo.data) for todo in self.raw_todos]
write cache file (calendar, include_completed, now, self.raw_todos)
```

Key-mismatch on `calendar` or `include_completed` is treated as a miss (not an error). Stale file is overwritten in place on the next miss.

**Invalidation — on every write path:**
- `TodoList.create_task` calls a new `self._invalidate_cache()` after `self.calendar.save_todo(...)` and before re-fetching. (The post-`save_todo` `get_tasks()` call that already exists will then repopulate the cache from the server.)
- `TodoList.delete_task` calls `self._invalidate_cache()` too. The actual `task.delete()` is still commented out (stub), but the invalidation is wired so the command is correct when the stub is replaced.
- `_invalidate_cache()` deletes the cache file if it exists; no error if missing. Idempotent.

**TTL check:** `age < 600 seconds`, where `age = (datetime.now() - fetched_at).total_seconds()`. `fetched_at` is parsed from the file via `datetime.fromisoformat`. If the file is corrupt or unparseable, treat as a miss (delete + refetch) rather than raise.

## Tradeoffs / known limitations

- **Import still calls `get_task_cal()`.** This is two PROPFINDs (principal + calendar list) on every invocation, not cached. If this proves to be a meaningful share of latency, Approach B (cache the calendar URL so we build `caldav.Calendar(client, url=...)` directly) extends cleanly — but it's YAGNI until measured.
- **Position-based IDs are fragile.** `view N` and `delete N` both index into `self.todos`, whose order depends on the server's response order. If the server reorders between calls, `N` may point at a different task. Out of scope to fix here (would require switching to UID-based addressing); flagged so it's a conscious omission.
- **No cache size bound.** A 10-minute TTL with overwrite-on-miss means at most one stale file per (calendar, include_completed) tuple — effectively one file. No eviction policy needed.
- **Cache is per-host** (because `~/.cache` is local). Multiple machines using the same CalDAV account each maintain their own cache; a write on host A doesn't invalidate host B's cache. Acceptable for a personal CLI.
- **Markdown renderer on plain-text DESCRIPTION.** If your DESCRIPTION is actually plain text (RFC 5545 default), `rich.markdown.Markdown` still renders it fine — plain text is a subset of Markdown. No fallback path needed.

## Testing

No tests exist yet (`pyproject.toml` has `pytest` as a dev dep but no test files). The plan should include minimal unit tests for the cache logic (pure functions, no server):

- Cache hit/miss/expiry/invalidation, tested by monkeypatching the file path to a `tmp_path` and faking `calendar.todos()`.
- `Task.view()` output shape — smoke test that it doesn't raise with a minimal VTODO and with a VTODO lacking a DESCRIPTION.
- `view N` resolves the same index `delete N` does (consistency test).

Module-level side effects in `taskdav.py` (the `client = caldav.DAVClient(...)` and `tdl = TodoList(client)` at import) make importing the CLI module hit the network. Tests for the CLI commands must mock `caldav.DAVClient` and the `TodoList` constructor at import time. The cache tests can import `task.py` directly (no module-level side effects in that file's top level) and exercise `TodoList` by injecting a fake client.

## Out of scope

- Edit command (not requested; invalidation hooks ready for when it is).
- UID-based addressing to replace position IDs.
- Caching the calendar URL (Approach B — deferred until import latency is measured and `get_task_cal` proven slow).
- `--refresh` flag or `refresh` subcommand (explicitly rejected in brainstorming).
- Tests for the actual CalDAV network round-trip (out of scope; the value of this change is measurable only against a live server).
