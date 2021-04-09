from datetime import datetime
import os
import caldav
from task import Task

## CONFIGURATION.
caldav_url = os.environ.get('CALDAV_URL')
username = os.environ.get('TASK_USERNAME')
password = os.environ.get('TASK_PWORD')

def main():
    client = caldav.DAVClient(url=caldav_url, username=username, password=password)

    ## Typically the next step is to fetch a principal object.
    ## This will cause communication with the server.
    my_principal = client.principal()

    ## The principals calendars can be fetched like this:
    calendars = my_principal.calendars()

    ## Fetch the tasks
    todos = calendars[1].todos()

    for t in todos:
        task = Task(t.data)
        print(task.serialize())

## It's possible to fetch historic tasks too
##todos = my_new_tasklist.todos(include_completed=True)
if __name__ == "__main__":
    main()
