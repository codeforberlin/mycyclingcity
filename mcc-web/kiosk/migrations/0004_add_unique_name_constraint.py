# Generated manually for unique name constraint
# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('kiosk', '0003_alter_kioskdevice_brightness_and_more'),
    ]

    operations = [
        # Add unique constraint to KioskDevice.name
        migrations.AlterField(
            model_name='kioskdevice',
            name='name',
            field=models.CharField(max_length=200, unique=True, verbose_name='Gerätename', help_text='Lesbarer Name für dieses Kiosk-Gerät'),
        ),
    ]
