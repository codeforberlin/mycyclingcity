# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    0002_add_track_filter.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0006_add_track_filter'),
        ('kiosk', '0001_initial'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='kioskdevice',
            options={'ordering': ['name'], 'verbose_name': 'Device', 'verbose_name_plural': 'Devices'},
        ),
        migrations.AddField(
            model_name='kioskplaylistentry',
            name='track_filter',
            field=models.ManyToManyField(blank=True, help_text='Optional: Filter map view to show only selected tracks (leave empty to show all tracks)', related_name='kiosk_playlist_entries', to='api.traveltrack', verbose_name='Track Filter'),
        ),
        migrations.AlterField(
            model_name='kioskplaylistentry',
            name='order',
            field=models.PositiveIntegerField(default=1, help_text='Display order in the playlist (lower numbers first, starts at 1)', verbose_name='Order'),
        ),
    ]
