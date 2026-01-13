# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    0010_add_auto_start_to_travel_track.py
# @author  Roland Rutz

#
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0009_remove_unique_constraint_from_travel_history'),
    ]

    operations = [
        migrations.AddField(
            model_name='traveltrack',
            name='auto_start',
            field=models.BooleanField(default=False, help_text='Wenn aktiviert, startet die Reise automatisch beim Eintreffen der ersten Kilometer. Wenn deaktiviert, muss eine Startzeit definiert werden.', verbose_name='Automatischer Start'),
        ),
        migrations.AlterField(
            model_name='traveltrack',
            name='end_time',
            field=models.DateTimeField(blank=True, help_text='Optional: Definiert den Endzeitpunkt der Reise. Wenn nicht gesetzt, läuft die Reise unbegrenzt.', null=True, verbose_name='Endzeitpunkt'),
        ),
        migrations.AlterField(
            model_name='traveltrack',
            name='start_time',
            field=models.DateTimeField(blank=True, help_text="Optional: Definiert den Startzeitpunkt der Reise. Wird ignoriert, wenn 'Automatischer Start' aktiviert ist.", null=True, verbose_name='Startzeitpunkt'),
        ),
    ]
