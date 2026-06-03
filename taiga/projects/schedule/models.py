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

    @property
    def project_id(self):
        if self.from_schedule_id and getattr(self, "from_schedule", None):
            return self.from_schedule.project_id

        if self.to_schedule_id and getattr(self, "to_schedule", None):
            return self.to_schedule.project_id

        if self.from_schedule_id:
            project_id = (
                Schedule.objects.filter(id=self.from_schedule_id)
                .values_list("project_id", flat=True)
                .first()
            )
            if project_id is not None:
                return project_id

        if self.to_schedule_id:
            return (
                Schedule.objects.filter(id=self.to_schedule_id)
                .values_list("project_id", flat=True)
                .first()
            )

        return None

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


class ScheduleItemOrder(models.Model):
    ROOT_PARENT_ENTITY_TYPE = ""
    ROOT_PARENT_ENTITY_ID = 0

    schedule = models.OneToOneField(
        Schedule,
        related_name="item_order",
        on_delete=models.CASCADE,
    )
    project_id = models.BigIntegerField(db_index=True)
    entity_type = models.CharField(
        max_length=16, choices=Schedule.ENTITY_TYPE_CHOICES, db_index=True
    )
    parent_entity_type = models.CharField(
        max_length=16,
        blank=True,
        default=ROOT_PARENT_ENTITY_TYPE,
        db_index=True,
    )
    parent_entity_id = models.BigIntegerField(
        default=ROOT_PARENT_ENTITY_ID, db_index=True
    )
    position = models.PositiveIntegerField(default=1)
    modified_date = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "schedule item order"
        verbose_name_plural = "schedule item orders"
        unique_together = (
            ("project_id", "entity_type", "parent_entity_type", "parent_entity_id", "position"),
        )
        indexes = [
            models.Index(
                fields=[
                    "project_id",
                    "entity_type",
                    "parent_entity_type",
                    "parent_entity_id",
                    "position",
                ],
                name="schedule_sc_project_484285_idx",
            ),
        ]
        ordering = [
            "project_id",
            "entity_type",
            "parent_entity_type",
            "parent_entity_id",
            "position",
            "id",
        ]

    def clean(self):
        super().clean()

        if not self.schedule_id:
            return

        schedule = self.schedule

        if schedule.project_id != self.project_id:
            raise ValidationError(
                _("The schedule order project must match the schedule project.")
            )

        if schedule.entity_type != self.entity_type:
            raise ValidationError(
                _("The schedule order entity type must match the schedule entity type.")
            )

        if self.position is None or self.position < 1:
            raise ValidationError(_("The schedule order position must be greater than zero."))

        is_root_parent = (
            self.parent_entity_type == self.ROOT_PARENT_ENTITY_TYPE
            and self.parent_entity_id == self.ROOT_PARENT_ENTITY_ID
        )

        if self.entity_type == Schedule.TYPE_EPIC:
            if not is_root_parent:
                raise ValidationError(_("Epic schedule order items must have a root parent."))
            return

        if self.entity_type == Schedule.TYPE_USERSTORY:
            if is_root_parent:
                return
            if self.parent_entity_type != Schedule.TYPE_EPIC:
                raise ValidationError(
                    _("User story schedule order items can only be grouped by epic parent.")
                )
            return

        if self.entity_type == Schedule.TYPE_TASK:
            if is_root_parent:
                return
            if self.parent_entity_type != Schedule.TYPE_USERSTORY:
                raise ValidationError(
                    _("Task schedule order items can only be grouped by user story parent.")
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return "{}:{}@{}".format(self.entity_type, self.schedule_id, self.position)
