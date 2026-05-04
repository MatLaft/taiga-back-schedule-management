# -*- coding: utf-8 -*-

import json
from datetime import date
from unittest import mock

import pytest
from django.test.client import Client

from taiga.permissions.choices import MEMBERS_PERMISSIONS
from taiga.projects.schedule import services as schedule_services
from taiga.projects.schedule.models import ScheduleDependency
from tests import factories


pytestmark = pytest.mark.django_db


def _build_project_client(role_permissions=None):
    project = factories.create_project()
    owner = project.owner
    if role_permissions is None:
        role_permissions = [permission[0] for permission in MEMBERS_PERMISSIONS]
    role = factories.RoleFactory.create(
        project=project,
        permissions=role_permissions,
    )
    factories.MembershipFactory.create(project=project, user=owner, role=role)

    client = Client()
    client.force_login(owner)
    return project, client


def test_bulk_apply_dates_requires_modify_schedule_dates_permission():
    role_permissions = [
        permission[0]
        for permission in MEMBERS_PERMISSIONS
        if permission[0] != "modify_schedule_dates"
    ]
    project, client = _build_project_client(role_permissions=role_permissions)

    task = factories.create_task(project=project, due_date=date(2026, 1, 8))
    schedule_services.upsert_schedule(
        schedule_services.ENTITY_TASK,
        task.id,
        project_id=project.id,
        estimated_start=date(2026, 1, 5),
        due_date=date(2026, 1, 8),
    )

    payload = {
        "project_id": project.id,
        "bulk_updates": [
            {
                "entity_type": "task",
                "entity_id": task.id,
                "start_field": "estimated_start",
                "start": "2026-01-10",
                "due": "2026-01-12",
            }
        ],
    }

    response = client.post(
        "/api/v1/schedule-dependencies/bulk_apply_dates",
        data=json.dumps(payload),
        content_type="application/json",
    )

    assert response.status_code == 403


def test_bulk_apply_dates_updates_schedule_and_due_dates_atomically():
    project, client = _build_project_client()

    epic = factories.create_epic(project=project, owner=project.owner)
    userstory = factories.create_userstory(project=project, due_date=date(2026, 1, 8))
    factories.RelatedUserStory.create(epic=epic, user_story=userstory)
    task = factories.create_task(project=project, user_story=userstory, due_date=date(2026, 1, 8))

    schedule_services.upsert_schedule(
        schedule_services.ENTITY_EPIC,
        epic.id,
        project_id=project.id,
        estimated_start=date(2026, 1, 5),
        due_date=date(2026, 1, 8),
    )
    schedule_services.upsert_schedule(
        schedule_services.ENTITY_USERSTORY,
        userstory.id,
        project_id=project.id,
        estimated_start=date(2026, 1, 5),
        due_date=date(2026, 1, 8),
    )
    schedule_services.upsert_schedule(
        schedule_services.ENTITY_TASK,
        task.id,
        project_id=project.id,
        estimated_start=date(2026, 1, 5),
        due_date=date(2026, 1, 8),
    )

    payload = {
        "project_id": project.id,
        "bulk_updates": [
            {
                "entity_type": "task",
                "entity_id": task.id,
                "start_field": "estimated_start",
                "start": "2026-01-10",
                "due": "2026-01-12",
            },
            {
                "entity_type": "userstory",
                "entity_id": userstory.id,
                "start_field": "estimated_start",
                "start": "2026-01-10",
                "due": "2026-01-12",
            },
            {
                "entity_type": "epic",
                "entity_id": epic.id,
                "start_field": "estimated_start",
                "start": "2026-01-10",
                "due": "2026-01-12",
            },
        ],
    }

    response = client.post(
        "/api/v1/schedule-dependencies/bulk_apply_dates",
        data=json.dumps(payload),
        content_type="application/json",
    )

    assert response.status_code == 200
    assert json.loads(response.content)["updated"] == 3

    task_schedule = schedule_services.get_schedule(schedule_services.ENTITY_TASK, task.id)
    userstory_schedule = schedule_services.get_schedule(schedule_services.ENTITY_USERSTORY, userstory.id)
    epic_schedule = schedule_services.get_schedule(schedule_services.ENTITY_EPIC, epic.id)

    task.refresh_from_db()
    userstory.refresh_from_db()

    assert task_schedule.estimated_start == date(2026, 1, 10)
    assert task_schedule.due_date == date(2026, 1, 12)
    assert userstory_schedule.estimated_start == date(2026, 1, 10)
    assert userstory_schedule.due_date == date(2026, 1, 12)
    assert epic_schedule.estimated_start == date(2026, 1, 10)
    assert epic_schedule.due_date == date(2026, 1, 12)

    assert task.due_date == date(2026, 1, 12)
    assert userstory.due_date == date(2026, 1, 12)


def test_bulk_apply_dates_rolls_back_when_dependency_rule_is_violated():
    project, client = _build_project_client()

    userstory = factories.create_userstory(project=project, due_date=date(2026, 1, 20))
    source_task = factories.create_task(project=project, user_story=userstory, due_date=date(2026, 1, 10))
    target_task = factories.create_task(project=project, user_story=userstory, due_date=date(2026, 1, 13))

    source_schedule = schedule_services.upsert_schedule(
        schedule_services.ENTITY_TASK,
        source_task.id,
        project_id=project.id,
        estimated_start=date(2026, 1, 8),
        due_date=date(2026, 1, 10),
    )
    schedule_services.upsert_schedule(
        schedule_services.ENTITY_TASK,
        target_task.id,
        project_id=project.id,
        estimated_start=date(2026, 1, 11),
        due_date=date(2026, 1, 13),
    )
    ScheduleDependency.objects.create(
        from_schedule=source_schedule,
        to_schedule=schedule_services.get_schedule(schedule_services.ENTITY_TASK, target_task.id),
    )

    payload = {
        "project_id": project.id,
        "bulk_updates": [
            {
                "entity_type": "task",
                "entity_id": target_task.id,
                "start_field": "estimated_start",
                "start": "2026-01-10",
                "due": "2026-01-13",
            }
        ],
    }

    response = client.post(
        "/api/v1/schedule-dependencies/bulk_apply_dates",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert response.status_code == 400

    target_schedule = schedule_services.get_schedule(schedule_services.ENTITY_TASK, target_task.id)
    assert target_schedule.estimated_start == date(2026, 1, 11)
    assert target_schedule.due_date == date(2026, 1, 13)


def test_bulk_apply_dates_syncs_dependency_chain_and_ancestor_bounds():
    project, client = _build_project_client()

    epic = factories.create_epic(project=project, owner=project.owner)
    source_userstory = factories.create_userstory(project=project, due_date=date(2026, 1, 10))
    target_userstory = factories.create_userstory(project=project, due_date=date(2026, 1, 13))
    factories.RelatedUserStory.create(epic=epic, user_story=source_userstory, order=1)
    factories.RelatedUserStory.create(epic=epic, user_story=target_userstory, order=2)

    source_task = factories.create_task(
        project=project,
        user_story=source_userstory,
        due_date=date(2026, 1, 10),
    )
    target_task = factories.create_task(
        project=project,
        user_story=target_userstory,
        due_date=date(2026, 1, 13),
    )

    source_schedule = schedule_services.upsert_schedule(
        schedule_services.ENTITY_TASK,
        source_task.id,
        project_id=project.id,
        estimated_start=date(2026, 1, 8),
        due_date=date(2026, 1, 10),
    )
    target_schedule = schedule_services.upsert_schedule(
        schedule_services.ENTITY_TASK,
        target_task.id,
        project_id=project.id,
        estimated_start=date(2026, 1, 11),
        due_date=date(2026, 1, 13),
    )
    schedule_services.upsert_schedule(
        schedule_services.ENTITY_USERSTORY,
        target_userstory.id,
        project_id=project.id,
        estimated_start=date(2026, 1, 11),
        due_date=date(2026, 1, 13),
    )
    schedule_services.upsert_schedule(
        schedule_services.ENTITY_EPIC,
        epic.id,
        project_id=project.id,
        estimated_start=date(2026, 1, 11),
        due_date=date(2026, 1, 13),
    )

    ScheduleDependency.objects.create(
        from_schedule=source_schedule,
        to_schedule=target_schedule,
    )

    payload = {
        "project_id": project.id,
        "bulk_updates": [
            {
                "entity_type": "task",
                "entity_id": source_task.id,
                "start_field": "estimated_start",
                "start": "2026-01-08",
                "due": "2026-01-14",
            }
        ],
    }

    response = client.post(
        "/api/v1/schedule-dependencies/bulk_apply_dates",
        data=json.dumps(payload),
        content_type="application/json",
    )

    assert response.status_code == 200
    assert json.loads(response.content)["updated"] == 1

    target_task.refresh_from_db()
    target_userstory.refresh_from_db()
    target_schedule = schedule_services.get_schedule(schedule_services.ENTITY_TASK, target_task.id)
    target_userstory_schedule = schedule_services.get_schedule(
        schedule_services.ENTITY_USERSTORY,
        target_userstory.id,
    )
    epic_schedule = schedule_services.get_schedule(
        schedule_services.ENTITY_EPIC,
        epic.id,
    )

    assert target_schedule.estimated_start == date(2026, 1, 15)
    assert target_schedule.due_date == date(2026, 1, 17)
    assert target_task.due_date == date(2026, 1, 17)

    assert target_userstory_schedule.due_date == date(2026, 1, 17)
    assert target_userstory.due_date == date(2026, 1, 17)
    assert epic_schedule.due_date == date(2026, 1, 17)


def test_bulk_apply_dates_emits_realtime_change_events():
    project, client = _build_project_client()

    task = factories.create_task(project=project, due_date=date(2026, 1, 8))
    schedule_services.upsert_schedule(
        schedule_services.ENTITY_TASK,
        task.id,
        project_id=project.id,
        estimated_start=date(2026, 1, 5),
        due_date=date(2026, 1, 8),
    )

    payload = {
        "project_id": project.id,
        "bulk_updates": [
            {
                "entity_type": "task",
                "entity_id": task.id,
                "start_field": "estimated_start",
                "start": "2026-01-10",
                "due": "2026-01-12",
            }
        ],
    }

    with mock.patch(
        "taiga.projects.schedule.services.events.emit_event_for_ids"
    ) as emit_event_for_ids:
        response = client.post(
            "/api/v1/schedule-dependencies/bulk_apply_dates",
            data=json.dumps(payload),
            content_type="application/json",
        )

    assert response.status_code == 200
    emit_event_for_ids.assert_any_call(
        ids=[task.id],
        content_type="tasks.task",
        projectid=project.id,
    )
    emit_event_for_ids.assert_any_call(
        ids=[task.id],
        content_type="schedule.scheduledependency",
        projectid=project.id,
    )
