# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos INC

from taiga.base.api import serializers
from taiga.base.fields import Field, MethodField


class ScheduleDependencySerializer(serializers.LightSerializer):
    id = Field()
    from_schedule = Field(attr="from_schedule_id")
    to_schedule = Field(attr="to_schedule_id")
    from_entity_type = MethodField()
    from_entity_id = MethodField()
    to_entity_type = MethodField()
    to_entity_id = MethodField()
    project = MethodField()

    def get_from_entity_type(self, obj):
        return obj.from_schedule.entity_type if obj.from_schedule_id else None

    def get_from_entity_id(self, obj):
        return obj.from_schedule.entity_id if obj.from_schedule_id else None

    def get_to_entity_type(self, obj):
        return obj.to_schedule.entity_type if obj.to_schedule_id else None

    def get_to_entity_id(self, obj):
        return obj.to_schedule.entity_id if obj.to_schedule_id else None

    def get_project(self, obj):
        if obj.from_schedule_id:
            return obj.from_schedule.project_id
        return None
