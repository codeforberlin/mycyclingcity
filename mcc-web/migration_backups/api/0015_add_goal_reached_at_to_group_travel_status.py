# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    0015_add_goal_reached_at_to_group_travel_status.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0014_add_leaf_group_travel_contribution'),
    ]

    operations = [
        migrations.AddField(
            model_name='grouptravelstatus',
            name='goal_reached_at',
            field=models.DateTimeField(blank=True, help_text='Zeitpunkt, zu dem die Gruppe das Ziel erreicht hat. Wird für die Sortierung am Ziel verwendet.', null=True, verbose_name='Ziel erreicht am'),
        ),
    ]
