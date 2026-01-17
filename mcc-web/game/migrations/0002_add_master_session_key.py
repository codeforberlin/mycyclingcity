# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    0002_add_master_session_key.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
# Generated migration for master_session_key field

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('game', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='gameroom',
            name='master_session_key',
            field=models.CharField(blank=True, help_text='Session-Key des Raum-Masters (Spielleiter)', max_length=40, null=True, verbose_name='Master Session Key'),
        ),
    ]
