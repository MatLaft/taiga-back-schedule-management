# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos INC

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("schedule", "0005_add_schedule_color"),
    ]

    operations = [
        migrations.CreateModel(
            name="ScheduleDependency",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "from_schedule",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="outgoing_dependencies",
                        to="schedule.schedule",
                    ),
                ),
                (
                    "to_schedule",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="incoming_dependencies",
                        to="schedule.schedule",
                    ),
                ),
            ],
            options={
                "verbose_name": "schedule dependency",
                "verbose_name_plural": "schedule dependencies",
                "unique_together": {("from_schedule", "to_schedule")},
            },
        ),
    ]
