# -*- coding: utf-8 -*-
# Test: Check that the bulk_create API endpoint creates Schedule entries AND
# that the schedule-items API correctly returns position.

import pytest
import json

from django.test.client import Client

from taiga.projects.epics import services as epic_services
from taiga.projects.schedule import services as schedule_services
from taiga.projects.schedule.models import Schedule, ScheduleItemOrder
from taiga.permissions.choices import MEMBERS_PERMISSIONS
from tests import factories


pytestmark = pytest.mark.django_db


def test_list_api_returns_schedule_position_for_bulk_created_stories():
    """
    After bulk-creating stories under an epic, schedule-items should return
    position values for these stories.
    """
    project = factories.create_project()
    owner = project.owner
    role = factories.RoleFactory.create(
        project=project,
        permissions=list(map(lambda x: x[0], MEMBERS_PERMISSIONS)),
    )
    factories.MembershipFactory.create(project=project, user=owner, role=role)

    epic = factories.create_epic(project=project, owner=owner)

    schedule_services.upsert_schedule(
        schedule_services.ENTITY_EPIC, epic.id, project_id=project.id,
    )

    # Bulk create stories
    related = epic_services.create_related_userstories_in_bulk(
        "Story Alpha\nStory Beta\nStory Gamma",
        epic,
        project=project,
        owner=owner,
    )
    us_ids = [r.user_story_id for r in related]

    # Check that Schedule entries exist for all stories
    for us_id in us_ids:
        sched = Schedule.objects.filter(entity_type="userstory", entity_id=us_id).first()
        assert sched is not None, f"No Schedule entry for US {us_id}"
        print(f"US {us_id}: Schedule id={sched.id}")

        item_order = ScheduleItemOrder.objects.filter(schedule=sched).first()
        assert item_order is not None, f"No ScheduleItemOrder for US {us_id}"
        print(f"US {us_id}: ScheduleItemOrder position={item_order.position}, parent_type={item_order.parent_entity_type}, parent_id={item_order.parent_entity_id}")

    # Load schedule overlays via API.
    client = Client()
    client.force_login(owner)

    response = client.get(
        "/api/v1/schedule-items",
        {"project": project.id},
    )
    assert response.status_code == 200

    schedule_items = json.loads(response.content)
    stories = [
        item
        for item in schedule_items
        if item["entity_type"] == "userstory" and item["entity_id"] in us_ids
    ]
    print(f"\nAPI response ({len(stories)} story schedule items):")
    for story in stories:
        print(f"  US {story['entity_id']}: schedule_id={story.get('schedule_id')}, position={story.get('position')}")
        assert story.get("schedule_id") is not None, f"US {story['entity_id']} missing schedule_id"
        assert story.get("position") is not None, f"US {story['entity_id']} missing position"
        assert story["position"] > 0, f"US {story['entity_id']} has invalid position"

    # Verify positions are contiguous and unique
    positions = sorted([s["position"] for s in stories])
    assert positions == list(range(1, len(stories) + 1)), f"Expected contiguous positions 1..{len(stories)}, got {positions}"
    print(f"\nAll positions verified: {positions}")
