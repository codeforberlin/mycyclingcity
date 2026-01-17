# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    0001_initial.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
# Generated migration for GameRoom model

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='GameRoom',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('room_code', models.CharField(default='', help_text='6-stelliger Code zum Beitreten des Raums', max_length=6, unique=True, verbose_name='Raum-Code')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Erstellt am')),
                ('last_activity', models.DateTimeField(auto_now=True, verbose_name='Letzte Aktivität')),
                ('is_active', models.BooleanField(default=True, help_text='Ob der Raum noch aktiv ist', verbose_name='Aktiv')),
                ('device_assignments', models.JSONField(blank=True, default=dict, help_text='Dictionary: {device_name: cyclist_user_id}', verbose_name='Geräte-Zuweisungen')),
                ('start_distances', models.JSONField(blank=True, default=dict, help_text='Dictionary: {cyclist_user_id: start_distance}', verbose_name='Start-Distanzen')),
                ('stop_distances', models.JSONField(blank=True, default=dict, help_text='Dictionary: {cyclist_user_id: stop_distance}', verbose_name='Stop-Distanzen')),
                ('is_game_stopped', models.BooleanField(default=False, verbose_name='Spiel gestoppt')),
                ('announced_winners', models.JSONField(blank=True, default=list, help_text='Liste von cyclist_user_id, die bereits ein Popup erhalten haben', verbose_name='Bereits angekündigte Gewinner')),
                ('current_target_km', models.FloatField(default=0.0, verbose_name='Aktuelles Ziel (km)')),
            ],
            options={
                'verbose_name': 'Spiel-Raum',
                'verbose_name_plural': 'Spiel-Räume',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='gameroom',
            index=models.Index(fields=['room_code'], name='game_gamero_room_co_idx'),
        ),
        migrations.AddIndex(
            model_name='gameroom',
            index=models.Index(fields=['is_active', '-last_activity'], name='game_gamero_is_acti_idx'),
        ),
    ]
