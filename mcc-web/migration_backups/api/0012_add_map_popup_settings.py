# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    0012_add_map_popup_settings.py
# @author  Roland Rutz

#
import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0011_add_reward_fields_to_group_milestone_achievement'),
    ]

    operations = [
        migrations.CreateModel(
            name='MapPopupSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('weltmeister_popup_duration_seconds', models.IntegerField(default=6, help_text='Anzeigedauer des Kilometer-Weltmeister Popups in Sekunden (1-300)', validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(300)], verbose_name='Kilometer-Weltmeister Popup Dauer (Sekunden)')),
                ('milestone_popup_duration_seconds', models.IntegerField(default=30, help_text='Anzeigedauer des Meilenstein Popups in Sekunden (1-300)', validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(300)], verbose_name='Meilenstein Popup Dauer (Sekunden)')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Aktualisiert am')),
            ],
            options={
                'verbose_name': 'Map Popup Einstellungen',
                'verbose_name_plural': 'Map Popup Einstellungen',
            },
        ),
    ]
