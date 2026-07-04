#!/usr/bin/env python

from datetime import datetime, timedelta
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


@click.group()
def cli():
    pass


@click.command(help="Delete a task")
@click.argument("id")
def delete_task(id):
    tdl.get_tasks()
    tdl.delete_task(id)
    tdl.serialize()


@click.command(help="List all open Tasks")
@click.option(
    "--include-completed",
    "-i",
    is_flag=True,
    help="Include completed Tasks in the task list.",
)
def list_tasks(include_completed):
    try:
        tdl.get_tasks(include_completed)
        tdl.serialize()
    except ValueError as e:
        print(e)


@click.command(help="Create a new Task")
@click.argument("line")
def create(line):
    tdl.create_task(line)
    tdl.serialize()


cli.add_command(list_tasks, name="list")
cli.add_command(create)
cli.add_command(delete_task, name="delete")

if __name__ == "__main__":
    cli()
