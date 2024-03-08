import vobject
import json


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
            "uid": self.uid
        }

    def serialize(self):
        return json.dumps(self.to_dict, indent=4, sort_keys=True, default=str)

    def _parse_categories(self):
        categories = []
        todo = self.data_dict.contents.get("vtodo")[0]
        if todo.contents.get("categories") is not None:
            for y in todo.contents.get("categories"):
                categories.append(y.value)
        return [item for sublist in categories for item in sublist]

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
            return None

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
            return priority[0].value
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


class TodoList():
    def __init__(self, todos):
        self.todos = []
        for t in todos:
            self.todos.append(Task(t.data))

    def serialize(self):
        for t in self.todos:
            print(t.serialize())
