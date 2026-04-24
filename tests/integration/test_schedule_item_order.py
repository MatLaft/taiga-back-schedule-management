# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos INC

import pytest

from taiga.projects.epics.models import RelatedUserStory
from taiga.projects.schedule import services as schedule_services
from taiga.projects.schedule.models import ScheduleItemOrder
from tests import factories


pytestmark = pytest.mark.django_db


def _upsert_schedule(entity_type, entity_id, project_id):
    schedule_services.upsert_schedule(
        entity_type,
        entity_id,
        project_id=project_id,
    )


def _get_group_positions(
    project_id,
    entity_type,
    parent_entity_type=ScheduleItemOrder.ROOT_PARENT_ENTITY_TYPE,
    parent_entity_id=ScheduleItemOrder.ROOT_PARENT_ENTITY_ID,
):
    rows = (
        ScheduleItemOrder.objects
        .filter(
            project_id=project_id,
            entity_type=entity_type,
            parent_entity_type=parent_entity_type,
            parent_entity_id=parent_entity_id,
        )
        .select_related("schedule")
        .order_by("position", "id")
    )
    return [(row.schedule.entity_id, row.position) for row in rows]


def test_schedule_item_order_is_grouped_only_between_siblings():
    project = factories.create_project()

    epic_1 = factories.create_epic(project=project)
    epic_2 = factories.create_epic(project=project)

    userstory_1 = factories.create_userstory(project=project)
    userstory_2 = factories.create_userstory(project=project)
    userstory_3 = factories.create_userstory(project=project)

    RelatedUserStory.objects.create(epic=epic_1, user_story=userstory_1, order=1)
    RelatedUserStory.objects.create(epic=epic_1, user_story=userstory_2, order=2)
    RelatedUserStory.objects.create(epic=epic_2, user_story=userstory_3, order=1)

    task_1 = factories.create_task(project=project, user_story=userstory_1)
    task_2 = factories.create_task(project=project, user_story=userstory_1)
    task_3 = factories.create_task(project=project, user_story=userstory_2)

    _upsert_schedule(schedule_services.ENTITY_EPIC, epic_1.id, project.id)
    _upsert_schedule(schedule_services.ENTITY_EPIC, epic_2.id, project.id)
    _upsert_schedule(schedule_services.ENTITY_USERSTORY, userstory_1.id, project.id)
    _upsert_schedule(schedule_services.ENTITY_USERSTORY, userstory_2.id, project.id)
    _upsert_schedule(schedule_services.ENTITY_USERSTORY, userstory_3.id, project.id)
    _upsert_schedule(schedule_services.ENTITY_TASK, task_1.id, project.id)
    _upsert_schedule(schedule_services.ENTITY_TASK, task_2.id, project.id)
    _upsert_schedule(schedule_services.ENTITY_TASK, task_3.id, project.id)

    assert _get_group_positions(project.id, schedule_services.ENTITY_EPIC) == [
        (epic_1.id, 1),
        (epic_2.id, 2),
    ]
    assert _get_group_positions(
        project.id,
        schedule_services.ENTITY_USERSTORY,
        parent_entity_type=schedule_services.ENTITY_EPIC,
        parent_entity_id=epic_1.id,
    ) == [
        (userstory_1.id, 1),
        (userstory_2.id, 2),
    ]
    assert _get_group_positions(
        project.id,
        schedule_services.ENTITY_USERSTORY,
        parent_entity_type=schedule_services.ENTITY_EPIC,
        parent_entity_id=epic_2.id,
    ) == [
        (userstory_3.id, 1),
    ]
    assert _get_group_positions(
        project.id,
        schedule_services.ENTITY_TASK,
        parent_entity_type=schedule_services.ENTITY_USERSTORY,
        parent_entity_id=userstory_1.id,
    ) == [
        (task_1.id, 1),
        (task_2.id, 2),
    ]
    assert _get_group_positions(
        project.id,
        schedule_services.ENTITY_TASK,
        parent_entity_type=schedule_services.ENTITY_USERSTORY,
        parent_entity_id=userstory_2.id,
    ) == [
        (task_3.id, 1),
    ]


def test_schedule_item_order_compacts_positions_when_a_sibling_is_deleted():
    project = factories.create_project()
    userstory = factories.create_userstory(project=project)

    task_1 = factories.create_task(project=project, user_story=userstory)
    task_2 = factories.create_task(project=project, user_story=userstory)
    task_3 = factories.create_task(project=project, user_story=userstory)
    task_4 = factories.create_task(project=project, user_story=userstory)

    _upsert_schedule(schedule_services.ENTITY_TASK, task_1.id, project.id)
    _upsert_schedule(schedule_services.ENTITY_TASK, task_2.id, project.id)
    _upsert_schedule(schedule_services.ENTITY_TASK, task_3.id, project.id)
    _upsert_schedule(schedule_services.ENTITY_TASK, task_4.id, project.id)

    schedule_services.delete_schedule(schedule_services.ENTITY_TASK, task_2.id)

    assert _get_group_positions(
        project.id,
        schedule_services.ENTITY_TASK,
        parent_entity_type=schedule_services.ENTITY_USERSTORY,
        parent_entity_id=userstory.id,
    ) == [
        (task_1.id, 1),
        (task_3.id, 2),
        (task_4.id, 3),
    ]


def test_schedule_item_order_reposition_shifts_following_siblings_in_chain():
    project = factories.create_project()
    userstory = factories.create_userstory(project=project)

    task_1 = factories.create_task(project=project, user_story=userstory)
    task_2 = factories.create_task(project=project, user_story=userstory)
    task_3 = factories.create_task(project=project, user_story=userstory)
    task_4 = factories.create_task(project=project, user_story=userstory)

    _upsert_schedule(schedule_services.ENTITY_TASK, task_1.id, project.id)
    _upsert_schedule(schedule_services.ENTITY_TASK, task_2.id, project.id)
    _upsert_schedule(schedule_services.ENTITY_TASK, task_3.id, project.id)
    _upsert_schedule(schedule_services.ENTITY_TASK, task_4.id, project.id)

    schedule_services.set_schedule_item_order_position(
        schedule_services.ENTITY_TASK,
        task_4.id,
        2,
    )

    assert _get_group_positions(
        project.id,
        schedule_services.ENTITY_TASK,
        parent_entity_type=schedule_services.ENTITY_USERSTORY,
        parent_entity_id=userstory.id,
    ) == [
        (task_1.id, 1),
        (task_4.id, 2),
        (task_2.id, 3),
        (task_3.id, 4),
    ]


def test_schedule_item_order_sync_keeps_position_when_parent_group_is_unchanged():
    project = factories.create_project()
    userstory = factories.create_userstory(project=project)

    task_1 = factories.create_task(project=project, user_story=userstory)
    task_2 = factories.create_task(project=project, user_story=userstory)
    task_3 = factories.create_task(project=project, user_story=userstory)

    _upsert_schedule(schedule_services.ENTITY_TASK, task_1.id, project.id)
    _upsert_schedule(schedule_services.ENTITY_TASK, task_2.id, project.id)
    _upsert_schedule(schedule_services.ENTITY_TASK, task_3.id, project.id)

    _upsert_schedule(schedule_services.ENTITY_TASK, task_2.id, project.id)

    assert _get_group_positions(
        project.id,
        schedule_services.ENTITY_TASK,
        parent_entity_type=schedule_services.ENTITY_USERSTORY,
        parent_entity_id=userstory.id,
    ) == [
        (task_1.id, 1),
        (task_2.id, 2),
        (task_3.id, 3),
    ]
