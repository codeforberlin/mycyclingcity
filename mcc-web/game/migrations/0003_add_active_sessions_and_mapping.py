# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    0003_add_active_sessions_and_mapping.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
# Generated migration for active_sessions and session_to_cyclist fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('game', '0002_add_master_session_key'),
    ]

    operations = [
        migrations.AddField(
            model_name='gameroom',
            name='active_sessions',
            field=models.JSONField(blank=True, default=list, verbose_name='Aktive Sessions'),
        ),
        migrations.AddField(
            model_name='gameroom',
            name='session_to_cyclist',
            field=models.JSONField(blank=True, default=dict, verbose_name='Session zu Cyclist Mapping'),
        ),
    ]
