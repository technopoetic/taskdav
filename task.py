import vobject
import json

class Task():
    def __init__(self, vdata):
        self.data_dict = vobject.readOne(vdata)

        self.categories = self._parse_categories()
        self.created = self._parse_created()
        self.task_class = self._parse_class()
        self.description = self._parse_description()
        self.priority = self._parse_priority()
        self.summary = self._parse_summary()
        self.status = self._parse_status()

    def pp(self):
        return self.data_dict.prettyPrint()

    @property
    def to_dict(self):
        return {
            'categories': self.categories,
            'class': self.task_class,
            'created': self.created,
            'description': self.description,
            'priority': self.priority,
            'summary': self.summary,
            'status': self.status
        }

    def serialize(self):
        return json.dumps(self.to_dict, indent=4, sort_keys=True, default=str)

    def _parse_categories(self):
        categories = []
        todo = self.data_dict.contents.get('vtodo')[0]
        if todo.contents.get('categories') is not None:
            for y in todo.contents.get('categories'):
                categories.append(y.value)
        return [item for sublist in categories for item in sublist]

    def _parse_summary(self):
        todo = self.data_dict.contents.get('vtodo')[0]
        return todo.contents.get('summary')[0].value

    def _parse_description(self):
        todo = self.data_dict.contents.get('vtodo')[0]
        desc_list = todo.contents.get('description')

        if desc_list is not None:
            return desc_list[0].value
        else:
            return None

    def _parse_status(self):
        todo = self.data_dict.contents.get('vtodo')[0]
        status = todo.contents.get('status')
        if status is not None:
            return status[0].value
        else: 
            return None

    def _parse_class(self):
        todo = self.data_dict.contents.get('vtodo')[0]
        task_class = todo.contents.get('class')
        if task_class is not None:
            return task_class[0].value 
        else:
            return None

    def _parse_priority(self):
        todo = self.data_dict.contents.get('vtodo')[0]
        priority = todo.contents.get('priority')
        if priority is not None:
            return priority[0].value 
        else:
            return None

    def _parse_created(self):
        todo = self.data_dict.contents.get('vtodo')[0]
        created = todo.contents.get('created')
        if created is not None:
            return created[0].value 
        else:
            return None
