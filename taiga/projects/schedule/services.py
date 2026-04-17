# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos INC

from django.apps import apps
from django.db import OperationalError
from django.db import ProgrammingError

from .models import Schedule


ENTITY_EPIC = Schedule.TYPE_EPIC
ENTITY_USERSTORY = Schedule.TYPE_USERSTORY
ENTITY_TASK = Schedule.TYPE_TASK

_UNSET = object()
_ALLOWED_ENTITIES = {ENTITY_EPIC, ENTITY_USERSTORY, ENTITY_TASK}


def _assert_entity_type(entity_type):
    if entity_type not in _ALLOWED_ENTITIES:
        raise ValueError("Unsupported entity_type: {}".format(entity_type))


def get_schedule(entity_type, entity_id):
    _assert_entity_type(entity_type)
    try:
        return Schedule.objects.filter(entity_type=entity_type, entity_id=entity_id).first()
    except (ProgrammingError, OperationalError):
        return None


def delete_schedule(entity_type, entity_id):
    _assert_entity_type(entity_type)
    try:
        Schedule.objects.filter(entity_type=entity_type, entity_id=entity_id).delete()
    except (ProgrammingError, OperationalError):
        return


def upsert_schedule(
    entity_type,
    entity_id,
    *,
    project_id,
    created_date=_UNSET,
    due_date=_UNSET,
    estimated_start=_UNSET,
    actual_start=_UNSET,
    estimated_hours=_UNSET,
    actual_hours=_UNSET,
    color=_UNSET,
):
    _assert_entity_type(entity_type)
    try:
        obj, _ = Schedule.objects.get_or_create(
            entity_type=entity_type,
            entity_id=entity_id,
            defaults={"project_id": project_id},
        )
    except (ProgrammingError, OperationalError):
        return None

    updates = {}
    if obj.project_id != project_id:
        updates["project_id"] = project_id
    if created_date is not _UNSET:
        updates["created_date"] = created_date
    if due_date is not _UNSET:
        updates["due_date"] = due_date
    if estimated_start is not _UNSET:
        updates["estimated_start"] = estimated_start
    if actual_start is not _UNSET:
        updates["actual_start"] = actual_start
    if estimated_hours is not _UNSET:
        updates["estimated_hours"] = estimated_hours
    if actual_hours is not _UNSET:
        updates["actual_hours"] = actual_hours
    if color is not _UNSET:
        updates["color"] = color

    if updates:
        try:
            Schedule.objects.filter(id=obj.id).update(**updates)
        except (ProgrammingError, OperationalError):
            return obj
        for key, value in updates.items():
            setattr(obj, key, value)

    return obj


def attach_schedule_fields(queryset, entity_type, field_names):
    _assert_entity_type(entity_type)
    model = queryset.model
    model_table = model._meta.db_table
    schedule_table = Schedule._meta.db_table

    select = {}
    for field_name in field_names:
        select_key = "schedule_{}".format(field_name)
        sql = (
            'SELECT "{schedule_table}"."{field_name}" '
            'FROM "{schedule_table}" '
            "WHERE "
            '"{schedule_table}"."entity_type" = \'{entity_type}\' '
            "AND "
            '"{schedule_table}"."entity_id" = "{model_table}"."id" '
            "LIMIT 1"
        ).format(
            schedule_table=schedule_table,
            field_name=field_name,
            entity_type=entity_type,
            model_table=model_table,
        )
        select[select_key] = sql

    if select:
        queryset = queryset.extra(select=select)

    return queryset


def get_schedule_field(obj, entity_type, field_name):
    attr_name = "schedule_{}".format(field_name)
    if hasattr(obj, attr_name):
        return getattr(obj, attr_name)

    schedule = get_schedule(entity_type, obj.id)
    if schedule is None:
        return None

    return getattr(schedule, field_name)


def get_due_date(entity_type, entity_id):
    _assert_entity_type(entity_type)

    if entity_type == ENTITY_EPIC:
        schedule = get_schedule(ENTITY_EPIC, entity_id)
        return schedule.due_date if schedule else None

    if entity_type == ENTITY_USERSTORY:
        model = apps.get_model("userstories", "UserStory")
        return model.objects.filter(id=entity_id).values_list("due_date", flat=True).first()

    model = apps.get_model("tasks", "Task")
    return model.objects.filter(id=entity_id).values_list("due_date", flat=True).first()


def get_primary_epic_color_for_userstory(userstory_id):
    if not userstory_id:
        return None

    try:
        related_model = apps.get_model("epics", "RelatedUserStory")
        relation = (
            related_model.objects
            .filter(user_story_id=userstory_id)
            .select_related("epic")
            .order_by("order", "id")
            .first()
        )
    except (ProgrammingError, OperationalError):
        return None

    if relation is None or relation.epic is None:
        return None

    return relation.epic.color


def sync_userstory_and_tasks_schedule_color(userstory_id):
    if not userstory_id:
        return

    try:
        userstory_model = apps.get_model("userstories", "UserStory")
        task_model = apps.get_model("tasks", "Task")
        userstory = userstory_model.objects.filter(id=userstory_id).first()
    except (ProgrammingError, OperationalError):
        return

    if userstory is None:
        return

    color = get_primary_epic_color_for_userstory(userstory_id)

    upsert_schedule(
        ENTITY_USERSTORY,
        userstory.id,
        project_id=userstory.project_id,
        color=color,
    )

    try:
        tasks = task_model.objects.filter(user_story_id=userstory.id).only("id", "project_id")
    except (ProgrammingError, OperationalError):
        return

    for task in tasks:
        upsert_schedule(
            ENTITY_TASK,
            task.id,
            project_id=task.project_id,
            color=color,
        )


def sync_epic_related_schedule_colors(epic_id):
    if not epic_id:
        return

    try:
        related_model = apps.get_model("epics", "RelatedUserStory")
        userstory_ids = (
            related_model.objects
            .filter(epic_id=epic_id)
            .values_list("user_story_id", flat=True)
            .distinct()
        )
    except (ProgrammingError, OperationalError):
        return

    for userstory_id in userstory_ids:
        sync_userstory_and_tasks_schedule_color(userstory_id)
