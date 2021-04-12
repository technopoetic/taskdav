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
    client = caldav.DAVClient(url=caldav_url, username=username, password=password)
    my_principal = client.principal()
    calendars = my_principal.calendars()
    task_cal = None
    for cal in calendars:
        if cal.name == task_calendar:
            task_cal = cal

    if task_cal is not None:
        todos = task_cal.todos(include_completed=include_completed)
        return todos
    else:
        raise ValueError('No Calendar specified for Tasks.')


@click.group()
def cli():
    pass

@click.command()
@click.option(
    '--include-completed',
    '-i',
    is_flag=True,
    help='Include completed Tasks in the task list.')
def list(include_completed):
    try:
        todos = get_tasks(include_completed)

        for t in todos:
            task = Task(t.data)
            print(task.serialize())
    except ValueError as e:
        print(e)

@click.command()
def create():
    print("Not implemented yet")

cli.add_command(list)
cli.add_command(create)

## It's possible to fetch historic tasks too
##todos = my_new_tasklist.todos(include_completed=True)
if __name__ == "__main__":
    cli()
