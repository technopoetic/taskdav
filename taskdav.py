#!/usr/bin/env python

from datetime import datetime
import click
import os
import caldav
from task import Task, TodoList

# CONFIGURATION.
caldav_url = os.environ.get("CALDAV_URL")
username = os.environ.get("TASK_USERNAME")
pwd = os.environ.get("TASK_PWORD")

client = caldav.DAVClient(url=caldav_url, username=username, password=pwd)
tdl = TodoList(client)

def create_task(data=None):
    pass
    # if data is None:
    #     data = {}
    # task_cal = get_task_cal()
    # vdata = (
    #     f'BEGIN:VCALENDAR\n'
    #     f'BEGIN:VTODO\n'
    #     f'SUMMARY:{data.get("summary")}\n'
    #     f'CATEGORIES:{data.get("category")}\n'
    #     f'STATUS:{data.get("status")}\n'
    #     f'PRIORITY:{data.get("priority")}\n'
    #     f'END:VTODO\n'
    #     f'END:VCALENDAR'
    # )
    #
    # if task_cal is not None:
    #     task_cal.save_todo(vdata)
    # else:
    #     raise ValueError("No Calendar specified for Tasks.")


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
def list_tasks(include_completed):
    try:
        tdl.serialize()
    except ValueError as e:
        print(e)


@click.command(help="Create a new Task")
# @click.option("--category", "-c", help="Task Category.  Will be created, if it does not already exist.")
# @click.option("--access", "-a", help="Task Class.  Usually one of Private, Public or Confidential")
# @click.option("--desc", "-d", help="Task Description. Note, this is typically the 'body' of the task.")
# @click.option("--priority", "-p", help="Task Priority.")
# @click.option("--summary", "-s", help="Task Summary. Can be thought of as 'Title'")
# @click.option("--status", "-t", help="Task Status.")
@click.argument('line')

# "NEEDS-ACTION" ;Indicates to-do needs action.
#                    / "COMPLETED"    ;Indicates to-do completed.
#                    / "IN-PROCESS"   ;Indicates to-do in process of.
#                    / "CANCELLED"
# def create(category=None, access='public', desc=None, priority=None, summary=None, status=None):
def create(line):

    print(line)
    try:
        pass
        # create_task({
        #     "category": category,
        #     "access": access,
        #     "description": desc,
        #     "priority": priority,
        #     "summary": summary,
        #     "status": status
        # })
        # todos = get_tasks()
        #
        # for t in todos:
        #     task = Task(t.data)
        #     print(task.pp())
        #     print(task.serialize())
    except ValueError as e:
        print(e)


cli.add_command(list_tasks, name='list')
cli.add_command(create)

if __name__ == "__main__":
    cli()
