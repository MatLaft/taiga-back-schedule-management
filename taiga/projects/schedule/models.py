# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos INC

from django.db import models
from django.utils.translation import gettext_lazy as _


class Schedule(models.Model):
    TYPE_EPIC = "epic"
    TYPE_USERSTORY = "userstory"
    TYPE_TASK = "task"

    ENTITY_TYPE_CHOICES = (
        (TYPE_EPIC, "Epic"),
        (TYPE_USERSTORY, "User Story"),
        (TYPE_TASK, "Task"),
    )

    entity_type = models.CharField(
        max_length=16, choices=ENTITY_TYPE_CHOICES, db_index=True
    )
    entity_id = models.BigIntegerField(db_index=True)
    project_id = models.BigIntegerField(db_index=True)
    created_date = models.DateTimeField(
        null=True, blank=True, default=None, verbose_name=_("created date")
    )
    due_date = models.DateField(
        null=True, blank=True, default=None, verbose_name=_("due date")
    )
    estimated_start = models.DateField(
        null=True, blank=True, default=None, verbose_name=_("estimated start date")
    )
    actual_start = models.DateField(
        null=True, blank=True, default=None, verbose_name=_("actual start date")
    )
    estimated_hours = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        default=None,
        verbose_name=_("estimated hours"),
    )
    actual_hours = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        default=None,
        verbose_name=_("actual hours"),
    )
    color = models.CharField(
        max_length=32,
        null=True,
        blank=True,
        default=None,
        verbose_name=_("color"),
    )
    modified_date = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "schedule"
        verbose_name_plural = "schedules"
        unique_together = (("entity_type", "entity_id"),)
        indexes = [
            models.Index(fields=["entity_type", "entity_id"]),
        ]

    def __str__(self):
        return "{}:{}".format(self.entity_type, self.entity_id)
