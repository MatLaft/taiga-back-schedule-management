# -*- coding: utf-8 -*-
# Deeper investigation: test various scenarios where bulk ordering might break

import pytest

from taiga.projects.epics.models import RelatedUserStory
from taiga.projects.epics import services as epic_services
from taiga.projects.schedule import services as schedule_services
from taiga.projects.schedule.models import ScheduleItemOrder
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


def test_multiple_bulk_creates_maintain_ordering():
    """Multiple sequential bulk creates should produce valid ordering."""
    project = factories.create_project()
    owner = project.owner
    epic = factories.create_epic(project=project, owner=owner)

    schedule_services.upsert_schedule(
        schedule_services.ENTITY_EPIC, epic.id, project_id=project.id,
    )

    # First bulk create
    bulk1 = epic_services.create_related_userstories_in_bulk(
        "Batch1 Story A\nBatch1 Story B",
        epic,
        project=project,
        owner=owner,
    )

    pos1 = _get_group_positions(
        project.id,
        schedule_services.ENTITY_USERSTORY,
        parent_entity_type=schedule_services.ENTITY_EPIC,
        parent_entity_id=epic.id,
    )
    print("After first bulk:", pos1)
    positions_only = [p for _, p in pos1]
    assert positions_only == sorted(positions_only), f"Positions not sorted: {positions_only}"
    assert len(set(positions_only)) == len(positions_only), f"Duplicate positions: {positions_only}"

    # Second bulk create
    bulk2 = epic_services.create_related_userstories_in_bulk(
        "Batch2 Story C\nBatch2 Story D",
        epic,
        project=project,
        owner=owner,
    )

    pos2 = _get_group_positions(
        project.id,
        schedule_services.ENTITY_USERSTORY,
        parent_entity_type=schedule_services.ENTITY_EPIC,
        parent_entity_id=epic.id,
    )
    print("After second bulk:", pos2)
    positions_only2 = [p for _, p in pos2]
    assert positions_only2 == sorted(positions_only2), f"Positions not sorted: {positions_only2}"
    assert len(set(positions_only2)) == len(positions_only2), f"Duplicate positions: {positions_only2}"
    assert positions_only2 == [1, 2, 3, 4], f"Expected [1,2,3,4], got {positions_only2}"

    # Try reordering after multiple bulk creates
    last_us_id = pos2[3][0]
    result = schedule_services.set_schedule_item_order_position(
        schedule_services.ENTITY_USERSTORY,
        last_us_id,
        1,
    )
    assert result is not None

    pos3 = _get_group_positions(
        project.id,
        schedule_services.ENTITY_USERSTORY,
        parent_entity_type=schedule_services.ENTITY_EPIC,
        parent_entity_id=epic.id,
    )
    print("After reorder:", pos3)
    assert pos3[0][0] == last_us_id
    assert [p for _, p in pos3] == [1, 2, 3, 4]


def test_bulk_create_with_userstory_in_multiple_epics():
    """User stories belonging to multiple epics should still have correct positions."""
    project = factories.create_project()
    owner = project.owner
    epic1 = factories.create_epic(project=project, owner=owner)
    epic2 = factories.create_epic(project=project, owner=owner)

    schedule_services.upsert_schedule(
        schedule_services.ENTITY_EPIC, epic1.id, project_id=project.id,
    )
    schedule_services.upsert_schedule(
        schedule_services.ENTITY_EPIC, epic2.id, project_id=project.id,
    )

    # Create stories in epic1
    bulk1 = epic_services.create_related_userstories_in_bulk(
        "E1 Story A\nE1 Story B",
        epic1,
        project=project,
        owner=owner,
    )

    # Create stories in epic2
    bulk2 = epic_services.create_related_userstories_in_bulk(
        "E2 Story C\nE2 Story D",
        epic2,
        project=project,
        owner=owner,
    )

    pos_epic1 = _get_group_positions(
        project.id,
        schedule_services.ENTITY_USERSTORY,
        parent_entity_type=schedule_services.ENTITY_EPIC,
        parent_entity_id=epic1.id,
    )
    pos_epic2 = _get_group_positions(
        project.id,
        schedule_services.ENTITY_USERSTORY,
        parent_entity_type=schedule_services.ENTITY_EPIC,
        parent_entity_id=epic2.id,
    )
    print(f"Epic1 positions: {pos_epic1}")
    print(f"Epic2 positions: {pos_epic2}")
    assert [p for _, p in pos_epic1] == [1, 2]
    assert [p for _, p in pos_epic2] == [1, 2]

    # Reorder in epic1
    result = schedule_services.set_schedule_item_order_position(
        schedule_services.ENTITY_USERSTORY,
        pos_epic1[1][0],
        1,
    )
    assert result is not None

    pos_epic1_after = _get_group_positions(
        project.id,
        schedule_services.ENTITY_USERSTORY,
        parent_entity_type=schedule_services.ENTITY_EPIC,
        parent_entity_id=epic1.id,
    )
    print(f"Epic1 positions after reorder: {pos_epic1_after}")
    assert pos_epic1_after[0][0] == pos_epic1[1][0]
    assert [p for _, p in pos_epic1_after] == [1, 2]


def test_add_existing_userstory_to_epic_then_bulk_create():
    """Add existing userstory to an epic, then bulk-create more, then reorder."""
    project = factories.create_project()
    owner = project.owner
    epic = factories.create_epic(project=project, owner=owner)

    schedule_services.upsert_schedule(
        schedule_services.ENTITY_EPIC, epic.id, project_id=project.id,
    )

    # Create a standalone userstory not related to any epic
    us_existing = factories.create_userstory(project=project, owner=owner)
    schedule_services.upsert_schedule(
        schedule_services.ENTITY_USERSTORY, us_existing.id, project_id=project.id,
    )

    # Check it's in the root group
    root_pos = _get_group_positions(
        project.id,
        schedule_services.ENTITY_USERSTORY,
    )
    print(f"Root group before: {root_pos}")
    assert len(root_pos) == 1

    # Add it to the epic
    RelatedUserStory.objects.create(epic=epic, user_story=us_existing, order=1)

    # Re-sync the schedule for this userstory
    schedule_services.sync_schedule_item_order(
        schedule_services.ENTITY_USERSTORY,
        us_existing.id,
    )

    epic_pos_before = _get_group_positions(
        project.id,
        schedule_services.ENTITY_USERSTORY,
        parent_entity_type=schedule_services.ENTITY_EPIC,
        parent_entity_id=epic.id,
    )
    print(f"Epic group after adding existing US: {epic_pos_before}")

    # Bulk create more stories
    bulk = epic_services.create_related_userstories_in_bulk(
        "Bulk A\nBulk B",
        epic,
        project=project,
        owner=owner,
    )

    epic_pos_after_bulk = _get_group_positions(
        project.id,
        schedule_services.ENTITY_USERSTORY,
        parent_entity_type=schedule_services.ENTITY_EPIC,
        parent_entity_id=epic.id,
    )
    print(f"Epic group after bulk create: {epic_pos_after_bulk}")
    positions = [p for _, p in epic_pos_after_bulk]
    assert positions == sorted(positions), f"Positions not sorted: {positions}"
    assert len(set(positions)) == len(positions), f"Duplicate positions: {positions}"
    assert len(epic_pos_after_bulk) == 3

    # Try reorder
    last_us_id = epic_pos_after_bulk[2][0]
    result = schedule_services.set_schedule_item_order_position(
        schedule_services.ENTITY_USERSTORY,
        last_us_id,
        1,
    )
    assert result is not None

    epic_pos_final = _get_group_positions(
        project.id,
        schedule_services.ENTITY_USERSTORY,
        parent_entity_type=schedule_services.ENTITY_EPIC,
        parent_entity_id=epic.id,
    )
    print(f"Epic group after reorder: {epic_pos_final}")
    assert epic_pos_final[0][0] == last_us_id
    assert [p for _, p in epic_pos_final] == [1, 2, 3]
