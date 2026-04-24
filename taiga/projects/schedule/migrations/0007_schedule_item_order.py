# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos INC

from django.db import migrations, models
import django.db.models.deletion


ROOT_PARENT_ENTITY_TYPE = ""
ROOT_PARENT_ENTITY_ID = 0


def backfill_schedule_item_order(apps, schema_editor):
    Schedule = apps.get_model("schedule", "Schedule")
    ScheduleItemOrder = apps.get_model("schedule", "ScheduleItemOrder")
    RelatedUserStory = apps.get_model("epics", "RelatedUserStory")
    Task = apps.get_model("tasks", "Task")

    primary_epic_by_userstory_id = {}
    related_rows = (
        RelatedUserStory.objects
        .all()
        .order_by("user_story_id", "order", "id")
        .values_list("user_story_id", "epic_id")
    )
    for user_story_id, epic_id in related_rows.iterator():
        if user_story_id not in primary_epic_by_userstory_id:
            primary_epic_by_userstory_id[user_story_id] = epic_id

    task_userstory_map = {
        task_id: user_story_id
        for task_id, user_story_id in Task.objects.all().values_list("id", "user_story_id")
    }

    counters_by_group = {}
    rows = []

    schedules = (
        Schedule.objects
        .all()
        .order_by("project_id", "entity_type", "entity_id", "id")
        .only("id", "project_id", "entity_type", "entity_id")
    )

    for schedule in schedules.iterator():
        parent_entity_type = ROOT_PARENT_ENTITY_TYPE
        parent_entity_id = ROOT_PARENT_ENTITY_ID

        if schedule.entity_type == "userstory":
            epic_id = primary_epic_by_userstory_id.get(schedule.entity_id)
            if epic_id:
                parent_entity_type = "epic"
                parent_entity_id = epic_id
        elif schedule.entity_type == "task":
            user_story_id = task_userstory_map.get(schedule.entity_id)
            if user_story_id:
                parent_entity_type = "userstory"
                parent_entity_id = user_story_id

        group_key = (
            schedule.project_id,
            schedule.entity_type,
            parent_entity_type,
            parent_entity_id,
        )
        position = counters_by_group.get(group_key, 0) + 1
        counters_by_group[group_key] = position

        rows.append(
            ScheduleItemOrder(
                schedule_id=schedule.id,
                project_id=schedule.project_id,
                entity_type=schedule.entity_type,
                parent_entity_type=parent_entity_type,
                parent_entity_id=parent_entity_id,
                position=position,
            )
        )

        if len(rows) >= 1000:
            ScheduleItemOrder.objects.bulk_create(rows, batch_size=1000)
            rows = []

    if rows:
        ScheduleItemOrder.objects.bulk_create(rows, batch_size=1000)


def clear_schedule_item_order(apps, schema_editor):
    ScheduleItemOrder = apps.get_model("schedule", "ScheduleItemOrder")
    ScheduleItemOrder.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("epics", "0006_auto_20200615_0811"),
        ("tasks", "0013_auto_20200615_0811"),
        ("userstories", "0021_auto_20201202_0850"),
        ("schedule", "0006_schedule_dependency"),
    ]

    operations = [
        migrations.CreateModel(
            name="ScheduleItemOrder",
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
                    "project_id",
                    models.BigIntegerField(db_index=True),
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
                (
                    "parent_entity_type",
                    models.CharField(blank=True, db_index=True, default="", max_length=16),
                ),
                (
                    "parent_entity_id",
                    models.BigIntegerField(db_index=True, default=0),
                ),
                (
                    "position",
                    models.PositiveIntegerField(default=1),
                ),
                (
                    "modified_date",
                    models.DateTimeField(auto_now=True),
                ),
                (
                    "schedule",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="item_order",
                        to="schedule.schedule",
                    ),
                ),
            ],
            options={
                "verbose_name": "schedule item order",
                "verbose_name_plural": "schedule item orders",
                "ordering": [
                    "project_id",
                    "entity_type",
                    "parent_entity_type",
                    "parent_entity_id",
                    "position",
                    "id",
                ],
                "unique_together": {
                    (
                        "project_id",
                        "entity_type",
                        "parent_entity_type",
                        "parent_entity_id",
                        "position",
                    ),
                },
            },
        ),
        migrations.AddIndex(
            model_name="scheduleitemorder",
            index=models.Index(
                fields=[
                    "project_id",
                    "entity_type",
                    "parent_entity_type",
                    "parent_entity_id",
                    "position",
                ],
                name="schedule_sc_project_484285_idx",
            ),
        ),
        migrations.RunPython(backfill_schedule_item_order, clear_schedule_item_order),
    ]
