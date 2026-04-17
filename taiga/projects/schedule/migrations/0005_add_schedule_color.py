# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos INC

from django.db import migrations, models


def backfill_schedule_color(apps, schema_editor):
    Schedule = apps.get_model("schedule", "Schedule")
    Epic = apps.get_model("epics", "Epic")
    RelatedUserStory = apps.get_model("epics", "RelatedUserStory")
    Task = apps.get_model("tasks", "Task")

    qn = schema_editor.quote_name
    schedule_table = qn(Schedule._meta.db_table)
    epic_table = qn(Epic._meta.db_table)
    related_table = qn(RelatedUserStory._meta.db_table)
    task_table = qn(Task._meta.db_table)
    order_column = qn("order")

    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            (
                "UPDATE {schedule_table} AS s "
                "SET color = e.color "
                "FROM {epic_table} AS e "
                "WHERE s.entity_type = %s "
                "AND s.entity_id = e.id"
            ).format(schedule_table=schedule_table, epic_table=epic_table),
            ["epic"],
        )

        cursor.execute(
            (
                "UPDATE {schedule_table} AS s "
                "SET color = ("
                "    SELECT e.color "
                "    FROM {related_table} AS rus "
                "    INNER JOIN {epic_table} AS e ON e.id = rus.epic_id "
                "    WHERE rus.user_story_id = s.entity_id "
                "    ORDER BY rus.{order_column}, rus.id "
                "    LIMIT 1"
                ") "
                "WHERE s.entity_type = %s"
            ).format(
                schedule_table=schedule_table,
                related_table=related_table,
                epic_table=epic_table,
                order_column=order_column,
            ),
            ["userstory"],
        )

        cursor.execute(
            (
                "UPDATE {schedule_table} AS s "
                "SET color = ("
                "    SELECT e.color "
                "    FROM {task_table} AS t "
                "    INNER JOIN {related_table} AS rus ON rus.user_story_id = t.user_story_id "
                "    INNER JOIN {epic_table} AS e ON e.id = rus.epic_id "
                "    WHERE t.id = s.entity_id "
                "    ORDER BY rus.{order_column}, rus.id "
                "    LIMIT 1"
                ") "
                "WHERE s.entity_type = %s"
            ).format(
                schedule_table=schedule_table,
                task_table=task_table,
                related_table=related_table,
                epic_table=epic_table,
                order_column=order_column,
            ),
            ["task"],
        )


def clear_schedule_color(apps, schema_editor):
    Schedule = apps.get_model("schedule", "Schedule")
    Schedule.objects.update(color=None)


class Migration(migrations.Migration):

    dependencies = [
        ("schedule", "0004_auto_20260405_0011"),
    ]

    operations = [
        migrations.AddField(
            model_name="schedule",
            name="color",
            field=models.CharField(
                blank=True,
                default=None,
                max_length=32,
                null=True,
                verbose_name="color",
            ),
        ),
        migrations.RunPython(backfill_schedule_color, clear_schedule_color),
    ]
