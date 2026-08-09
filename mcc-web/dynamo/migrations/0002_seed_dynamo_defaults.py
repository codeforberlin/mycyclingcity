# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Seed default dynamo battery targets and display settings singleton.

from decimal import Decimal

from django.db import migrations


DEFAULT_BATTERIES = [
    ('Smartphone', Decimal('15.00'), 'phone', 10),
    ('Tablet', Decimal('40.00'), 'tablet', 20),
    ('Notebook', Decimal('60.00'), 'notebook', 30),
    ('E-Bike-Akku', Decimal('500.00'), 'ebike', 40),
    ('Haushalts-Anteil', Decimal('1000.00'), 'house', 50),
]


def seed_dynamo_defaults(apps, schema_editor):
    DynamoDisplaySettings = apps.get_model('dynamo', 'DynamoDisplaySettings')
    DynamoBatteryTarget = apps.get_model('dynamo', 'DynamoBatteryTarget')
    DynamoDisplaySettings.objects.get_or_create(pk=1)
    if DynamoBatteryTarget.objects.exists():
        return
    for name, capacity, icon_key, sort_order in DEFAULT_BATTERIES:
        DynamoBatteryTarget.objects.create(
            name=name,
            capacity_wh=capacity,
            icon_key=icon_key,
            sort_order=sort_order,
            is_active=True,
            use_daily_energy=True,
        )


def unseed_dynamo_defaults(apps, schema_editor):
    DynamoBatteryTarget = apps.get_model('dynamo', 'DynamoBatteryTarget')
    DynamoBatteryTarget.objects.filter(
        name__in=[name for name, *_ in DEFAULT_BATTERIES]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('dynamo', '0001_dynamo_energy_fields'),
    ]

    operations = [
        migrations.RunPython(seed_dynamo_defaults, unseed_dynamo_defaults),
    ]
