# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos INC

from django.db import migrations, models


def backfill_schedule_data(apps, schema_editor):
    Schedule = apps.get_model("schedule", "Schedule")
    Task = apps.get_model("tasks", "Task")
    UserStory = apps.get_model("userstories", "UserStory")
    Epic = apps.get_model("epics", "Epic")

    rows = []

    for task in Task.objects.all().only("id", "created_date", "due_date"):
        rows.append(
            Schedule(
                entity_type="task",
                entity_id=task.id,
                created_date=task.created_date,
                due_date=task.due_date,
            )
        )

    for user_story in UserStory.objects.all().only("id", "created_date", "due_date"):
        rows.append(
            Schedule(
                entity_type="userstory",
                entity_id=user_story.id,
                created_date=user_story.created_date,
                due_date=user_story.due_date,
            )
        )

    for epic in Epic.objects.all().only("id", "created_date"):
        rows.append(
            Schedule(
                entity_type="epic",
                entity_id=epic.id,
                created_date=epic.created_date,
            )
        )

    if rows:
        Schedule.objects.bulk_create(rows, batch_size=1000, ignore_conflicts=True)


def clear_schedule_data(apps, schema_editor):
    Schedule = apps.get_model("schedule", "Schedule")
    Schedule.objects.all().delete()


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("tasks", "0013_auto_20200615_0811"),
        ("userstories", "0021_auto_20201202_0850"),
        ("epics", "0006_auto_20200615_0811"),
    ]

    operations = [
        migrations.CreateModel(
            name="Schedule",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "entity_type",
                    models.CharField(
                        choices=[
                            ("epic", "Epic"),
                            ("userstory", "User Story"),
                            ("task", "Task"),
                        ],
                        db_index=True,
                        max_length=16,
                    ),
                ),
                ("entity_id", models.BigIntegerField(db_index=True)),
                (
                    "created_date",
                    models.DateTimeField(
                        blank=True, default=None, null=True, verbose_name="created date"
                    ),
                ),
                (
                    "due_date",
                    models.DateField(
                        blank=True, default=None, null=True, verbose_name="due date"
                    ),
                ),
                (
                    "estimated_start",
                    models.DateField(
                        blank=True,
                        default=None,
                        null=True,
                        verbose_name="estimated start date",
                    ),
                ),
                (
                    "actual_start",
                    models.DateField(
                        blank=True,
                        default=None,
                        null=True,
                        verbose_name="actual start date",
                    ),
                ),
                ("modified_date", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "schedule",
                "verbose_name_plural": "schedules",
                "unique_together": {("entity_type", "entity_id")},
            },
        ),
        migrations.AddIndex(
            model_name="schedule",
            index=models.Index(fields=["entity_type", "entity_id"], name="schedule_sc_entity__fa00ef_idx"),
        ),
        migrations.RunPython(backfill_schedule_data, clear_schedule_data),
    ]
