# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos INC

from django.core.exceptions import ValidationError
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


class ScheduleDependency(models.Model):
    from_schedule = models.ForeignKey(
        Schedule,
        related_name="outgoing_dependencies",
        on_delete=models.CASCADE,
    )
    to_schedule = models.ForeignKey(
        Schedule,
        related_name="incoming_dependencies",
        on_delete=models.CASCADE,
    )

    class Meta:
        verbose_name = "schedule dependency"
        verbose_name_plural = "schedule dependencies"
        unique_together = (("from_schedule", "to_schedule"),)

    def clean(self):
        super().clean()

        if not self.from_schedule_id or not self.to_schedule_id:
            return

        if self.from_schedule_id == self.to_schedule_id:
            raise ValidationError(
                _("The source and target schedules must be different.")
            )

        schedules_by_id = {
            schedule.id: schedule
            for schedule in Schedule.objects.filter(
                id__in=[self.from_schedule_id, self.to_schedule_id]
            )
        }
        from_schedule = schedules_by_id.get(self.from_schedule_id)
        to_schedule = schedules_by_id.get(self.to_schedule_id)

        if from_schedule is None or to_schedule is None:
            return

        if from_schedule.project_id != to_schedule.project_id:
            raise ValidationError(
                _("The source and target schedules must belong to the same project.")
            )

        source_due_date = from_schedule.due_date
        target_start_date = to_schedule.actual_start or to_schedule.estimated_start

        if source_due_date is None:
            raise ValidationError(_("The source schedule must have a due date."))

        if target_start_date is None:
            raise ValidationError(_("The target schedule must have a start date."))

        if target_start_date <= source_due_date:
            raise ValidationError(
                _("The target schedule must start after the source schedule due date.")
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return "{} -> {}".format(self.from_schedule_id, self.to_schedule_id)
