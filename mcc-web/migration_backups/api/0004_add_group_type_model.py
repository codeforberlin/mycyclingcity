# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    0004_add_group_type_model.py
# @author  Roland Rutz

#
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0003_cyclist_remove_hourlymetric_player_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='GroupType',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=50, unique=True, verbose_name='Typ-Name')),
                ('description', models.TextField(blank=True, null=True, verbose_name='Beschreibung')),
                ('is_active', models.BooleanField(default=True, verbose_name='Aktiv')),
            ],
            options={
                'verbose_name': 'Gruppentyp',
                'verbose_name_plural': 'Gruppentypen',
                'ordering': ['name'],
            },
        ),
        migrations.AlterField(
            model_name='group',
            name='group_type',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='groups', to='api.grouptype', verbose_name='Gruppentyp'),
        ),
        migrations.AddIndex(
            model_name='group',
            index=models.Index(fields=['group_type', 'name'], name='api_group_group_t_ac03c5_idx'),
        ),
    ]
