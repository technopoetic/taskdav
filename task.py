import os

import vobject
import json
import re
import dateutil
from datetime import datetime

from rich import print
from rich.columns import Columns


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
        print(
            f"({num}) ({self.priority}) {status} {due_date} {self.summary} {self.categories or ''}"
        )

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
        task.add("priority").value = task_data.get("priority", 9)
        if task_data.get("start_date") is not None:
            task.add("dtstart").value = task_data.get("start_date")
        if task_data.get("status") is not None:
            task.add("status").value = task_data.get("status")

        self.calendar.save_todo(task.serialize())
        self.get_tasks()
        return task

    def delete_task(self, id):
        task = self.todos[int(id) - 1]
        # print(task.serialize())
        # task.delete()
        ttype = type(task.data_dict)
        return None

    def parse(self, data):
        task_data = {
            "priority": None,
            "summary": None,
            "description": None,
            "due_date": None,
            "categories": None,
            "status": None,
            "start_date": None,
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
