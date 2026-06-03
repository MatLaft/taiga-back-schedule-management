# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos INC

from taiga.base.api import validators
from taiga.base.api import serializers
from taiga.base.exceptions import ValidationError

from . import models


class ScheduleDependencyValidator(validators.ModelValidator):
    class Meta:
        model = models.ScheduleDependency
        read_only_fields = ("id",)


class _ScheduleBulkDateUpdateValidator(validators.Validator):
    entity_type = serializers.ChoiceField(
        choices=(
            (models.Schedule.TYPE_EPIC, models.Schedule.TYPE_EPIC),
            (models.Schedule.TYPE_USERSTORY, models.Schedule.TYPE_USERSTORY),
            (models.Schedule.TYPE_TASK, models.Schedule.TYPE_TASK),
        )
    )
    entity_id = serializers.IntegerField(min_value=1)
    start_field = serializers.ChoiceField(
        required=False,
        choices=(("estimated_start", "estimated_start"), ("actual_start", "actual_start")),
    )
    start = serializers.DateField(required=False)
    due = serializers.DateField(required=False)


class ScheduleBulkApplyDatesValidator(validators.Validator):
    project_id = serializers.IntegerField(min_value=1)
    bulk_updates = _ScheduleBulkDateUpdateValidator(many=True)

    def validate_bulk_updates(self, attrs, source):
        bulk_updates = attrs.get(source) or []
        if not bulk_updates:
            raise ValidationError("At least one bulk update is required.")

        return attrs


class ScheduleItemDatesValidator(validators.Validator):
    project = serializers.IntegerField(min_value=1)
    entity_type = serializers.ChoiceField(
        choices=(
            (models.Schedule.TYPE_EPIC, models.Schedule.TYPE_EPIC),
            (models.Schedule.TYPE_USERSTORY, models.Schedule.TYPE_USERSTORY),
            (models.Schedule.TYPE_TASK, models.Schedule.TYPE_TASK),
        )
    )
    entity_id = serializers.IntegerField(min_value=1)
    estimated_start = serializers.DateField(required=False)
    actual_start = serializers.DateField(required=False)

    def validate(self, attrs):
        if "estimated_start" not in attrs and "actual_start" not in attrs:
            raise ValidationError(
                "At least one of 'estimated_start' or 'actual_start' is required."
            )
        return attrs
