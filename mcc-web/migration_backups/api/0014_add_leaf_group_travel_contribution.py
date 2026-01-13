# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    0014_add_leaf_group_travel_contribution.py
# @author  Roland Rutz

#
import django.db.models.deletion
from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0013_add_popup_colors_and_opacity'),
    ]

    operations = [
        migrations.CreateModel(
            name='LeafGroupTravelContribution',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('current_travel_distance', models.DecimalField(decimal_places=5, default=Decimal('0.00000'), help_text='Die von dieser Leaf-Gruppe während der aktuellen Reise zurückgelegte Distanz', max_digits=15, verbose_name='Aktuelle Reise-Distanz (km)')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Aktualisiert am')),
                ('leaf_group', models.ForeignKey(help_text='Die Leaf-Gruppe (z.B. Klasse), die Kilometer beiträgt', on_delete=django.db.models.deletion.CASCADE, related_name='travel_contributions', to='api.group', verbose_name='Leaf-Gruppe')),
                ('track', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='leaf_group_contributions', to='api.traveltrack', verbose_name='Reisen-Track')),
            ],
            options={
                'verbose_name': 'Leaf-Gruppe Reise-Beitrag',
                'verbose_name_plural': 'Leaf-Gruppe Reise-Beiträge',
                'indexes': [models.Index(fields=['leaf_group', 'track'], name='api_leafgro_leaf_gr_0e2a34_idx'), models.Index(fields=['track', '-current_travel_distance'], name='api_leafgro_track_i_ee21e4_idx')],
                'unique_together': {('leaf_group', 'track')},
            },
        ),
    ]
