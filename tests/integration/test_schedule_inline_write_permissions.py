# -*- coding: utf-8 -*-

import json
from datetime import date

import pytest
from django.test.client import Client

from taiga.permissions.choices import MEMBERS_PERMISSIONS
from tests import factories


pytestmark = pytest.mark.django_db


def _build_project_client_without(permission_codename):
    project = factories.create_project()
    owner = project.owner
    role_permissions = [
        permission[0]
        for permission in MEMBERS_PERMISSIONS
        if permission[0] != permission_codename
    ]
    role = factories.RoleFactory.create(
        project=project,
        permissions=role_permissions,
    )
    factories.MembershipFactory.create(project=project, user=owner, role=role)

    client = Client()
    client.force_login(owner)
    return project, owner, client


def test_userstory_schedule_position_update_requires_modify_gantt_list_order():
    project, owner, client = _build_project_client_without("modify_gantt_list_order")

    epic = factories.create_epic(project=project, owner=owner)
    userstory = factories.create_userstory(project=project, owner=owner)
    factories.RelatedUserStory.create(epic=epic, user_story=userstory, order=1)

    response = client.post(
        "/api/v1/schedule-items/update_item",
        data=json.dumps({
            "project": project.id,
            "entity_type": "userstory",
            "entity_id": userstory.id,
            "position": 1,
        }),
        content_type="application/json",
    )

    assert response.status_code == 403


def test_epic_schedule_color_update_requires_modify_schedule_color():
    project, owner, client = _build_project_client_without("modify_schedule_color")

    epic = factories.create_epic(
        project=project,
        owner=owner,
        color="#111111",
    )

    response = client.post(
        "/api/v1/schedule-items/update_item",
        data=json.dumps({
            "project": project.id,
            "entity_type": "epic",
            "entity_id": epic.id,
            "color": "#ff0000",
        }),
        content_type="application/json",
    )

    assert response.status_code == 403

    epic.refresh_from_db()
    assert epic.color == "#111111"


def test_task_schedule_due_date_update_requires_modify_schedule_dates():
    project, owner, client = _build_project_client_without("modify_schedule_dates")

    task = factories.create_task(
        project=project,
        owner=owner,
        due_date=date(2026, 1, 10),
    )

    response = client.post(
        "/api/v1/schedule-items/update_item",
        data=json.dumps({
            "project": project.id,
            "entity_type": "task",
            "entity_id": task.id,
            "due_date": "2026-01-15",
        }),
        content_type="application/json",
    )

    assert response.status_code == 403

    task.refresh_from_db()
    assert task.due_date == date(2026, 1, 10)
