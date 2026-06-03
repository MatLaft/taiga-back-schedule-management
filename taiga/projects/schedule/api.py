# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos INC

from django.utils.translation import gettext as _
from django_pglocks import advisory_lock

from taiga.base import exceptions as exc
from taiga.base import filters as base_filters
from taiga.base import response
from taiga.base.decorators import list_route
from taiga.base.api import ModelCrudViewSet, GenericViewSet
from taiga.permissions import services as permissions_service
from taiga.projects.models import Project
from taiga.projects.epics.models import Epic
from taiga.projects.userstories.models import UserStory
from taiga.projects.tasks.models import Task

from . import models
from . import permissions
from . import serializers
from . import services
from . import validators


_ENTITY_MODEL_MAP = {
    models.Schedule.TYPE_EPIC: Epic,
    models.Schedule.TYPE_USERSTORY: UserStory,
    models.Schedule.TYPE_TASK: Task,
}


class ScheduleDependencyViewSet(ModelCrudViewSet):
    serializer_class = serializers.ScheduleDependencySerializer
    validator_class = validators.ScheduleDependencyValidator
    permission_classes = (permissions.ScheduleDependencyPermission,)
    queryset = models.ScheduleDependency.objects.all()

    def _normalize_project_id(self, raw_project_id):
        if raw_project_id is None:
            return None

        try:
            return int(raw_project_id)
        except (TypeError, ValueError):
            raise exc.BadRequest(_("'project' must be an integer value."))

    def _user_can_view_project(self, project_id):
        filter_expression = base_filters.get_filter_expression_can_view_projects(
            self.request.user, project_id=project_id
        )
        return Project.objects.filter(id=project_id).filter(filter_expression).exists()

    def _user_can_view_schedule_pages(self, project):
        return (
            permissions_service.user_has_perm(self.request.user, "view_schedule", project)
            or permissions_service.user_has_perm(self.request.user, "view_gantt", project)
        )

    def _user_can_modify_dependencies(self, project):
        return permissions_service.user_has_perm(
            self.request.user, "modify_schedule_links", project
        )

    def _user_can_modify_schedule_dates(self, project):
        return permissions_service.user_has_perm(
            self.request.user, "modify_schedule_dates", project
        )

    def _check_project_access(self, project_id, for_write=False, for_dates_write=False):
        if project_id is None:
            raise exc.WrongArguments(_("Project is required."))

        project = Project.objects.filter(id=project_id).first()
        if project is None:
            raise exc.WrongArguments(_("The project doesn't exist."))

        if not self._user_can_view_project(project_id):
            raise exc.PermissionDenied(
                _("You don't have permissions to access this project.")
            )

        if not self._user_can_view_schedule_pages(project):
            raise exc.PermissionDenied(
                _("You don't have permissions to access schedule or gantt data.")
            )

        if for_write and not self._user_can_modify_dependencies(project):
            raise exc.PermissionDenied(
                _("You don't have permissions to modify schedule dependencies.")
            )

        if for_dates_write and not self._user_can_modify_schedule_dates(project):
            raise exc.PermissionDenied(
                _("You don't have permissions to modify schedule dates.")
            )

    def get_queryset(self):
        qs = super().get_queryset().select_related("from_schedule", "to_schedule")

        requested_project_id = self._normalize_project_id(
            self.request.QUERY_PARAMS.get("project")
        )
        if requested_project_id is not None:
            self._check_project_access(requested_project_id)

        project_filter_expression = base_filters.get_filter_expression_can_view_projects(
            self.request.user, project_id=requested_project_id
        )
        visible_projects = Project.objects.filter(project_filter_expression)
        if requested_project_id is not None:
            visible_projects = visible_projects.filter(id=requested_project_id)

        visible_project_ids = []
        for project in visible_projects:
            if self._user_can_view_schedule_pages(project):
                visible_project_ids.append(project.id)

        qs = qs.filter(
            from_schedule__project_id__in=visible_project_ids,
            to_schedule__project_id__in=visible_project_ids,
        )

        if requested_project_id is not None:
            qs = qs.filter(
                from_schedule__project_id=requested_project_id,
                to_schedule__project_id=requested_project_id,
            )

        return qs

    def pre_conditions_on_save(self, obj):
        super().pre_conditions_on_save(obj)

        if not obj.from_schedule_id or not obj.to_schedule_id:
            raise exc.WrongArguments(
                _("Both source and target schedules are required.")
            )

        if obj.from_schedule.project_id != obj.to_schedule.project_id:
            raise exc.WrongArguments(
                _("The source and target schedules must belong to the same project.")
            )

        self._check_project_access(obj.from_schedule.project_id, for_write=True)

    def pre_conditions_on_delete(self, obj):
        super().pre_conditions_on_delete(obj)

        project_id = obj.from_schedule.project_id if obj and obj.from_schedule_id else None
        self._check_project_access(project_id, for_write=True)

    @list_route(methods=["POST"])
    def bulk_apply_dates(self, request, **kwargs):
        validator = validators.ScheduleBulkApplyDatesValidator(data=request.DATA)
        if not validator.is_valid():
            return response.BadRequest(validator.errors)

        # Use deserialized values (e.g. DateField -> datetime.date) instead of
        # serialized representation to keep type-safe schedule validations.
        data = validator.object
        project_id = data["project_id"]
        self._check_project_access(project_id, for_dates_write=True)

        try:
            with advisory_lock("schedule-bulk-apply-dates-{}".format(project_id)):
                normalized_updates = services.apply_schedule_dates_in_bulk(
                    project_id,
                    data["bulk_updates"],
                )
        except ValueError as err:
            raise exc.WrongArguments(str(err))

        return response.Ok({"updated": len(normalized_updates)})


class ScheduleItemViewSet(GenericViewSet):
    permission_classes = (permissions.ScheduleItemPermission,)

    def _user_can_view_project(self, project_id):
        filter_expression = base_filters.get_filter_expression_can_view_projects(
            self.request.user, project_id=project_id
        )
        return Project.objects.filter(id=project_id).filter(filter_expression).exists()

    def _user_can_view_schedule_pages(self, project):
        return (
            permissions_service.user_has_perm(self.request.user, "view_schedule", project)
            or permissions_service.user_has_perm(self.request.user, "view_gantt", project)
        )

    def _resolve_entity(self, entity_type, entity_id, project_id):
        model = _ENTITY_MODEL_MAP[entity_type]
        try:
            entity = model.objects.get(id=entity_id, project_id=project_id)
        except model.DoesNotExist:
            raise exc.WrongArguments(
                _("Entity not found in the given project.")
            )
        return entity

    @list_route(methods=["POST"])
    def update_dates(self, request, **kwargs):
        validator = validators.ScheduleItemDatesValidator(data=request.DATA)
        if not validator.is_valid():
            return response.BadRequest(validator.errors)

        data = validator.object
        project_id = data["project"]
        entity_type = data["entity_type"]
        entity_id = data["entity_id"]

        project = Project.objects.filter(id=project_id).first()
        if project is None:
            raise exc.WrongArguments(_("The project doesn't exist."))

        if not self._user_can_view_project(project_id):
            raise exc.PermissionDenied(
                _("You don't have permissions to access this project.")
            )

        if not self._user_can_view_schedule_pages(project):
            raise exc.PermissionDenied(
                _("You don't have permissions to access schedule or gantt data.")
            )

        if not permissions_service.user_has_perm(
            self.request.user, "modify_schedule_dates", project
        ):
            raise exc.PermissionDenied(
                _("You don't have permissions to modify schedule dates.")
            )

        # Validates that the entity exists in the project. Avoids letting a
        # caller create an orphan Schedule row by upserting against a bogus id.
        entity = self._resolve_entity(entity_type, entity_id, project_id)

        upsert_kwargs = {"project_id": project_id}
        if "estimated_start" in data:
            upsert_kwargs["estimated_start"] = data["estimated_start"]
        if "actual_start" in data:
            upsert_kwargs["actual_start"] = data["actual_start"]

        schedule = services.upsert_schedule(entity_type, entity_id, **upsert_kwargs)
        services.propagate_dependency_chain_forward(entity_type, entity_id)

        if entity_type == models.Schedule.TYPE_TASK:
            services.ensure_userstory_and_epic_bounds_from_task(
                entity_id, getattr(entity, "user_story_id", None)
            )
        elif entity_type == models.Schedule.TYPE_USERSTORY:
            services.ensure_epic_bounds_for_userstory(entity_id)

        payload = {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "project": project_id,
            "estimated_start": schedule.estimated_start if schedule else None,
            "actual_start": schedule.actual_start if schedule else None,
            "due_date": schedule.due_date if schedule else None,
        }
        return response.Ok(payload)
