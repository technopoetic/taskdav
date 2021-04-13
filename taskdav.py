#!/usr/bin/env python

from datetime import datetime
import click
import os
import caldav
from task import Task

## CONFIGURATION.
caldav_url = os.environ.get("CALDAV_URL")
task_calendar = os.environ.get("TASK_CALENDAR")
username = os.environ.get("TASK_USERNAME")
password = os.environ.get("TASK_PWORD")


def get_tasks(include_completed=False):
    task_cal = get_task_cal()
    if task_cal is not None:
        todos = task_cal.todos(include_completed=include_completed)
        return todos
    else:
        raise ValueError("No Calendar specified for Tasks.")

def create_task(data={}):
    task_cal = get_task_cal()
    vdata = (
    f'BEGIN:VCALENDAR\n'
    f'BEGIN:VTODO\n'
    f'SUMMARY:{data.get("summary")}\n'
    f'CATEGORIES:{data.get("category")}\n'
    f'STATUS:{data.get("status")}\n'
    f'PRIORITY:{data.get("priority")}\n'
    f'END:VTODO\n'
    f'END:VCALENDAR'
    )

    if task_cal is not None:
        task_cal.save_todo(vdata)
    else:
        raise ValueError("No Calendar specified for Tasks.")

@click.group()
def cli():
    pass


@click.command(help="List all open Tasks")
@click.option(
    "--include-completed",
    "-i",
    is_flag=True,
    help="Include completed Tasks in the task list.",
)
def list(include_completed):
    try:
        todos = get_tasks(include_completed)

        for t in todos:
            task = Task(t.data)
            print(task.serialize())
    except ValueError as e:
        print(e)


@click.command(help="Create a new Task")
@click.option("--category", "-c", help="Task Category.  Will be created, if it does not already exist")
@click.option("--access", "-a", help="Task Class.  Usually one of Private, Public or Confidential")
@click.option("--desc", "-d", help="Task Description.")
@click.option("--priority", "-p", help="Task Priority.")
@click.option("--summary", "-s", help="Task Summary.")
@click.option("--status", "-t", help="Task Status.")
    # "NEEDS-ACTION" ;Indicates to-do needs action.
    #                    / "COMPLETED"    ;Indicates to-do completed.
    #                    / "IN-PROCESS"   ;Indicates to-do in process of.
    #                    / "CANCELLED"
def create(category=None, access=None, desc=None, priority=None, summary=None, status=None):
    try:
        create_task({
            "category": category,
            "access": access,
            "description": desc,
            "priority": priority,
            "summary": summary,
            "status": status
        })
        todos = get_tasks()

        for t in todos:
            task = Task(t.data)
            print(task.pp())
            print(task.serialize())
    except ValueError as e:
        print(e)

def get_task_cal():
    client = caldav.DAVClient(url=caldav_url, username=username, password=password)
    my_principal = client.principal()
    calendars = my_principal.calendars()
    task_cal = None
    for cal in calendars:
        if cal.name == task_calendar:
            task_cal = cal
    return task_cal

cli.add_command(list)
cli.add_command(create)

if __name__ == "__main__":
    cli()
