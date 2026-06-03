# -*- coding: utf-8 -*-

import json

import pytest
from django.test.client import Client

from taiga.permissions.choices import MEMBERS_PERMISSIONS
from taiga.projects.schedule import models as schedule_models
from tests import factories


pytestmark = pytest.mark.django_db


def _build_project_client_with_perms(permissions_keep):
    project = factories.create_project()
    owner = project.owner
    role = factories.RoleFactory.create(
        project=project,
        permissions=list(permissions_keep),
    )
    factories.MembershipFactory.create(project=project, user=owner, role=role)

    client = Client()
    client.force_login(owner)
    return project, owner, client


def _all_perms_except(*excluded):
    excluded_set = set(excluded)
    return [p[0] for p in MEMBERS_PERMISSIONS if p[0] not in excluded_set]


def _get_schedule(entity_type, entity_id):
    return schedule_models.Schedule.objects.filter(
        entity_type=entity_type, entity_id=entity_id
    ).first()


def test_update_dates_writes_estimated_start_for_task():
    project, owner, client = _build_project_client_with_perms(
        _all_perms_except()
    )
    task = factories.create_task(project=project, owner=owner)

    payload = {
        "project": project.id,
        "entity_type": "task",
        "entity_id": task.id,
        "estimated_start": "2026-04-01",
    }
    response = client.post(
        "/api/v1/schedule-items/update_dates",
        data=json.dumps(payload),
        content_type="application/json",
    )

    assert response.status_code == 200
    body = response.json()
    assert body["estimated_start"] == "2026-04-01"
    assert body["entity_type"] == "task"

    schedule = _get_schedule("task", task.id)
    assert schedule is not None
    assert schedule.estimated_start.isoformat() == "2026-04-01"


def test_update_dates_writes_actual_start_for_userstory():
    project, owner, client = _build_project_client_with_perms(
        _all_perms_except()
    )
    userstory = factories.create_userstory(project=project, owner=owner)

    payload = {
        "project": project.id,
        "entity_type": "userstory",
        "entity_id": userstory.id,
        "actual_start": "2026-05-01",
    }
    response = client.post(
        "/api/v1/schedule-items/update_dates",
        data=json.dumps(payload),
        content_type="application/json",
    )

    assert response.status_code == 200
    schedule = _get_schedule("userstory", userstory.id)
    assert schedule.actual_start.isoformat() == "2026-05-01"


def test_update_dates_requires_modify_schedule_dates_permission():
    project, owner, client = _build_project_client_with_perms(
        _all_perms_except("modify_schedule_dates")
    )
    task = factories.create_task(project=project, owner=owner)

    payload = {
        "project": project.id,
        "entity_type": "task",
        "entity_id": task.id,
        "estimated_start": "2026-04-01",
    }
    response = client.post(
        "/api/v1/schedule-items/update_dates",
        data=json.dumps(payload),
        content_type="application/json",
    )

    assert response.status_code == 403


def test_update_dates_requires_view_schedule_or_view_gantt():
    project, owner, client = _build_project_client_with_perms(
        _all_perms_except("view_schedule", "view_gantt")
    )
    task = factories.create_task(project=project, owner=owner)

    payload = {
        "project": project.id,
        "entity_type": "task",
        "entity_id": task.id,
        "estimated_start": "2026-04-01",
    }
    response = client.post(
        "/api/v1/schedule-items/update_dates",
        data=json.dumps(payload),
        content_type="application/json",
    )

    assert response.status_code == 403


def test_update_dates_rejects_entity_from_other_project():
    project, owner, client = _build_project_client_with_perms(
        _all_perms_except()
    )
    other_project = factories.create_project()
    task_other = factories.create_task(project=other_project, owner=other_project.owner)

    payload = {
        "project": project.id,
        "entity_type": "task",
        "entity_id": task_other.id,
        "estimated_start": "2026-04-01",
    }
    response = client.post(
        "/api/v1/schedule-items/update_dates",
        data=json.dumps(payload),
        content_type="application/json",
    )

    assert response.status_code in (400, 404)


def test_update_dates_requires_at_least_one_date_field():
    project, owner, client = _build_project_client_with_perms(
        _all_perms_except()
    )
    task = factories.create_task(project=project, owner=owner)

    payload = {
        "project": project.id,
        "entity_type": "task",
        "entity_id": task.id,
    }
    response = client.post(
        "/api/v1/schedule-items/update_dates",
        data=json.dumps(payload),
        content_type="application/json",
    )

    assert response.status_code == 400


def test_core_entity_patch_no_longer_writes_estimated_start():
    """estimated_start sent via core entity PATCH is silently dropped (validator removed)."""
    project, owner, client = _build_project_client_with_perms(
        _all_perms_except()
    )
    task = factories.create_task(project=project, owner=owner)

    response = client.patch(
        "/api/v1/tasks/{}?include_schedule=true".format(task.id),
        data=json.dumps({"estimated_start": "2026-04-01", "version": task.version}),
        content_type="application/json",
    )

    # PATCH succeeds (no validator error) but estimated_start is NOT written to schedule.
    assert response.status_code == 200
    schedule = _get_schedule("task", task.id)
    assert schedule is None or schedule.estimated_start is None
