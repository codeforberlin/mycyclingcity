# Generated manually for unique name constraints
# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0013_alter_groupmilestoneachievement_options_and_more'),
    ]

    operations = [
        # Remove unique_together constraint from Group
        migrations.AlterUniqueTogether(
            name='group',
            unique_together=set(),
        ),
        # Add unique constraint to Group.name
        migrations.AlterField(
            model_name='group',
            name='name',
            field=models.CharField(max_length=100, unique=True, verbose_name='Gruppenname'),
        ),
        # Add unique constraint to TravelTrack.name
        migrations.AlterField(
            model_name='traveltrack',
            name='name',
            field=models.CharField(max_length=100, unique=True, verbose_name='Name der Route'),
        ),
        # Add unique constraint to Milestone.name
        migrations.AlterField(
            model_name='milestone',
            name='name',
            field=models.CharField(max_length=100, unique=True, verbose_name='Bezeichnung'),
        ),
    ]
