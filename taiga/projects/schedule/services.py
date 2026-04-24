# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos INC

from collections import deque
from datetime import timedelta

from django.apps import apps
from django.db import OperationalError
from django.db import ProgrammingError
from django.db import transaction
from django.utils.translation import gettext as _

from .models import Schedule
from .models import ScheduleItemOrder


ENTITY_EPIC = Schedule.TYPE_EPIC
ENTITY_USERSTORY = Schedule.TYPE_USERSTORY
ENTITY_TASK = Schedule.TYPE_TASK

_UNSET = object()
_ALLOWED_ENTITIES = {ENTITY_EPIC, ENTITY_USERSTORY, ENTITY_TASK}
_ROOT_PARENT_ENTITY_TYPE = ScheduleItemOrder.ROOT_PARENT_ENTITY_TYPE
_ROOT_PARENT_ENTITY_ID = ScheduleItemOrder.ROOT_PARENT_ENTITY_ID


def _assert_entity_type(entity_type):
    if entity_type not in _ALLOWED_ENTITIES:
        raise ValueError("Unsupported entity_type: {}".format(entity_type))


def _build_order_group_key(project_id, entity_type, parent_entity_type, parent_entity_id):
    return (
        int(project_id or 0),
        entity_type or _ROOT_PARENT_ENTITY_TYPE,
        parent_entity_type or _ROOT_PARENT_ENTITY_TYPE,
        int(parent_entity_id or _ROOT_PARENT_ENTITY_ID),
    )


def _build_order_group_filters(group_key):
    project_id, entity_type, parent_entity_type, parent_entity_id = group_key
    return {
        "project_id": project_id,
        "entity_type": entity_type,
        "parent_entity_type": parent_entity_type,
        "parent_entity_id": parent_entity_id,
    }


def _resolve_order_parent(entity_type, entity_id):
    if entity_type == ENTITY_EPIC:
        return _ROOT_PARENT_ENTITY_TYPE, _ROOT_PARENT_ENTITY_ID

    if entity_type == ENTITY_USERSTORY:
        relation = _get_primary_epic_relation(entity_id)
        epic_id = getattr(relation, "epic_id", None) if relation else None
        if epic_id:
            return ENTITY_EPIC, int(epic_id)
        return _ROOT_PARENT_ENTITY_TYPE, _ROOT_PARENT_ENTITY_ID

    if entity_type == ENTITY_TASK:
        try:
            task_model = apps.get_model("tasks", "Task")
            user_story_id = (
                task_model.objects
                .filter(id=entity_id)
                .values_list("user_story_id", flat=True)
                .first()
            )
        except (ProgrammingError, OperationalError):
            user_story_id = None

        if user_story_id:
            return ENTITY_USERSTORY, int(user_story_id)
        return _ROOT_PARENT_ENTITY_TYPE, _ROOT_PARENT_ENTITY_ID

    return _ROOT_PARENT_ENTITY_TYPE, _ROOT_PARENT_ENTITY_ID


def _fetch_group_items_for_update(group_key):
    filters = _build_order_group_filters(group_key)
    return list(
        ScheduleItemOrder.objects
        .select_for_update()
        .filter(**filters)
        .order_by("position", "id")
    )


def _persist_group_positions(items):
    for index, item in enumerate(items, start=1):
        if item.position == index:
            continue

        ScheduleItemOrder.objects.filter(id=item.id).update(position=index)
        item.position = index


def _move_order_item_between_groups(item_order, target_group_key, target_position=None):
    current_group_key = _build_order_group_key(
        item_order.project_id,
        item_order.entity_type,
        item_order.parent_entity_type,
        item_order.parent_entity_id,
    )

    if current_group_key == target_group_key:
        group_items = _fetch_group_items_for_update(current_group_key)
        ordered_items = [item for item in group_items if item.id != item_order.id]
        max_position = len(ordered_items) + 1
        if target_position is None:
            desired_position = item_order.position
        else:
            desired_position = int(target_position)
        desired_position = max(1, min(desired_position, max_position))
        ordered_items.insert(desired_position - 1, item_order)
        _persist_group_positions(ordered_items)
        return item_order

    group_keys = sorted(set([current_group_key, target_group_key]))
    locked_groups = {key: _fetch_group_items_for_update(key) for key in group_keys}

    current_group_items = locked_groups.get(current_group_key, [])
    remaining_current_items = [item for item in current_group_items if item.id != item_order.id]
    _persist_group_positions(remaining_current_items)

    target_group_items = locked_groups.get(target_group_key, [])
    max_target_position = len(target_group_items) + 1
    desired_position = max_target_position if target_position is None else int(target_position)
    desired_position = max(1, min(desired_position, max_target_position))

    (
        next_project_id,
        next_entity_type,
        next_parent_entity_type,
        next_parent_entity_id,
    ) = target_group_key
    ScheduleItemOrder.objects.filter(id=item_order.id).update(
        project_id=next_project_id,
        entity_type=next_entity_type,
        parent_entity_type=next_parent_entity_type,
        parent_entity_id=next_parent_entity_id,
        position=max_target_position,
    )
    item_order.project_id = next_project_id
    item_order.entity_type = next_entity_type
    item_order.parent_entity_type = next_parent_entity_type
    item_order.parent_entity_id = next_parent_entity_id
    item_order.position = max_target_position

    reordered_target_items = [item for item in target_group_items if item.id != item_order.id]
    reordered_target_items.insert(desired_position - 1, item_order)
    _persist_group_positions(reordered_target_items)

    return item_order


def _sync_schedule_item_order_for_schedule(schedule):
    parent_entity_type, parent_entity_id = _resolve_order_parent(
        schedule.entity_type, schedule.entity_id
    )
    target_group_key = _build_order_group_key(
        schedule.project_id,
        schedule.entity_type,
        parent_entity_type,
        parent_entity_id,
    )

    item_order = (
        ScheduleItemOrder.objects
        .select_for_update()
        .filter(schedule_id=schedule.id)
        .first()
    )

    if item_order is None:
        group_items = _fetch_group_items_for_update(target_group_key)
        item_order = ScheduleItemOrder.objects.create(
            schedule=schedule,
            project_id=target_group_key[0],
            entity_type=target_group_key[1],
            parent_entity_type=target_group_key[2],
            parent_entity_id=target_group_key[3],
            position=(len(group_items) + 1),
        )
        return item_order

    return _move_order_item_between_groups(item_order, target_group_key)


def sync_schedule_item_order(entity_type, entity_id):
    _assert_entity_type(entity_type)
    schedule = get_schedule(entity_type, entity_id)
    if schedule is None:
        return None

    try:
        with transaction.atomic():
            return _sync_schedule_item_order_for_schedule(schedule)
    except (ProgrammingError, OperationalError):
        return None


def get_schedule_item_order(entity_type, entity_id):
    _assert_entity_type(entity_type)
    schedule = get_schedule(entity_type, entity_id)
    if schedule is None:
        return None

    try:
        return ScheduleItemOrder.objects.filter(schedule_id=schedule.id).first()
    except (ProgrammingError, OperationalError):
        return None


def set_schedule_item_order_position(entity_type, entity_id, position):
    _assert_entity_type(entity_type)

    try:
        desired_position = int(position)
    except (TypeError, ValueError):
        raise ValueError("position must be an integer value")

    desired_position = max(1, desired_position)

    schedule = get_schedule(entity_type, entity_id)
    if schedule is None:
        return None

    try:
        with transaction.atomic():
            item_order = _sync_schedule_item_order_for_schedule(schedule)
            current_group_key = _build_order_group_key(
                item_order.project_id,
                item_order.entity_type,
                item_order.parent_entity_type,
                item_order.parent_entity_id,
            )
            return _move_order_item_between_groups(
                item_order,
                current_group_key,
                target_position=desired_position,
            )
    except (ProgrammingError, OperationalError):
        return None


def get_schedule(entity_type, entity_id):
    _assert_entity_type(entity_type)
    try:
        return Schedule.objects.filter(entity_type=entity_type, entity_id=entity_id).first()
    except (ProgrammingError, OperationalError):
        return None


def delete_schedule(entity_type, entity_id):
    _assert_entity_type(entity_type)
    try:
        with transaction.atomic():
            schedule = (
                Schedule.objects
                .select_for_update()
                .filter(entity_type=entity_type, entity_id=entity_id)
                .first()
            )
            if schedule is None:
                return

            item_order = (
                ScheduleItemOrder.objects
                .select_for_update()
                .filter(schedule_id=schedule.id)
                .first()
            )
            if item_order is not None:
                group_key = _build_order_group_key(
                    item_order.project_id,
                    item_order.entity_type,
                    item_order.parent_entity_type,
                    item_order.parent_entity_id,
                )
                group_items = _fetch_group_items_for_update(group_key)
                item_order.delete()
                remaining_items = [item for item in group_items if item.id != item_order.id]
                _persist_group_positions(remaining_items)

            Schedule.objects.filter(id=schedule.id).delete()
    except (ProgrammingError, OperationalError):
        return


def upsert_schedule(
    entity_type,
    entity_id,
    *,
    project_id,
    created_date=_UNSET,
    due_date=_UNSET,
    estimated_start=_UNSET,
    actual_start=_UNSET,
    estimated_hours=_UNSET,
    actual_hours=_UNSET,
    color=_UNSET,
):
    _assert_entity_type(entity_type)
    try:
        obj, _ = Schedule.objects.get_or_create(
            entity_type=entity_type,
            entity_id=entity_id,
            defaults={"project_id": project_id},
        )
    except (ProgrammingError, OperationalError):
        return None

    updates = {}
    if obj.project_id != project_id:
        updates["project_id"] = project_id
    if created_date is not _UNSET:
        updates["created_date"] = created_date
    if due_date is not _UNSET:
        updates["due_date"] = due_date
    if estimated_start is not _UNSET:
        updates["estimated_start"] = estimated_start
    if actual_start is not _UNSET:
        updates["actual_start"] = actual_start
    if estimated_hours is not _UNSET:
        updates["estimated_hours"] = estimated_hours
    if actual_hours is not _UNSET:
        updates["actual_hours"] = actual_hours
    if color is not _UNSET:
        updates["color"] = color

    if updates:
        try:
            Schedule.objects.filter(id=obj.id).update(**updates)
        except (ProgrammingError, OperationalError):
            return obj
        for key, value in updates.items():
            setattr(obj, key, value)

    sync_schedule_item_order(entity_type, entity_id)

    return obj


def attach_schedule_fields(queryset, entity_type, field_names):
    _assert_entity_type(entity_type)
    model = queryset.model
    model_table = model._meta.db_table
    schedule_table = Schedule._meta.db_table

    select = {}
    for field_name in field_names:
        select_key = "schedule_{}".format(field_name)
        sql = (
            'SELECT "{schedule_table}"."{field_name}" '
            'FROM "{schedule_table}" '
            "WHERE "
            '"{schedule_table}"."entity_type" = \'{entity_type}\' '
            "AND "
            '"{schedule_table}"."entity_id" = "{model_table}"."id" '
            "LIMIT 1"
        ).format(
            schedule_table=schedule_table,
            field_name=field_name,
            entity_type=entity_type,
            model_table=model_table,
        )
        select[select_key] = sql

    if select:
        queryset = queryset.extra(select=select)

    return queryset


def get_schedule_field(obj, entity_type, field_name):
    attr_name = "schedule_{}".format(field_name)
    if hasattr(obj, attr_name):
        return getattr(obj, attr_name)

    schedule = get_schedule(entity_type, obj.id)
    if schedule is None:
        return None

    return getattr(schedule, field_name)


def get_due_date(entity_type, entity_id):
    _assert_entity_type(entity_type)

    if entity_type == ENTITY_EPIC:
        schedule = get_schedule(ENTITY_EPIC, entity_id)
        return schedule.due_date if schedule else None

    if entity_type == ENTITY_USERSTORY:
        model = apps.get_model("userstories", "UserStory")
        return model.objects.filter(id=entity_id).values_list("due_date", flat=True).first()

    model = apps.get_model("tasks", "Task")
    return model.objects.filter(id=entity_id).values_list("due_date", flat=True).first()


def _get_primary_epic_relation(userstory_id):
    if not userstory_id:
        return None

    try:
        related_model = apps.get_model("epics", "RelatedUserStory")
        return (
            related_model.objects
            .filter(user_story_id=userstory_id)
            .select_related("epic")
            .order_by("order", "id")
            .first()
        )
    except (ProgrammingError, OperationalError):
        return None


def _get_effective_start(schedule):
    if schedule is None:
        return None

    if schedule.actual_start is not None:
        return schedule.actual_start

    return schedule.estimated_start


def _get_due_from_schedule_or_fallback(schedule, fallback_due):
    if schedule is not None and schedule.due_date is not None:
        return schedule.due_date

    return fallback_due


def _get_schedule_map(entity_type, entity_ids):
    if not entity_ids:
        return {}

    try:
        schedules = Schedule.objects.filter(entity_type=entity_type, entity_id__in=entity_ids)
    except (ProgrammingError, OperationalError):
        return {}

    return {schedule.entity_id: schedule for schedule in schedules}


def _resolve_effective_start(actual_start, estimated_start):
    if actual_start is not None:
        return actual_start

    return estimated_start


def _get_proposed_bounds_for_entity(obj, entity_type):
    entity_id = getattr(obj, "id", None)
    schedule = get_schedule(entity_type, entity_id) if entity_id else None

    if hasattr(obj, "actual_start"):
        actual_start = getattr(obj, "actual_start")
    else:
        actual_start = schedule.actual_start if schedule is not None else None

    if hasattr(obj, "estimated_start"):
        estimated_start = getattr(obj, "estimated_start")
    else:
        estimated_start = schedule.estimated_start if schedule is not None else None

    if entity_type == ENTITY_EPIC:
        if hasattr(obj, "due_date"):
            due_date = getattr(obj, "due_date")
        else:
            due_date = schedule.due_date if schedule is not None else None
    else:
        due_date = getattr(obj, "due_date", None)

    return _resolve_effective_start(actual_start, estimated_start), due_date


def _get_task_children_bounds(userstory_id):
    if not userstory_id:
        return None, None

    try:
        task_model = apps.get_model("tasks", "Task")
        tasks = list(task_model.objects.filter(user_story_id=userstory_id).only("id", "due_date"))
    except (ProgrammingError, OperationalError):
        return None, None

    if not tasks:
        return None, None

    schedule_map = _get_schedule_map(ENTITY_TASK, [task.id for task in tasks])

    min_start = None
    max_due = None
    for task in tasks:
        schedule = schedule_map.get(task.id)
        start = _get_effective_start(schedule)
        due = _get_due_from_schedule_or_fallback(schedule, task.due_date)

        if start is not None and (min_start is None or start < min_start):
            min_start = start

        if due is not None and (max_due is None or due > max_due):
            max_due = due

    return min_start, max_due


def _get_userstory_children_bounds(epic_id):
    if not epic_id:
        return None, None

    try:
        related_model = apps.get_model("epics", "RelatedUserStory")
        userstory_ids = list(
            related_model.objects
            .filter(epic_id=epic_id)
            .values_list("user_story_id", flat=True)
            .distinct()
        )
    except (ProgrammingError, OperationalError):
        return None, None

    if not userstory_ids:
        return None, None

    try:
        userstory_model = apps.get_model("userstories", "UserStory")
        userstories = list(userstory_model.objects.filter(id__in=userstory_ids).only("id", "due_date"))
    except (ProgrammingError, OperationalError):
        return None, None

    schedule_map = _get_schedule_map(ENTITY_USERSTORY, userstory_ids)

    min_start = None
    max_due = None
    for userstory in userstories:
        schedule = schedule_map.get(userstory.id)
        start = _get_effective_start(schedule)
        due = _get_due_from_schedule_or_fallback(schedule, userstory.due_date)

        if start is not None and (min_start is None or start < min_start):
            min_start = start

        if due is not None and (max_due is None or due > max_due):
            max_due = due

    return min_start, max_due


def get_userstory_bounds_violation_error(userstory):
    if userstory is None or not getattr(userstory, "id", None):
        return None

    parent_start, parent_due = _get_proposed_bounds_for_entity(userstory, ENTITY_USERSTORY)
    min_child_start, max_child_due = _get_task_children_bounds(userstory.id)

    if parent_due is not None and max_child_due is not None and max_child_due > parent_due:
        return _(
            "It is not possible to set a date earlier than an internal item date."
        )

    if parent_start is not None and min_child_start is not None and min_child_start < parent_start:
        return _(
            "Cannot set user story start date later than one of its task start dates."
        )

    return None


def get_epic_bounds_violation_error(epic):
    if epic is None or not getattr(epic, "id", None):
        return None

    parent_start, parent_due = _get_proposed_bounds_for_entity(epic, ENTITY_EPIC)
    min_child_start, max_child_due = _get_userstory_children_bounds(epic.id)

    if parent_due is not None and max_child_due is not None and max_child_due > parent_due:
        return _(
            "It is not possible to set a date earlier than an internal item date."
        )

    if parent_start is not None and min_child_start is not None and min_child_start < parent_start:
        return _(
            "Cannot set epic start date later than one of its user story start dates."
        )

    return None


def get_dependency_start_violation_error(obj, entity_type):
    if obj is None or not getattr(obj, "id", None):
        return None

    schedule = get_schedule(entity_type, obj.id)
    if schedule is None:
        return None

    proposed_start, _ = _get_proposed_bounds_for_entity(obj, entity_type)

    try:
        dependency_model = apps.get_model("schedule", "ScheduleDependency")
        incoming_dependencies = (
            dependency_model.objects
            .filter(to_schedule_id=schedule.id)
            .select_related("from_schedule")
        )
    except (ProgrammingError, OperationalError):
        return None

    if not incoming_dependencies.exists():
        return None

    if proposed_start is None:
        return _("The target schedule must have a start date.")

    for dependency in incoming_dependencies:
        source_due_date = dependency.from_schedule.due_date if dependency.from_schedule_id else None
        if source_due_date is None:
            continue

        if proposed_start <= source_due_date:
            return _(
                "The target schedule must start after the source schedule due date."
            )

    return None


def _expand_parent_start(current_parent_start, child_start):
    if child_start is None:
        return current_parent_start

    if current_parent_start is None or child_start < current_parent_start:
        return child_start

    return current_parent_start


def _get_dependency_violation_for_candidate_start(schedule, candidate_start):
    if schedule is None or candidate_start is None:
        return None

    required_start = _get_required_start_from_incoming_dependencies(schedule.id)
    if required_start is None:
        return None

    if candidate_start < required_start:
        return _(
            "The target schedule must start after the source schedule due date."
        )

    return None


def _get_task_parent_userstory_id(task_obj):
    userstory_id = getattr(task_obj, "user_story_id", None)
    if userstory_id:
        return userstory_id

    userstory = getattr(task_obj, "user_story", None)
    if userstory is None:
        return None

    return getattr(userstory, "id", None)


def _get_epic_dependency_violation_for_userstory_candidate_start(userstory_id, userstory_candidate_start):
    if not userstory_id or userstory_candidate_start is None:
        return None

    relation = _get_primary_epic_relation(userstory_id)
    if relation is None or relation.epic_id is None:
        return None

    epic_schedule = get_schedule(ENTITY_EPIC, relation.epic_id)
    epic_current_start = _get_effective_start(epic_schedule)
    epic_candidate_start = _expand_parent_start(epic_current_start, userstory_candidate_start)

    return _get_dependency_violation_for_candidate_start(epic_schedule, epic_candidate_start)


def get_ancestor_dependency_start_violation_error(obj, entity_type):
    if obj is None or not getattr(obj, "id", None):
        return None

    proposed_start, _ = _get_proposed_bounds_for_entity(obj, entity_type)
    if proposed_start is None:
        return None

    if entity_type == ENTITY_TASK:
        userstory_id = _get_task_parent_userstory_id(obj)
        if not userstory_id:
            return None

        userstory_schedule = get_schedule(ENTITY_USERSTORY, userstory_id)
        userstory_current_start = _get_effective_start(userstory_schedule)
        userstory_candidate_start = _expand_parent_start(userstory_current_start, proposed_start)

        userstory_violation = _get_dependency_violation_for_candidate_start(
            userstory_schedule,
            userstory_candidate_start,
        )
        if userstory_violation:
            return userstory_violation

        return _get_epic_dependency_violation_for_userstory_candidate_start(
            userstory_id,
            userstory_candidate_start,
        )

    if entity_type == ENTITY_USERSTORY:
        return _get_epic_dependency_violation_for_userstory_candidate_start(
            obj.id,
            proposed_start,
        )

    return None


def _get_model_for_entity_type(entity_type):
    if entity_type == ENTITY_EPIC:
        return apps.get_model("epics", "Epic")
    if entity_type == ENTITY_USERSTORY:
        return apps.get_model("userstories", "UserStory")
    if entity_type == ENTITY_TASK:
        return apps.get_model("tasks", "Task")
    return None


def _update_entity_due_date_for_schedule(schedule, due_date):
    if schedule is None or not schedule.entity_id:
        return

    try:
        model = _get_model_for_entity_type(schedule.entity_type)
    except (ProgrammingError, OperationalError):
        return

    if model is None:
        return

    try:
        model.objects.filter(id=schedule.entity_id).update(due_date=due_date)
    except (ProgrammingError, OperationalError):
        return


def _get_required_start_from_incoming_dependencies(schedule_id):
    if not schedule_id:
        return None

    try:
        dependency_model = apps.get_model("schedule", "ScheduleDependency")
        incoming_dependencies = (
            dependency_model.objects
            .filter(to_schedule_id=schedule_id)
            .select_related("from_schedule")
        )
    except (ProgrammingError, OperationalError):
        return None

    required_start = None
    for dependency in incoming_dependencies:
        source_due_date = dependency.from_schedule.due_date if dependency.from_schedule_id else None
        if source_due_date is None:
            continue

        candidate = source_due_date + timedelta(days=1)
        if required_start is None or candidate > required_start:
            required_start = candidate

    return required_start


def _shift_schedule_forward_to_start(schedule, required_start):
    if schedule is None or required_start is None:
        return False, False

    current_start = _get_effective_start(schedule)
    if current_start is not None and current_start >= required_start:
        return False, False

    updates = {}
    if schedule.actual_start is not None:
        updates["actual_start"] = required_start
    else:
        updates["estimated_start"] = required_start

    current_due = schedule.due_date
    if current_due is not None:
        if current_start is not None:
            duration_days = (current_due - current_start).days
            duration_days = max(duration_days, 0)
            next_due = required_start + timedelta(days=duration_days)
        else:
            next_due = max(current_due, required_start)

        if next_due != current_due:
            updates["due_date"] = next_due

    if not updates:
        return False, False

    try:
        Schedule.objects.filter(id=schedule.id).update(**updates)
    except (ProgrammingError, OperationalError):
        return False, False

    for key, value in updates.items():
        setattr(schedule, key, value)

    if "due_date" in updates:
        _update_entity_due_date_for_schedule(schedule, updates["due_date"])

    return True, "due_date" in updates


def propagate_dependency_chain_forward_from_schedule(schedule_id):
    if not schedule_id:
        return

    try:
        dependency_model = apps.get_model("schedule", "ScheduleDependency")
    except (ProgrammingError, OperationalError):
        return

    queue = deque([schedule_id])
    queued = {schedule_id}
    max_iterations = 10000
    iterations = 0

    while queue and iterations < max_iterations:
        iterations += 1
        current_schedule_id = queue.popleft()
        queued.discard(current_schedule_id)

        try:
            outgoing_target_ids = list(
                dependency_model.objects
                .filter(from_schedule_id=current_schedule_id)
                .values_list("to_schedule_id", flat=True)
            )
        except (ProgrammingError, OperationalError):
            return

        for target_schedule_id in outgoing_target_ids:
            try:
                target_schedule = (
                    Schedule.objects
                    .filter(id=target_schedule_id)
                    .only(
                        "id",
                        "entity_type",
                        "entity_id",
                        "estimated_start",
                        "actual_start",
                        "due_date",
                    )
                    .first()
                )
            except (ProgrammingError, OperationalError):
                return

            if target_schedule is None:
                continue

            required_start = _get_required_start_from_incoming_dependencies(target_schedule.id)
            if required_start is None:
                continue

            shifted, due_changed = _shift_schedule_forward_to_start(target_schedule, required_start)
            if shifted and due_changed and target_schedule.id not in queued:
                queue.append(target_schedule.id)
                queued.add(target_schedule.id)


def propagate_dependency_chain_forward(entity_type, entity_id):
    schedule = get_schedule(entity_type, entity_id)
    if schedule is None:
        return

    propagate_dependency_chain_forward_from_schedule(schedule.id)


def _build_expand_bounds_updates(schedule, fallback_due, candidate_start, candidate_due):
    updates = {}

    if candidate_start is not None:
        if schedule is not None and schedule.actual_start is not None:
            if candidate_start < schedule.actual_start:
                updates["actual_start"] = candidate_start
        elif schedule is not None and schedule.estimated_start is not None:
            if candidate_start < schedule.estimated_start:
                updates["estimated_start"] = candidate_start
        else:
            updates["estimated_start"] = candidate_start

    current_due = _get_due_from_schedule_or_fallback(schedule, fallback_due)
    if candidate_due is not None and (current_due is None or candidate_due > current_due):
        updates["due_date"] = candidate_due

    return updates


def _expand_userstory_bounds(userstory, candidate_start, candidate_due):
    schedule = get_schedule(ENTITY_USERSTORY, userstory.id)
    updates = _build_expand_bounds_updates(
        schedule,
        userstory.due_date,
        candidate_start,
        candidate_due,
    )
    if not updates:
        return updates

    upsert_schedule(
        ENTITY_USERSTORY,
        userstory.id,
        project_id=userstory.project_id,
        **updates
    )

    if "due_date" in updates:
        try:
            userstory_model = apps.get_model("userstories", "UserStory")
            userstory_model.objects.filter(id=userstory.id).update(due_date=updates["due_date"])
        except (ProgrammingError, OperationalError):
            return updates
        userstory.due_date = updates["due_date"]

    propagate_dependency_chain_forward(ENTITY_USERSTORY, userstory.id)

    return updates


def ensure_userstory_and_epic_bounds_from_task(task_id, userstory_id=None):
    if not task_id:
        return

    try:
        task_model = apps.get_model("tasks", "Task")
        filters = {"id": task_id}
        if userstory_id is not None:
            filters["user_story_id"] = userstory_id
        task = (
            task_model.objects
            .filter(**filters)
            .only("id", "project_id", "user_story_id", "due_date")
            .first()
        )
    except (ProgrammingError, OperationalError):
        return

    if task is None or not task.user_story_id:
        return

    task_schedule = get_schedule(ENTITY_TASK, task.id)
    task_start = _get_effective_start(task_schedule)
    task_due = _get_due_from_schedule_or_fallback(task_schedule, task.due_date)

    try:
        userstory_model = apps.get_model("userstories", "UserStory")
        userstory = (
            userstory_model.objects
            .filter(id=task.user_story_id)
            .only("id", "project_id", "due_date")
            .first()
        )
    except (ProgrammingError, OperationalError):
        return

    if userstory is None:
        return

    _expand_userstory_bounds(userstory, task_start, task_due)
    ensure_epic_bounds_for_userstory(userstory.id)


def ensure_epic_bounds_for_userstory(userstory_id):
    if not userstory_id:
        return

    try:
        userstory_model = apps.get_model("userstories", "UserStory")
        userstory = (
            userstory_model.objects
            .filter(id=userstory_id)
            .only("id", "project_id", "due_date")
            .first()
        )
    except (ProgrammingError, OperationalError):
        return

    if userstory is None:
        return

    relation = _get_primary_epic_relation(userstory.id)
    if relation is None or relation.epic_id is None:
        return

    epic = relation.epic
    if epic is None:
        try:
            epic_model = apps.get_model("epics", "Epic")
            epic = epic_model.objects.filter(id=relation.epic_id).only("id", "project_id").first()
        except (ProgrammingError, OperationalError):
            return

    if epic is None:
        return

    userstory_schedule = get_schedule(ENTITY_USERSTORY, userstory.id)
    userstory_start = _get_effective_start(userstory_schedule)
    userstory_due = _get_due_from_schedule_or_fallback(userstory_schedule, userstory.due_date)

    epic_schedule = get_schedule(ENTITY_EPIC, epic.id)
    updates = _build_expand_bounds_updates(
        epic_schedule,
        getattr(epic, "due_date", None),
        userstory_start,
        userstory_due,
    )

    if not updates:
        return

    upsert_schedule(
        ENTITY_EPIC,
        epic.id,
        project_id=epic.project_id,
        **updates
    )

    propagate_dependency_chain_forward(ENTITY_EPIC, epic.id)


def get_primary_epic_color_for_userstory(userstory_id):
    relation = _get_primary_epic_relation(userstory_id)
    if relation is None or relation.epic is None:
        return None

    return relation.epic.color


def sync_userstory_and_tasks_schedule_color(userstory_id):
    if not userstory_id:
        return

    try:
        userstory_model = apps.get_model("userstories", "UserStory")
        task_model = apps.get_model("tasks", "Task")
        userstory = userstory_model.objects.filter(id=userstory_id).first()
    except (ProgrammingError, OperationalError):
        return

    if userstory is None:
        return

    color = get_primary_epic_color_for_userstory(userstory_id)

    upsert_schedule(
        ENTITY_USERSTORY,
        userstory.id,
        project_id=userstory.project_id,
        color=color,
    )

    try:
        tasks = task_model.objects.filter(user_story_id=userstory.id).only("id", "project_id")
    except (ProgrammingError, OperationalError):
        return

    for task in tasks:
        upsert_schedule(
            ENTITY_TASK,
            task.id,
            project_id=task.project_id,
            color=color,
        )


def sync_epic_related_schedule_colors(epic_id):
    if not epic_id:
        return

    try:
        related_model = apps.get_model("epics", "RelatedUserStory")
        userstory_ids = (
            related_model.objects
            .filter(epic_id=epic_id)
            .values_list("user_story_id", flat=True)
            .distinct()
        )
    except (ProgrammingError, OperationalError):
        return

    for userstory_id in userstory_ids:
        sync_userstory_and_tasks_schedule_color(userstory_id)
