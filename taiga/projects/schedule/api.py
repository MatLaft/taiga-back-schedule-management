# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos INC

from django.utils.translation import gettext as _

from taiga.base import exceptions as exc
from taiga.base import filters as base_filters
from taiga.base.api import ModelCrudViewSet
from taiga.permissions import services as permissions_service
from taiga.projects.models import Project

from . import models
from . import permissions
from . import serializers
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

    def _user_can_modify_dependencies(self, project):
        return (
            permissions_service.user_has_perm(self.request.user, "modify_epic", project)
            or permissions_service.user_has_perm(self.request.user, "modify_us", project)
            or permissions_service.user_has_perm(self.request.user, "modify_task", project)
        )

    def _check_project_access(self, project_id, for_write=False):
        if project_id is None:
            raise exc.WrongArguments(_("Project is required."))

        project = Project.objects.filter(id=project_id).first()
        if project is None:
            raise exc.WrongArguments(_("The project doesn't exist."))

        if not self._user_can_view_project(project_id):
            raise exc.PermissionDenied(
                _("You don't have permissions to access this project.")
            )

        if for_write and not self._user_can_modify_dependencies(project):
            raise exc.PermissionDenied(
                _("You don't have permissions to modify schedule dependencies.")
            )

    def get_queryset(self):
        qs = super().get_queryset().select_related("from_schedule", "to_schedule")

        requested_project_id = self._normalize_project_id(
            self.request.QUERY_PARAMS.get("project")
        )
        project_filter_expression = base_filters.get_filter_expression_can_view_projects(
            self.request.user, project_id=requested_project_id
        )
        visible_project_ids = Project.objects.filter(project_filter_expression).values_list(
            "id", flat=True
        )

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
