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
from taiga.base.api import ModelCrudViewSet
from taiga.permissions import services as permissions_service
from taiga.projects.models import Project

from . import models
from . import permissions
from . import serializers
from . import services
from . import validators


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
