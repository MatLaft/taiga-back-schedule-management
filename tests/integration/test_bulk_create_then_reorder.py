# -*- coding: utf-8 -*-
# Reproduction test: bulk-create userstories under an epic, then reorder via schedule item order.

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


def test_reorder_after_bulk_create_related_userstories():
    """After bulk-creating userstories inside an epic, reordering them
    via set_schedule_item_order_position should work correctly."""
    project = factories.create_project()
    owner = project.owner
    epic = factories.create_epic(project=project, owner=owner)

    # Ensure epic has a schedule entry
    schedule_services.upsert_schedule(
        schedule_services.ENTITY_EPIC, epic.id, project_id=project.id,
    )

    # Bulk-create 3 userstories inside the epic
    bulk_data = "Story A\nStory B\nStory C"
    related_userstories = epic_services.create_related_userstories_in_bulk(
        bulk_data,
        epic,
        project=project,
        owner=owner,
    )

    userstory_ids = [rus.user_story_id for rus in related_userstories]
    assert len(userstory_ids) == 3

    # Check initial positions — all should be under the epic group
    positions_before = _get_group_positions(
        project.id,
        schedule_services.ENTITY_USERSTORY,
        parent_entity_type=schedule_services.ENTITY_EPIC,
        parent_entity_id=epic.id,
    )
    print("Positions before reorder:", positions_before)
    assert len(positions_before) == 3
    # Should have positions 1, 2, 3
    assert [p for _, p in positions_before] == [1, 2, 3]

    # Now try to reorder: move the last story (position 3) to position 1
    last_us_id = positions_before[2][0]
    result = schedule_services.set_schedule_item_order_position(
        schedule_services.ENTITY_USERSTORY,
        last_us_id,
        1,
    )
    assert result is not None, "set_schedule_item_order_position returned None!"

    positions_after = _get_group_positions(
        project.id,
        schedule_services.ENTITY_USERSTORY,
        parent_entity_type=schedule_services.ENTITY_EPIC,
        parent_entity_id=epic.id,
    )
    print("Positions after reorder:", positions_after)
    assert len(positions_after) == 3
    # The last story should now be at position 1
    assert positions_after[0][0] == last_us_id
    assert [p for _, p in positions_after] == [1, 2, 3]


def test_reorder_after_bulk_create_does_not_create_duplicate_groups():
    """Bulk-created userstories should not end up in the root group
    AND the epic group simultaneously."""
    project = factories.create_project()
    owner = project.owner
    epic = factories.create_epic(project=project, owner=owner)

    schedule_services.upsert_schedule(
        schedule_services.ENTITY_EPIC, epic.id, project_id=project.id,
    )

    bulk_data = "Story X\nStory Y"
    related_userstories = epic_services.create_related_userstories_in_bulk(
        bulk_data,
        epic,
        project=project,
        owner=owner,
    )

    userstory_ids = [rus.user_story_id for rus in related_userstories]

    # Should be in the epic group
    epic_group_positions = _get_group_positions(
        project.id,
        schedule_services.ENTITY_USERSTORY,
        parent_entity_type=schedule_services.ENTITY_EPIC,
        parent_entity_id=epic.id,
    )
    print("Epic group positions:", epic_group_positions)

    # Should NOT be in the root group
    root_group_positions = _get_group_positions(
        project.id,
        schedule_services.ENTITY_USERSTORY,
    )
    print("Root group positions:", root_group_positions)

    # All bulk-created stories should be ONLY under the epic
    epic_group_us_ids = {entity_id for entity_id, _ in epic_group_positions}
    root_group_us_ids = {entity_id for entity_id, _ in root_group_positions}

    for us_id in userstory_ids:
        assert us_id in epic_group_us_ids, f"US {us_id} missing from epic group"
        assert us_id not in root_group_us_ids, f"US {us_id} should NOT be in root group"


def test_reorder_bulk_created_stories_with_preexisting_stories():
    """Test reordering when an epic already has stories and more are added in bulk."""
    project = factories.create_project()
    owner = project.owner
    epic = factories.create_epic(project=project, owner=owner)

    schedule_services.upsert_schedule(
        schedule_services.ENTITY_EPIC, epic.id, project_id=project.id,
    )

    # Create a pre-existing userstory under the epic
    existing_us = factories.create_userstory(project=project, owner=owner)
    RelatedUserStory.objects.create(epic=epic, user_story=existing_us, order=1)
    schedule_services.upsert_schedule(
        schedule_services.ENTITY_USERSTORY, existing_us.id, project_id=project.id,
    )

    # Verify pre-existing position
    positions_initial = _get_group_positions(
        project.id,
        schedule_services.ENTITY_USERSTORY,
        parent_entity_type=schedule_services.ENTITY_EPIC,
        parent_entity_id=epic.id,
    )
    print("Initial positions:", positions_initial)
    assert len(positions_initial) == 1

    # Bulk-create 2 more stories
    bulk_data = "Bulk Story 1\nBulk Story 2"
    related_userstories = epic_services.create_related_userstories_in_bulk(
        bulk_data,
        epic,
        project=project,
        owner=owner,
    )

    positions_after_bulk = _get_group_positions(
        project.id,
        schedule_services.ENTITY_USERSTORY,
        parent_entity_type=schedule_services.ENTITY_EPIC,
        parent_entity_id=epic.id,
    )
    print("Positions after bulk:", positions_after_bulk)
    assert len(positions_after_bulk) == 3
    assert [p for _, p in positions_after_bulk] == [1, 2, 3]

    # Now reorder: move the last (3rd) story to position 1
    last_us_id = positions_after_bulk[2][0]
    result = schedule_services.set_schedule_item_order_position(
        schedule_services.ENTITY_USERSTORY,
        last_us_id,
        1,
    )
    assert result is not None, "Reorder failed — returned None!"

    positions_final = _get_group_positions(
        project.id,
        schedule_services.ENTITY_USERSTORY,
        parent_entity_type=schedule_services.ENTITY_EPIC,
        parent_entity_id=epic.id,
    )
    print("Positions final:", positions_final)
    assert len(positions_final) == 3
    assert positions_final[0][0] == last_us_id
    assert [p for _, p in positions_final] == [1, 2, 3]
