# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    0006_add_track_filter.py
# @author  Roland Rutz

#
import django.db.models.deletion
from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0005_populate_group_types'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='cyclist',
            options={'verbose_name': 'Cyclist', 'verbose_name_plural': 'Cyclists'},
        ),
        migrations.AlterModelOptions(
            name='cyclistdevicecurrentmileage',
            options={'verbose_name': 'Cyclist - Active Session', 'verbose_name_plural': 'Cyclists - Active Sessions'},
        ),
        migrations.AlterModelOptions(
            name='eventhistory',
            options={'ordering': ['-end_time'], 'verbose_name': 'Events - History', 'verbose_name_plural': 'Events - Histories'},
        ),
        migrations.AlterModelOptions(
            name='group',
            options={'verbose_name': 'Group', 'verbose_name_plural': 'Groups'},
        ),
        migrations.AlterModelOptions(
            name='grouptravelstatus',
            options={'verbose_name': 'Travels - Status', 'verbose_name_plural': 'Travels - Status'},
        ),
        migrations.AlterModelOptions(
            name='grouptype',
            options={'ordering': ['name'], 'verbose_name': 'Group Type', 'verbose_name_plural': 'Group Types'},
        ),
        migrations.AlterModelOptions(
            name='hourlymetric',
            options={'verbose_name': 'Hourly Metric', 'verbose_name_plural': 'Hourly Metrics'},
        ),
        migrations.AlterModelOptions(
            name='milestone',
            options={'ordering': ['distance_km'], 'verbose_name': 'Travels - Milestone', 'verbose_name_plural': 'Travels - Milestones'},
        ),
        migrations.AlterModelOptions(
            name='travelhistory',
            options={'ordering': ['-end_time'], 'verbose_name': 'Travels - History', 'verbose_name_plural': 'Travels - Histories'},
        ),
        migrations.AlterModelOptions(
            name='traveltrack',
            options={'verbose_name': 'Travels - Route', 'verbose_name_plural': 'Travels - Routes'},
        ),
        migrations.AlterField(
            model_name='grouptravelstatus',
            name='current_travel_distance',
            field=models.DecimalField(decimal_places=5, default=Decimal('0.00000'), max_digits=15, verbose_name='Aktuelle Reisen-Distanz (km)'),
        ),
        migrations.AlterField(
            model_name='grouptravelstatus',
            name='track',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='group_statuses', to='api.traveltrack', verbose_name='Reisen-Track'),
        ),
        migrations.AlterField(
            model_name='travelhistory',
            name='track',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='history_entries', to='api.traveltrack', verbose_name='Reisen - Route'),
        ),
    ]
