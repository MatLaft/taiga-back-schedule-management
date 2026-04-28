# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos INC

from datetime import date
from types import SimpleNamespace

import pytest
from django.core.exceptions import ValidationError

from taiga.projects.epics.models import RelatedUserStory
from taiga.projects.schedule import services as schedule_services
from taiga.projects.schedule.models import Schedule
from taiga.projects.schedule.models import ScheduleDependency
from tests import factories


pytestmark = pytest.mark.django_db


def _create_schedule(entity_id, **kwargs):
    data = {
        "entity_type": Schedule.TYPE_TASK,
        "entity_id": entity_id,
        "project_id": 1,
    }
    data.update(kwargs)
    return Schedule.objects.create(**data)


def test_schedule_dependency_accepts_target_start_after_source_due_date():
    source = _create_schedule(1, due_date=date(2026, 4, 10))
    target = _create_schedule(2, actual_start=date(2026, 4, 11))

    dependency = ScheduleDependency.objects.create(
        from_schedule=source,
        to_schedule=target,
    )

    assert dependency.from_schedule == source
    assert dependency.to_schedule == target


def test_schedule_dependency_uses_estimated_start_when_target_has_no_actual_start():
    source = _create_schedule(1, due_date=date(2026, 4, 10))
    target = _create_schedule(2, estimated_start=date(2026, 4, 11))

    dependency = ScheduleDependency.objects.create(
        from_schedule=source,
        to_schedule=target,
    )

    assert dependency.from_schedule == source
    assert dependency.to_schedule == target


def test_schedule_dependency_rejects_target_start_on_or_before_source_due_date():
    source = _create_schedule(1, due_date=date(2026, 4, 10))
    target = _create_schedule(2, actual_start=date(2026, 4, 10))

    with pytest.raises(ValidationError):
        ScheduleDependency.objects.create(
            from_schedule=source,
            to_schedule=target,
        )


def test_schedule_dependency_rejects_target_without_start_date():
    source = _create_schedule(1, due_date=date(2026, 4, 10))
    target = _create_schedule(2)

    with pytest.raises(ValidationError):
        ScheduleDependency.objects.create(
            from_schedule=source,
            to_schedule=target,
        )


def test_schedule_dependency_rejects_source_without_due_date():
    source = _create_schedule(1)
    target = _create_schedule(2, actual_start=date(2026, 4, 11))

    with pytest.raises(ValidationError):
        ScheduleDependency.objects.create(
            from_schedule=source,
            to_schedule=target,
        )


def test_schedule_dependency_rejects_self_dependency():
    source = _create_schedule(1, due_date=date(2026, 4, 10))

    with pytest.raises(ValidationError):
        ScheduleDependency.objects.create(
            from_schedule=source,
            to_schedule=source,
        )


def test_schedule_dependency_rejects_cross_project_dependency():
    source = _create_schedule(1, project_id=1, due_date=date(2026, 4, 10))
    target = _create_schedule(2, project_id=2, actual_start=date(2026, 4, 11))

    with pytest.raises(ValidationError):
        ScheduleDependency.objects.create(
            from_schedule=source,
            to_schedule=target,
        )


def test_dependency_start_violation_blocks_when_target_starts_on_or_before_source_due():
    source = _create_schedule(1, due_date=date(2026, 4, 10))
    target = _create_schedule(2, estimated_start=date(2026, 4, 11))

    ScheduleDependency.objects.create(
        from_schedule=source,
        to_schedule=target,
    )

    updated_target = SimpleNamespace(
        id=target.entity_id,
        estimated_start=date(2026, 4, 10),
    )

    error = schedule_services.get_dependency_start_violation_error(
        updated_target,
        schedule_services.ENTITY_TASK,
    )

    assert error is not None


def test_dependency_start_violation_allows_when_target_starts_after_source_due():
    source = _create_schedule(1, due_date=date(2026, 4, 10))
    target = _create_schedule(2, estimated_start=date(2026, 4, 11))

    ScheduleDependency.objects.create(
        from_schedule=source,
        to_schedule=target,
    )

    updated_target = SimpleNamespace(
        id=target.entity_id,
        estimated_start=date(2026, 4, 12),
    )

    error = schedule_services.get_dependency_start_violation_error(
        updated_target,
        schedule_services.ENTITY_TASK,
    )

    assert error is None


def test_ancestor_dependency_violation_blocks_when_task_would_pull_userstory_start_too_early():
    project = factories.create_project()
    source = factories.create_task(project=project, due_date=date(2026, 1, 10))
    target_userstory = factories.create_userstory(project=project, due_date=date(2026, 1, 20))
    child_task = factories.create_task(
        project=project,
        user_story=target_userstory,
        due_date=date(2026, 1, 16),
    )

    source_schedule = schedule_services.upsert_schedule(
        schedule_services.ENTITY_TASK,
        source.id,
        project_id=project.id,
        estimated_start=date(2026, 1, 1),
        due_date=date(2026, 1, 10),
    )
    target_userstory_schedule = schedule_services.upsert_schedule(
        schedule_services.ENTITY_USERSTORY,
        target_userstory.id,
        project_id=project.id,
        estimated_start=date(2026, 1, 12),
        due_date=date(2026, 1, 20),
    )
    schedule_services.upsert_schedule(
        schedule_services.ENTITY_TASK,
        child_task.id,
        project_id=project.id,
        estimated_start=date(2026, 1, 12),
        due_date=date(2026, 1, 16),
    )

    ScheduleDependency.objects.create(
        from_schedule=source_schedule,
        to_schedule=target_userstory_schedule,
    )

    updated_task = SimpleNamespace(
        id=child_task.id,
        user_story_id=target_userstory.id,
        estimated_start=date(2026, 1, 9),
    )

    error = schedule_services.get_ancestor_dependency_start_violation_error(
        updated_task,
        schedule_services.ENTITY_TASK,
    )

    assert error is not None


def test_ancestor_dependency_violation_allows_when_task_keeps_userstory_start_after_dependency():
    project = factories.create_project()
    source = factories.create_task(project=project, due_date=date(2026, 1, 10))
    target_userstory = factories.create_userstory(project=project, due_date=date(2026, 1, 20))
    child_task = factories.create_task(
        project=project,
        user_story=target_userstory,
        due_date=date(2026, 1, 16),
    )

    source_schedule = schedule_services.upsert_schedule(
        schedule_services.ENTITY_TASK,
        source.id,
        project_id=project.id,
        estimated_start=date(2026, 1, 1),
        due_date=date(2026, 1, 10),
    )
    target_userstory_schedule = schedule_services.upsert_schedule(
        schedule_services.ENTITY_USERSTORY,
        target_userstory.id,
        project_id=project.id,
        estimated_start=date(2026, 1, 12),
        due_date=date(2026, 1, 20),
    )
    schedule_services.upsert_schedule(
        schedule_services.ENTITY_TASK,
        child_task.id,
        project_id=project.id,
        estimated_start=date(2026, 1, 12),
        due_date=date(2026, 1, 16),
    )

    ScheduleDependency.objects.create(
        from_schedule=source_schedule,
        to_schedule=target_userstory_schedule,
    )

    updated_task = SimpleNamespace(
        id=child_task.id,
        user_story_id=target_userstory.id,
        estimated_start=date(2026, 1, 11),
    )

    error = schedule_services.get_ancestor_dependency_start_violation_error(
        updated_task,
        schedule_services.ENTITY_TASK,
    )

    assert error is None


def test_propagates_forward_dependency_chain_preserving_duration():
    schedule_a = _create_schedule(
        1,
        estimated_start=date(2026, 1, 1),
        due_date=date(2026, 1, 10),
    )
    schedule_b = _create_schedule(
        2,
        estimated_start=date(2026, 1, 13),
        due_date=date(2026, 1, 16),
    )
    schedule_c = _create_schedule(
        3,
        estimated_start=date(2026, 1, 17),
        due_date=date(2026, 1, 20),
    )

    ScheduleDependency.objects.create(from_schedule=schedule_a, to_schedule=schedule_b)
    ScheduleDependency.objects.create(from_schedule=schedule_b, to_schedule=schedule_c)

    Schedule.objects.filter(id=schedule_a.id).update(due_date=date(2026, 1, 14))
    schedule_services.propagate_dependency_chain_forward_from_schedule(schedule_a.id)

    schedule_b.refresh_from_db()
    schedule_c.refresh_from_db()

    assert schedule_b.estimated_start == date(2026, 1, 15)
    assert schedule_b.due_date == date(2026, 1, 18)
    assert schedule_c.estimated_start == date(2026, 1, 19)
    assert schedule_c.due_date == date(2026, 1, 22)


def test_propagation_uses_most_restrictive_incoming_dependency():
    schedule_a = _create_schedule(
        1,
        estimated_start=date(2026, 1, 1),
        due_date=date(2026, 1, 10),
    )
    schedule_b = _create_schedule(
        2,
        estimated_start=date(2026, 1, 1),
        due_date=date(2026, 1, 12),
    )
    target = _create_schedule(
        3,
        estimated_start=date(2026, 1, 13),
        due_date=date(2026, 1, 16),
    )

    ScheduleDependency.objects.create(from_schedule=schedule_a, to_schedule=target)
    ScheduleDependency.objects.create(from_schedule=schedule_b, to_schedule=target)

    Schedule.objects.filter(id=schedule_a.id).update(due_date=date(2026, 1, 14))
    schedule_services.propagate_dependency_chain_forward_from_schedule(schedule_a.id)

    target.refresh_from_db()

    assert target.estimated_start == date(2026, 1, 15)
    assert target.due_date == date(2026, 1, 18)


def test_propagation_does_not_pull_targets_backwards():
    source = _create_schedule(
        1,
        estimated_start=date(2026, 1, 1),
        due_date=date(2026, 1, 10),
    )
    target = _create_schedule(
        2,
        estimated_start=date(2026, 1, 13),
        due_date=date(2026, 1, 16),
    )

    ScheduleDependency.objects.create(from_schedule=source, to_schedule=target)

    Schedule.objects.filter(id=source.id).update(due_date=date(2026, 1, 7))
    schedule_services.propagate_dependency_chain_forward_from_schedule(source.id)

    target.refresh_from_db()
    assert target.estimated_start == date(2026, 1, 13)
    assert target.due_date == date(2026, 1, 16)


def test_propagation_expands_ancestors_for_shifted_targets_in_dependency_chain():
    project = factories.create_project()

    epic_1 = factories.create_epic(project=project)
    epic_2 = factories.create_epic(project=project)

    source_userstory = factories.create_userstory(project=project, due_date=date(2026, 1, 10))
    target_userstory_1 = factories.create_userstory(project=project, due_date=date(2026, 1, 13))
    target_userstory_2 = factories.create_userstory(project=project, due_date=date(2026, 1, 16))

    RelatedUserStory.objects.create(epic=epic_1, user_story=source_userstory, order=1)
    RelatedUserStory.objects.create(epic=epic_1, user_story=target_userstory_1, order=2)
    RelatedUserStory.objects.create(epic=epic_2, user_story=target_userstory_2, order=1)

    source_task = factories.create_task(
        project=project,
        user_story=source_userstory,
        due_date=date(2026, 1, 10),
    )
    target_task_1 = factories.create_task(
        project=project,
        user_story=target_userstory_1,
        due_date=date(2026, 1, 13),
    )
    target_task_2 = factories.create_task(
        project=project,
        user_story=target_userstory_2,
        due_date=date(2026, 1, 16),
    )

    source_schedule = schedule_services.upsert_schedule(
        schedule_services.ENTITY_TASK,
        source_task.id,
        project_id=project.id,
        estimated_start=date(2026, 1, 8),
        due_date=date(2026, 1, 10),
    )
    target_schedule_1 = schedule_services.upsert_schedule(
        schedule_services.ENTITY_TASK,
        target_task_1.id,
        project_id=project.id,
        estimated_start=date(2026, 1, 11),
        due_date=date(2026, 1, 13),
    )
    target_schedule_2 = schedule_services.upsert_schedule(
        schedule_services.ENTITY_TASK,
        target_task_2.id,
        project_id=project.id,
        estimated_start=date(2026, 1, 14),
        due_date=date(2026, 1, 16),
    )

    schedule_services.upsert_schedule(
        schedule_services.ENTITY_USERSTORY,
        target_userstory_1.id,
        project_id=project.id,
        estimated_start=date(2026, 1, 11),
        due_date=date(2026, 1, 13),
    )
    schedule_services.upsert_schedule(
        schedule_services.ENTITY_USERSTORY,
        target_userstory_2.id,
        project_id=project.id,
        estimated_start=date(2026, 1, 14),
        due_date=date(2026, 1, 16),
    )

    schedule_services.upsert_schedule(
        schedule_services.ENTITY_EPIC,
        epic_1.id,
        project_id=project.id,
        estimated_start=date(2026, 1, 11),
        due_date=date(2026, 1, 13),
    )
    schedule_services.upsert_schedule(
        schedule_services.ENTITY_EPIC,
        epic_2.id,
        project_id=project.id,
        estimated_start=date(2026, 1, 14),
        due_date=date(2026, 1, 16),
    )

    ScheduleDependency.objects.create(
        from_schedule=source_schedule,
        to_schedule=target_schedule_1,
    )
    ScheduleDependency.objects.create(
        from_schedule=target_schedule_1,
        to_schedule=target_schedule_2,
    )

    Schedule.objects.filter(id=source_schedule.id).update(due_date=date(2026, 1, 14))
    schedule_services.propagate_dependency_chain_forward_from_schedule(source_schedule.id)

    target_schedule_1.refresh_from_db()
    target_schedule_2.refresh_from_db()
    target_userstory_1.refresh_from_db()
    target_userstory_2.refresh_from_db()
    target_userstory_schedule_1 = schedule_services.get_schedule(
        schedule_services.ENTITY_USERSTORY,
        target_userstory_1.id,
    )
    target_userstory_schedule_2 = schedule_services.get_schedule(
        schedule_services.ENTITY_USERSTORY,
        target_userstory_2.id,
    )
    epic_schedule_1 = schedule_services.get_schedule(
        schedule_services.ENTITY_EPIC,
        epic_1.id,
    )
    epic_schedule_2 = schedule_services.get_schedule(
        schedule_services.ENTITY_EPIC,
        epic_2.id,
    )

    assert target_schedule_1.estimated_start == date(2026, 1, 15)
    assert target_schedule_1.due_date == date(2026, 1, 17)
    assert target_schedule_2.estimated_start == date(2026, 1, 18)
    assert target_schedule_2.due_date == date(2026, 1, 20)

    assert target_userstory_1.due_date == date(2026, 1, 17)
    assert target_userstory_2.due_date == date(2026, 1, 20)
    assert target_userstory_schedule_1.due_date == date(2026, 1, 17)
    assert target_userstory_schedule_2.due_date == date(2026, 1, 20)

    assert epic_schedule_1.due_date == date(2026, 1, 17)
    assert epic_schedule_2.due_date == date(2026, 1, 20)
