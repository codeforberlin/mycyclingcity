# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    0007_groupmilestoneachievement.py
# @author  Roland Rutz

#
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0006_add_track_filter'),
    ]

    operations = [
        migrations.CreateModel(
            name='GroupMilestoneAchievement',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('reached_at', models.DateTimeField(verbose_name='Erreicht am')),
                ('reached_distance', models.DecimalField(blank=True, decimal_places=5, max_digits=15, null=True, verbose_name='Erreichte Distanz (km)')),
                ('group', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='milestone_achievements', to='api.group', verbose_name='Gruppe')),
                ('milestone', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='achievements', to='api.milestone', verbose_name='Meilenstein')),
                ('track', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='milestone_achievements', to='api.traveltrack', verbose_name='Route')),
            ],
            options={
                'verbose_name': 'Travels - Meilenstein-Erreichung',
                'verbose_name_plural': 'Travels - Meilenstein-Erreichungen',
                'ordering': ['-reached_at'],
                'indexes': [models.Index(fields=['group', 'reached_at'], name='api_groupmi_group_i_c994f0_idx'), models.Index(fields=['track', 'reached_at'], name='api_groupmi_track_i_6c6835_idx')],
                'unique_together': {('group', 'milestone')},
            },
        ),
    ]
