# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos INC

from django.db import migrations, models


def backfill_schedule_project_id(apps, schema_editor):
    Schedule = apps.get_model("schedule", "Schedule")
    Task = apps.get_model("tasks", "Task")
    UserStory = apps.get_model("userstories", "UserStory")
    Epic = apps.get_model("epics", "Epic")

    qn = schema_editor.quote_name
    schedule_table = qn(Schedule._meta.db_table)
    task_table = qn(Task._meta.db_table)
    userstory_table = qn(UserStory._meta.db_table)
    epic_table = qn(Epic._meta.db_table)

    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            (
                "UPDATE {schedule_table} AS s "
                "SET project_id = t.project_id "
                "FROM {task_table} AS t "
                "WHERE s.entity_type = %s "
                "AND s.entity_id = t.id"
            ).format(schedule_table=schedule_table, task_table=task_table),
            ["task"],
        )
        cursor.execute(
            (
                "UPDATE {schedule_table} AS s "
                "SET project_id = us.project_id "
                "FROM {userstory_table} AS us "
                "WHERE s.entity_type = %s "
                "AND s.entity_id = us.id"
            ).format(schedule_table=schedule_table, userstory_table=userstory_table),
            ["userstory"],
        )
        cursor.execute(
            (
                "UPDATE {schedule_table} AS s "
                "SET project_id = e.project_id "
                "FROM {epic_table} AS e "
                "WHERE s.entity_type = %s "
                "AND s.entity_id = e.id"
            ).format(schedule_table=schedule_table, epic_table=epic_table),
            ["epic"],
        )

    # Schedule rows must always map to an existing entity/project pair.
    Schedule.objects.filter(project_id__isnull=True).delete()


def clear_schedule_project_id(apps, schema_editor):
    Schedule = apps.get_model("schedule", "Schedule")
    Schedule.objects.update(project_id=None)


class Migration(migrations.Migration):

    dependencies = [
        ("schedule", "0002_add_schedule_hours"),
    ]

    operations = [
        migrations.AddField(
            model_name="schedule",
            name="project_id",
            field=models.BigIntegerField(blank=True, db_index=True, default=None, null=True),
        ),
        migrations.RunPython(backfill_schedule_project_id, clear_schedule_project_id),
        migrations.AlterField(
            model_name="schedule",
            name="project_id",
            field=models.BigIntegerField(db_index=True),
        ),
    ]
