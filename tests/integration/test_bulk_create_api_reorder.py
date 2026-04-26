# -*- coding: utf-8 -*-
# Test: bulk-create userstories via API, then reorder via PATCH with position attribute.

import pytest
import json

from django.test.client import Client

from taiga.projects.epics.models import RelatedUserStory
from taiga.projects.epics import services as epic_services
from taiga.projects.schedule import services as schedule_services
from taiga.projects.schedule.models import ScheduleItemOrder
from taiga.permissions.choices import MEMBERS_PERMISSIONS
from tests import factories


pytestmark = pytest.mark.django_db


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


def test_api_patch_reorder_after_bulk_create():
    """
    Simulate the exact API call made by the Gantt frontend:
    1. Bulk-create userstories under epic (via service)
    2. PATCH /api/v1/userstories/{id}?include_schedule=true with `position` attribute
    """
    project = factories.create_project()
    owner = project.owner
    role = factories.RoleFactory.create(
        project=project,
        permissions=list(map(lambda x: x[0], MEMBERS_PERMISSIONS)),
    )
    membership = factories.MembershipFactory.create(
        project=project, user=owner, role=role,
    )

    epic = factories.create_epic(project=project, owner=owner)

    # Ensure epic has schedule
    schedule_services.upsert_schedule(
        schedule_services.ENTITY_EPIC, epic.id, project_id=project.id,
    )

    # Bulk create 3 stories under the epic
    bulk_data = "API Story 1\nAPI Story 2\nAPI Story 3"
    related_userstories = epic_services.create_related_userstories_in_bulk(
        bulk_data,
        epic,
        project=project,
        owner=owner,
    )
    assert len(related_userstories) == 3

    # Get positions in the epic group
    positions_after_bulk = _get_group_positions(
        project.id,
        schedule_services.ENTITY_USERSTORY,
        parent_entity_type=schedule_services.ENTITY_EPIC,
        parent_entity_id=epic.id,
    )
    print("Positions after bulk create:", positions_after_bulk)
    assert len(positions_after_bulk) == 3
    assert [p for _, p in positions_after_bulk] == [1, 2, 3]

    # Now simulate what the Gantt frontend does: PATCH to reorder
    last_us_id = positions_after_bulk[2][0]
    first_us_id = positions_after_bulk[0][0]

    client = Client()
    client.force_login(owner)

    # First, load the userstory to get its version and schedule_position
    get_response = client.get(
        f"/api/v1/userstories/{last_us_id}",
        {"include_schedule": "true"},
        content_type="application/json",
    )
    assert get_response.status_code == 200, f"GET failed: {get_response.status_code}"
    us_data = json.loads(get_response.content)
    print(f"US {last_us_id} data: version={us_data.get('version')}, schedule_position={us_data.get('schedule_position')}")

    # PATCH to reorder: move last story to position 1
    patch_data = {
        "position": 1,
        "version": us_data["version"],
    }
    patch_response = client.patch(
        f"/api/v1/userstories/{last_us_id}?include_schedule=true",
        data=json.dumps(patch_data),
        content_type="application/json",
    )
    print(f"PATCH response status: {patch_response.status_code}")
    if patch_response.status_code != 200:
        try:
            print(f"PATCH response body: {json.loads(patch_response.content)}")
        except:
            print(f"PATCH response body: {patch_response.content}")

    assert patch_response.status_code == 200, f"PATCH failed: {patch_response.status_code}"

    patch_result = json.loads(patch_response.content)
    print(f"PATCH result schedule_position: {patch_result.get('schedule_position')}")

    # Check positions after reorder
    positions_after_reorder = _get_group_positions(
        project.id,
        schedule_services.ENTITY_USERSTORY,
        parent_entity_type=schedule_services.ENTITY_EPIC,
        parent_entity_id=epic.id,
    )
    print("Positions after reorder:", positions_after_reorder)
    assert len(positions_after_reorder) == 3, f"Expected 3 items, got {len(positions_after_reorder)}"

    # The last story should now be at position 1
    assert positions_after_reorder[0][0] == last_us_id, (
        f"Expected US {last_us_id} at position 1, but got US {positions_after_reorder[0][0]}"
    )
    assert [p for _, p in positions_after_reorder] == [1, 2, 3]

    # Verify the response includes correct schedule_position
    assert patch_result.get("schedule_position") == 1, (
        f"Expected schedule_position=1 in response, got {patch_result.get('schedule_position')}"
    )
