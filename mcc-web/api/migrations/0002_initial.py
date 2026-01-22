# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    0002_initial.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0001_initial'),
        ('iot', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='hourlymetric',
            name='device',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='metrics', to='iot.device', verbose_name='Gerät'),
        ),
        migrations.AddField(
            model_name='hourlymetric',
            name='group_at_time',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='api.group', verbose_name='Gruppe'),
        ),
        migrations.AddField(
            model_name='leafgrouptravelcontribution',
            name='leaf_group',
            field=models.ForeignKey(help_text='Die Leaf-Gruppe (z.B. Klasse), die Kilometer beiträgt', on_delete=django.db.models.deletion.CASCADE, related_name='travel_contributions', to='api.group', verbose_name='Leaf-Gruppe'),
        ),
        migrations.AddField(
            model_name='milestone',
            name='winner_group',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='api.group', verbose_name='Gewinner'),
        ),
        migrations.AddField(
            model_name='groupmilestoneachievement',
            name='milestone',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='achievements', to='api.milestone', verbose_name='Meilenstein'),
        ),
        migrations.AddField(
            model_name='travelhistory',
            name='group',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='travel_history', to='api.group', verbose_name='Gruppe'),
        ),
        migrations.AddField(
            model_name='travelhistory',
            name='track',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='history_entries', to='api.traveltrack', verbose_name='Reisen - Route'),
        ),
        migrations.AddField(
            model_name='milestone',
            name='track',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='milestones', to='api.traveltrack', verbose_name='Route'),
        ),
        migrations.AddField(
            model_name='leafgrouptravelcontribution',
            name='track',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='leaf_group_contributions', to='api.traveltrack', verbose_name='Reisen-Track'),
        ),
        migrations.AddField(
            model_name='grouptravelstatus',
            name='track',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='group_statuses', to='api.traveltrack', verbose_name='Reisen-Track'),
        ),
        migrations.AddField(
            model_name='groupmilestoneachievement',
            name='track',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='milestone_achievements', to='api.traveltrack', verbose_name='Route'),
        ),
        migrations.AddField(
            model_name='cyclistdevicecurrentmileage',
            name='device',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='iot.device', verbose_name='Gerät'),
        ),
        migrations.AlterUniqueTogether(
            name='eventhistory',
            unique_together={('event', 'group', 'start_time')},
        ),
        migrations.AlterUniqueTogether(
            name='groupeventstatus',
            unique_together={('group', 'event')},
        ),
        migrations.AddIndex(
            model_name='group',
            index=models.Index(fields=['group_type', 'name'], name='api_group_group_t_ac03c5_idx'),
        ),
        migrations.AlterUniqueTogether(
            name='group',
            unique_together={('group_type', 'name')},
        ),
        migrations.AddIndex(
            model_name='leafgrouptravelcontribution',
            index=models.Index(fields=['leaf_group', 'track'], name='api_leafgro_leaf_gr_0e2a34_idx'),
        ),
        migrations.AddIndex(
            model_name='leafgrouptravelcontribution',
            index=models.Index(fields=['track', '-current_travel_distance'], name='api_leafgro_track_i_ee21e4_idx'),
        ),
        migrations.AlterUniqueTogether(
            name='leafgrouptravelcontribution',
            unique_together={('leaf_group', 'track')},
        ),
        migrations.AddIndex(
            model_name='groupmilestoneachievement',
            index=models.Index(fields=['group', 'reached_at'], name='api_groupmi_group_i_c994f0_idx'),
        ),
        migrations.AddIndex(
            model_name='groupmilestoneachievement',
            index=models.Index(fields=['track', 'reached_at'], name='api_groupmi_track_i_6c6835_idx'),
        ),
        migrations.AddIndex(
            model_name='groupmilestoneachievement',
            index=models.Index(fields=['group', 'is_redeemed'], name='api_groupmi_group_i_d6bff0_idx'),
        ),
        migrations.AlterUniqueTogether(
            name='groupmilestoneachievement',
            unique_together={('group', 'milestone')},
        ),
    ]
