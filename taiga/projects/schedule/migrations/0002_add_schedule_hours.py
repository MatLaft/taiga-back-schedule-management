# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos INC

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("schedule", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="schedule",
            name="estimated_hours",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                default=None,
                max_digits=10,
                null=True,
                verbose_name="estimated hours",
            ),
        ),
        migrations.AddField(
            model_name="schedule",
            name="actual_hours",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                default=None,
                max_digits=10,
                null=True,
                verbose_name="actual hours",
            ),
        ),
    ]
