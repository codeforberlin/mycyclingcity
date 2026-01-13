# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    0011_add_reward_fields_to_group_milestone_achievement.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0010_add_auto_start_to_travel_track'),
    ]

    operations = [
        migrations.AddField(
            model_name='groupmilestoneachievement',
            name='is_redeemed',
            field=models.BooleanField(default=False, help_text='Gibt an, ob die Belohnung bereits eingelöst wurde. Eine Belohnung kann nur einmal eingelöst werden.', verbose_name='Eingelöst'),
        ),
        migrations.AddField(
            model_name='groupmilestoneachievement',
            name='redeemed_at',
            field=models.DateTimeField(blank=True, help_text='Zeitpunkt, zu dem die Belohnung eingelöst wurde.', null=True, verbose_name='Eingelöst am'),
        ),
        migrations.AddField(
            model_name='groupmilestoneachievement',
            name='reward_text',
            field=models.CharField(blank=True, help_text='Die Belohnung, die zum Zeitpunkt des Erreichens des Meilensteins definiert war. Diese bleibt unverändert, auch wenn die Meilenstein-Belohnung später geändert wird.', max_length=200, null=True, verbose_name='Belohnung'),
        ),
        migrations.AddIndex(
            model_name='groupmilestoneachievement',
            index=models.Index(fields=['group', 'is_redeemed'], name='api_groupmi_group_i_d6bff0_idx'),
        ),
    ]
