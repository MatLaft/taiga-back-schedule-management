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
        "created_date": instance.created_date,
        "due_date": instance.due_date,
    }

    if hasattr(instance, "estimated_start"):
        data["estimated_start"] = instance.estimated_start

    if hasattr(instance, "actual_start"):
        data["actual_start"] = instance.actual_start

    services.upsert_schedule(services.ENTITY_TASK, instance.id, **data)


def _task_post_delete(sender, instance, **kwargs):
    services.delete_schedule(services.ENTITY_TASK, instance.id)


def _userstory_post_save(sender, instance, created, **kwargs):
    services.upsert_schedule(
        services.ENTITY_USERSTORY,
        instance.id,
        created_date=instance.created_date,
        due_date=instance.due_date,
    )


def _userstory_post_delete(sender, instance, **kwargs):
    services.delete_schedule(services.ENTITY_USERSTORY, instance.id)


def _epic_post_save(sender, instance, created, **kwargs):
    data = {
        "created_date": instance.created_date,
    }

    if hasattr(instance, "due_date"):
        data["due_date"] = instance.due_date

    services.upsert_schedule(services.ENTITY_EPIC, instance.id, **data)


def _epic_post_delete(sender, instance, **kwargs):
    services.delete_schedule(services.ENTITY_EPIC, instance.id)


def connect_schedule_signals():
    task_model = apps.get_model("tasks", "Task")
    userstory_model = apps.get_model("userstories", "UserStory")
    epic_model = apps.get_model("epics", "Epic")

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
