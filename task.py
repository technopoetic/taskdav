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

RECURRENCE_UNITS = {"d": "DAILY", "w": "WEEKLY", "m": "MONTHLY", "y": "YEARLY"}
FREQ_TO_UNIT = {freq: unit for unit, freq in RECURRENCE_UNITS.items()}
# CalDAV PRIORITY is an integer (1 highest, 0/absent undefined). CLI letters map onto
# the display buckets in Task._parse_priority (<=4 HIGH, 5 MEDIUM, >=6 LOW).
LETTER_PRIORITY_TO_INT = {"A": 1, "B": 3, "C": 5, "D": 7}


def priority_to_int(priority):
    if priority is None:
        return 9
    value = str(priority).upper()
    if value.isdigit():
        return min(9, max(1, int(value)))
    return LETTER_PRIORITY_TO_INT.get(value, 9)


def recurrence_to_rrule(recurrence):
    """Convert a todo.txt-style rec: value (e.g. '1w', 'w', '+2m') to an RRULE string."""
    match = re.fullmatch(r"([+-]?\d+)?([dwmy])", str(recurrence).strip().lower())
    if not match:
        raise ValueError(
            f"Invalid recurrence: {recurrence!r} (expected optional count + d/w/m/y, e.g. 'w', '1w', '2m')"
        )
    interval = int(match.group(1) or 1)
    parts = [f"FREQ={RECURRENCE_UNITS[match.group(2)]}"]
    if interval > 1:
        parts.append(f"INTERVAL={interval}")
    return ";".join(parts)


def rrule_to_recurrence(rrule):
    """Convert an RRULE string back to rec: short form. Falls back to the raw RRULE for anything we did not create."""
    if not rrule:
        return None
    keys = {}
    for part in str(rrule).split(";"):
        if "=" in part:
            key, value = part.split("=", 1)
            keys[key] = value
    unit = FREQ_TO_UNIT.get(keys.get("FREQ", ""))
    if unit is None or set(keys) - {"FREQ", "INTERVAL"}:
        return str(rrule)
    interval = int(keys.get("INTERVAL", 1))
    return f"{interval}{unit}" if interval > 1 else unit


class Task:
    def __init__(self, vdata):
        self.data_dict = vobject.readOne(vdata)

        dates = self._parse_dates()
        self.categories = self._parse_categories()
        self.completed_date = dates[2]
        self.created = self._parse_created()
        self.description = self._parse_description()
        self.last_modified = self._parse_updated()
        self.percent = self._parse_percent()
        self.priority = self._parse_priority()
        self.recurrence = self._parse_recurrence()
        self.status = self._parse_status()
        self.summary = self._parse_summary()
        self.task_class = self._parse_class()
        self.start_date = dates[0]
        self.due_date = dates[1]
        self.uid = self._parse_uid()

    def pp(self):
        self.data_dict.prettyPrint()
        return True

    @property
    def to_dict(self):
        return {
            "categories": self.categories,
            "class": self.task_class,
            "created": self.created,
            "completed": self.completed_date,
            "last_modified": self.last_modified,
            "description": self.description,
            "due_date": self.due_date,
            "percent_complete": self.percent,
            "priority": self.priority,
            "recurrence": self.recurrence,
            "summary": self.summary,
            "start_date": self.start_date,
            "status": self.status,
            "uid": self.uid,
        }

    def serialize(self):
        return json.dumps(self.to_dict, indent=4, sort_keys=True, default=str)

    def to_todo_txt(self, num):
        if self.status is None:
            status = "NEEDS-ACTION"
        else:
            status = self.status

        if self.due_date is None:
            due_date = ""
        else:
            due_date = f"({self.due_date: %Y-%m-%d})"
        recurrence = (
            f" rec:{rrule_to_recurrence(self.recurrence)}" if self.recurrence else ""
        )
        print(
            f"({num}) ({self.priority}) {status} {due_date} {self.summary} {self.categories or ''}{recurrence}"
        )

    def view(self):
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column(style="bold cyan", no_wrap=True)
        table.add_column()

        def fmt_date(d):
            if d is None:
                return "—"
            return d.strftime("%Y-%m-%d")

        table.add_row("Status", self.status or "—")
        table.add_row("Due", fmt_date(self.due_date))
        table.add_row(
            "Recurrence",
            f"rec:{rrule_to_recurrence(self.recurrence)}" if self.recurrence else "—",
        )
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

    def _parse_categories(self):
        categories = []
        todo = self.data_dict.contents.get("vtodo")[0]
        if todo.contents.get("categories") is not None:
            return todo.contents.get("categories")[0].value
        else:
            return None

    def _parse_summary(self):
        todo = self.data_dict.contents.get("vtodo")[0]
        return todo.contents.get("summary")[0].value

    def _parse_description(self):
        todo = self.data_dict.contents.get("vtodo")[0]
        desc_list = todo.contents.get("description")

        if desc_list is not None:
            return desc_list[0].value
        else:
            return None

    def _parse_status(self):
        todo = self.data_dict.contents.get("vtodo")[0]
        status = todo.contents.get("status")
        if status is not None:
            return status[0].value
        else:
            return "NEEDS-ACTION"

    def _parse_class(self):
        todo = self.data_dict.contents.get("vtodo")[0]
        task_class = todo.contents.get("class")
        if task_class is not None:
            return task_class[0].value
        else:
            return None

    def _parse_priority(self):
        todo = self.data_dict.contents.get("vtodo")[0]
        priority = todo.contents.get("priority")
        if priority is not None:
            priority = int(priority[0].value)
            if priority <= 4:
                return "HIGH"
            elif priority == 5:
                return "MEDIUM"
            elif priority > 5 and priority <= 9:
                return "LOW"
            else:
                return None
        else:
            return None

    def _parse_created(self):
        todo = self.data_dict.contents.get("vtodo")[0]
        created = todo.contents.get("created")
        if created is not None:
            return created[0].value
        else:
            return None

    def _parse_updated(self):
        todo = self.data_dict.contents.get("vtodo")[0]
        created = todo.contents.get("last-modified")
        if created is not None:
            return created[0].value
        else:
            return None

    def _parse_percent(self):
        todo = self.data_dict.contents.get("vtodo")[0]
        created = todo.contents.get("percent-complete")
        if created is not None:
            return created[0].value
        else:
            return None

    def _parse_recurrence(self):
        todo = self.data_dict.contents.get("vtodo")[0]
        rrule = todo.contents.get("rrule")
        if rrule is not None:
            return rrule[0].value
        return None

    def _parse_uid(self):
        todo = self.data_dict.contents.get("vtodo")[0]
        created = todo.contents.get("uid")
        if created is not None:
            return created[0].value
        else:
            return None

    def _parse_dates(self):
        todo = self.data_dict.contents.get("vtodo")[0]
        start = None
        due = None
        completed = None
        if todo.contents.get("dtstart") is not None:
            start = todo.contents.get("dtstart")[0].value
        if todo.contents.get("due") is not None:
            due = todo.contents.get("due")[0].value
        if todo.contents.get("completed") is not None:
            completed = todo.contents.get("completed")[0].value
        return start, due, completed


class TodoList:
    PRIORITY_RE = re.compile(r"^\s*\(([0-9])\)")
    PROJECT_RE = re.compile(r"(\s+|^)\+([^\s]+)")
    CONTEXT_RE = re.compile(r"(\s+|^)@([^\s]+)")
    KEYVALUE_RE = re.compile(r"(\s+|^)([^\s]+):([^\s$]+)")
    DATE_RE = re.compile(r"^\s*([\d]{4}-[\d]{2}-[\d]{2})", re.ASCII)
    DATE_FMT = "%Y-%m-%d"
    CACHE_TTL_SECONDS = 600

    def __init__(self, client):
        self.calendar = None
        self.todos = None
        self.client = client
        self.task_calendar = os.environ.get("TASK_CALENDAR")
        self.get_task_cal()
        self.get_tasks()

    def serialize(self):
        for t in enumerate(self.todos):
            t[1].to_todo_txt(t[0] + 1)
        # my_columns = [t.to_todo_txt() for t in self.todos]
        # columns = Columns(my_columns, equal=True, expand=True)
        # print(columns)

    def get_task_cal(self):
        my_principal = self.client.principal()
        calendars = my_principal.calendars()
        for cal in calendars:
            if cal.name == self.task_calendar:
                self.calendar = cal

    def _cache_path(self):
        cache_dir = os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache"))
        return os.path.join(cache_dir, "taskdav", "tasks.json")

    def _invalidate_cache(self):
        try:
            os.remove(self._cache_path())
        except FileNotFoundError:
            pass

    def _read_cache(self, path, include_completed):
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return None
        if not isinstance(data, dict):
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

    def get_tasks(self, include_completed=False):
        if self.calendar is None:
            raise ValueError("No Calendar specified for Tasks.")

        cache_path = self._cache_path()
        cached = self._read_cache(cache_path, include_completed)
        if cached is not None:
            # Hit: raw_todos is list[str]; miss path below assigns list[caldav.Todo].
            self.raw_todos = cached
            self.todos = [Task(s) for s in cached]
            return None

        self.raw_todos = self.calendar.todos(include_completed=include_completed)
        raw_strings = [todo.data for todo in self.raw_todos]
        self.todos = [Task(s) for s in raw_strings]
        self._write_cache(cache_path, include_completed, raw_strings)
        return None

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
        task.add("priority").value = str(priority_to_int(task_data.get("priority")))
        if task_data.get("start_date") is not None:
            task.add("dtstart").value = task_data.get("start_date")
        if task_data.get("recurrence"):
            task.add("rrule").value = recurrence_to_rrule(task_data["recurrence"])
        if task_data.get("status") is not None:
            task.add("status").value = task_data.get("status")

        self.calendar.save_todo(task.serialize())
        self._invalidate_cache()
        self.get_tasks()
        return task

    def delete_task(self, id):
        task = self.todos[int(id) - 1]
        # print(task.serialize())
        # task.delete()
        self._invalidate_cache()  # bust cache after successful delete (un-stub above)
        ttype = type(task.data_dict)
        return None

    def view_task(self, id):
        self.get_tasks()
        task = self.todos[int(id) - 1]
        task.view()

    def parse(self, data):
        task_data = {
            "priority": None,
            "summary": None,
            "description": None,
            "due_date": None,
            "categories": None,
            "status": None,
            "start_date": None,
            "recurrence": None,
        }
        data = data.strip().split()

        summary_words = []
        categories = []
        for item in data:
            # Is it the priority?
            if re.match(r"\((\w{1})\)", item):
                task_data["priority"] = re.match(r"\((\w{1})\)", item).group(1)
            # CalDav doesn't know the difference between projects and contexts.  Put both in categories?
            elif re.match(r"(\+|\@)(\w+)", item):
                categories.append(re.match(r"(\+|\@)(\w+)", item).group(2))
            # Start date
            elif re.match(r"start:(.*)", item):
                task_data["start_date"] = dateutil.parser.parse(
                    re.match(r"start:(.*)", item).group(1)
                )
            # due date
            elif re.match(r"due:(.*)", item):
                task_data["due_date"] = dateutil.parser.parse(
                    re.match(r"due:(.*)", item).group(1)
                )
            # recurrence (todo.txt-style: w, 1w, +2m)
            elif re.match(r"rec:(\S+)", item):
                task_data["recurrence"] = re.match(r"rec:(\S+)", item).group(1)
            else:
                summary_words.append(item)

        # "NEEDS-ACTION" ;Indicates to-do needs action.
        # "COMPLETED"    ;Indicates to-do completed.
        # "IN-PROCESS"   ;Indicates to-do in process of.
        # "CANCELLED"    ;Indicates to-do was cancelled.
        # New tasks are set to NEEDS-ACTION for now?
        # TODO: Figure out a better way to handle this.
        task_data["status"] = "NEEDS-ACTION"
        task_data["summary"] = " ".join(summary_words)
        # task_data["categories"] = ",".join(categories)
        task_data["categories"] = categories
        return task_data
