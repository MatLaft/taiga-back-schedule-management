# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos INC

from taiga.base.api.permissions import TaigaResourcePermission, IsAuthenticated


class ScheduleDependencyPermission(TaigaResourcePermission):
    retrieve_perms = IsAuthenticated()
    create_perms = IsAuthenticated()
    update_perms = IsAuthenticated()
    partial_update_perms = IsAuthenticated()
    destroy_perms = IsAuthenticated()
    list_perms = IsAuthenticated()
    bulk_apply_dates_perms = IsAuthenticated()


class ScheduleItemPermission(TaigaResourcePermission):
    list_perms = IsAuthenticated()
    update_item_perms = IsAuthenticated()
