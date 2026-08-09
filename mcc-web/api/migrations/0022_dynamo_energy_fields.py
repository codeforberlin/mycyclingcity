# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Generated migration: dynamo energy fields on session + HourlyMetric.

from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0021_cyclist_arena_sim_allowed'),
    ]

    operations = [
        migrations.AddField(
            model_name='cyclistdevicecurrentmileage',
            name='last_power_w',
            field=models.FloatField(
                default=0.0,
                help_text='Momentanleistung aus dem letzten Distanz-Intervall.',
                verbose_name='Letzte Leistung (W)',
            ),
        ),
        migrations.AddField(
            model_name='cyclistdevicecurrentmileage',
            name='last_rpm',
            field=models.FloatField(
                default=0.0,
                help_text='Mittlere Rad-Drehzahl aus dem letzten Distanz-Intervall.',
                verbose_name='Letzte Drehzahl (RPM)',
            ),
        ),
        migrations.AddField(
            model_name='cyclistdevicecurrentmileage',
            name='last_speed_kmh',
            field=models.FloatField(
                default=0.0,
                help_text='Mittlere Geschwindigkeit aus dem letzten Distanz-Intervall.',
                verbose_name='Letzte Geschwindigkeit (km/h)',
            ),
        ),
        migrations.AddField(
            model_name='cyclistdevicecurrentmileage',
            name='session_energy_wh',
            field=models.DecimalField(
                decimal_places=5,
                default=Decimal('0.00000'),
                help_text='Virtuelle Nabendynamo-Energie seit Session-Start.',
                max_digits=15,
                verbose_name='Sitzungs-Energie (Wh)',
            ),
        ),
        migrations.AddField(
            model_name='hourlymetric',
            name='energy_wh',
            field=models.DecimalField(
                decimal_places=5,
                default=Decimal('0.00000'),
                help_text=(
                    'Summierte virtuelle Nabendynamo-Energie (Wh) für diese Stunde. '
                    'Wird beim Distanz-Ingest aus Intervallgeschwindigkeit berechnet.'
                ),
                max_digits=15,
                verbose_name='Energie (Wh)',
            ),
        ),
    ]
