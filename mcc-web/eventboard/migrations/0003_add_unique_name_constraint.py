# Generated manually for unique name constraint
# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('eventboard', '0002_add_top_group_to_event'),
    ]

    operations = [
        # Add unique constraint to Event.name
        migrations.AlterField(
            model_name='event',
            name='name',
            field=models.CharField(max_length=200, unique=True, verbose_name='Event-Name'),
        ),
    ]
