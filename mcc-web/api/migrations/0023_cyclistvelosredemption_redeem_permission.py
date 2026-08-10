# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0022_dynamo_energy_fields'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='cyclistvelosredemption',
            options={
                'ordering': ['-redeemed_at'],
                'permissions': [
                    ('redeem_velos', 'Velos von Radlern einlösen'),
                ],
                'verbose_name': 'Velos-Einlösung',
                'verbose_name_plural': 'Velos-Einlösungen',
            },
        ),
    ]
