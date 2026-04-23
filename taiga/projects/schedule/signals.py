# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos INC

from django.apps import apps
from django.db.models import signals

from . import services


def _task_post_save(sender, instance, created, **kwargs):
    data = {
        "project_id": instance.project_id,
        "created_date": instance.created_date,
        "due_date": instance.due_date,
    }

    if hasattr(instance, "estimated_start"):
        data["estimated_start"] = instance.estimated_start

    if hasattr(instance, "actual_start"):
        data["actual_start"] = instance.actual_start

    if hasattr(instance, "estimated_hours"):
        data["estimated_hours"] = instance.estimated_hours

    if hasattr(instance, "actual_hours"):
        data["actual_hours"] = instance.actual_hours

    inherited_color = None
    if getattr(instance, "user_story_id", None):
        inherited_color = services.get_primary_epic_color_for_userstory(instance.user_story_id)

    if inherited_color is not None:
        data["color"] = inherited_color
    elif hasattr(instance, "color"):
        data["color"] = instance.color

    services.upsert_schedule(services.ENTITY_TASK, instance.id, **data)
    services.ensure_userstory_and_epic_bounds_from_task(
        instance.id,
        getattr(instance, "user_story_id", None),
    )
    services.propagate_dependency_chain_forward(services.ENTITY_TASK, instance.id)


def _task_post_delete(sender, instance, **kwargs):
    services.delete_schedule(services.ENTITY_TASK, instance.id)


def _userstory_post_save(sender, instance, created, **kwargs):
    data = {
        "project_id": instance.project_id,
        "created_date": instance.created_date,
        "due_date": instance.due_date,
    }

    if hasattr(instance, "estimated_start"):
        data["estimated_start"] = instance.estimated_start

    if hasattr(instance, "actual_start"):
        data["actual_start"] = instance.actual_start

    if hasattr(instance, "estimated_hours"):
        data["estimated_hours"] = instance.estimated_hours

    if hasattr(instance, "actual_hours"):
        data["actual_hours"] = instance.actual_hours

    inherited_color = services.get_primary_epic_color_for_userstory(instance.id)
    if inherited_color is not None:
        data["color"] = inherited_color
    elif hasattr(instance, "color"):
        data["color"] = instance.color

    services.upsert_schedule(services.ENTITY_USERSTORY, instance.id, **data)
    services.ensure_epic_bounds_for_userstory(instance.id)
    services.propagate_dependency_chain_forward(services.ENTITY_USERSTORY, instance.id)


def _userstory_post_delete(sender, instance, **kwargs):
    services.delete_schedule(services.ENTITY_USERSTORY, instance.id)


def _epic_post_save(sender, instance, created, **kwargs):
    data = {
        "project_id": instance.project_id,
        "created_date": instance.created_date,
        "color": getattr(instance, "color", None),
    }

    if hasattr(instance, "due_date"):
        data["due_date"] = instance.due_date

    if hasattr(instance, "estimated_start"):
        data["estimated_start"] = instance.estimated_start

    if hasattr(instance, "actual_start"):
        data["actual_start"] = instance.actual_start

    if hasattr(instance, "estimated_hours"):
        data["estimated_hours"] = instance.estimated_hours

    if hasattr(instance, "actual_hours"):
        data["actual_hours"] = instance.actual_hours

    services.upsert_schedule(services.ENTITY_EPIC, instance.id, **data)
    services.sync_epic_related_schedule_colors(instance.id)
    services.propagate_dependency_chain_forward(services.ENTITY_EPIC, instance.id)


def _epic_post_delete(sender, instance, **kwargs):
    services.delete_schedule(services.ENTITY_EPIC, instance.id)


def _related_userstory_post_save(sender, instance, created, **kwargs):
    services.sync_userstory_and_tasks_schedule_color(instance.user_story_id)
    services.ensure_epic_bounds_for_userstory(instance.user_story_id)


def _related_userstory_post_delete(sender, instance, **kwargs):
    services.sync_userstory_and_tasks_schedule_color(instance.user_story_id)
    services.ensure_epic_bounds_for_userstory(instance.user_story_id)


def connect_schedule_signals():
    task_model = apps.get_model("tasks", "Task")
    userstory_model = apps.get_model("userstories", "UserStory")
    epic_model = apps.get_model("epics", "Epic")
    related_userstory_model = apps.get_model("epics", "RelatedUserStory")

    signals.post_save.connect(
        _task_post_save,
        sender=task_model,
        dispatch_uid="schedule_task_post_save",
    )
    signals.post_delete.connect(
        _task_post_delete,
        sender=task_model,
        dispatch_uid="schedule_task_post_delete",
    )

    signals.post_save.connect(
        _userstory_post_save,
        sender=userstory_model,
        dispatch_uid="schedule_userstory_post_save",
    )
    signals.post_delete.connect(
        _userstory_post_delete,
        sender=userstory_model,
        dispatch_uid="schedule_userstory_post_delete",
    )

    signals.post_save.connect(
        _epic_post_save,
        sender=epic_model,
        dispatch_uid="schedule_epic_post_save",
    )
    signals.post_delete.connect(
        _epic_post_delete,
        sender=epic_model,
        dispatch_uid="schedule_epic_post_delete",
    )

    signals.post_save.connect(
        _related_userstory_post_save,
        sender=related_userstory_model,
        dispatch_uid="schedule_related_userstory_post_save",
    )
    signals.post_delete.connect(
        _related_userstory_post_delete,
        sender=related_userstory_model,
        dispatch_uid="schedule_related_userstory_post_delete",
    )
