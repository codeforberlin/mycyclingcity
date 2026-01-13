# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    0009_remove_unique_constraint_from_travel_history.py
# @author  Roland Rutz

#
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0008_add_action_type_to_travel_history'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='travelhistory',
            unique_together=set(),
        ),
    ]
