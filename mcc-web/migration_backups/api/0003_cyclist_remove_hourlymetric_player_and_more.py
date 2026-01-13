# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    0003_cyclist_remove_hourlymetric_player_and_more.py
# @author  Roland Rutz

#
import django.db.models.deletion
import django.utils.timezone
from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0002_initial'),
        ('iot', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Cyclist',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('user_id', models.CharField(max_length=20, verbose_name='Symbolischer Name')),
                ('avatar', models.ImageField(blank=True, null=True, upload_to='cyclist_avatars/', verbose_name='Radler Avatar')),
                ('id_tag', models.CharField(max_length=50, unique=True, verbose_name='RFID-UID')),
                ('mc_username', models.CharField(blank=True, max_length=100, null=True, verbose_name='Minecraft-Name')),
                ('distance_total', models.DecimalField(decimal_places=5, default=Decimal('0.00000'), max_digits=15, verbose_name='Gesamt-KM')),
                ('coins_total', models.IntegerField(default=0, verbose_name='Gesamt-Coins')),
                ('coins_spendable', models.IntegerField(default=0, verbose_name='Ausgebbare Coins')),
                ('coin_conversion_factor', models.FloatField(default=100.0, verbose_name='Coin-Faktor')),
                ('last_active', models.DateTimeField(blank=True, null=True, verbose_name='Zuletzt aktiv')),
                ('is_visible', models.BooleanField(default=True, verbose_name='In Map/Game anzeigen')),
                ('is_km_collection_enabled', models.BooleanField(default=True, help_text='Wenn deaktiviert, werden keine Kilometer für diesen Radler erfasst', verbose_name='Kilometer-Erfassung aktiv')),
                ('groups', models.ManyToManyField(blank=True, related_name='members', to='api.group', verbose_name='Gruppen')),
            ],
            options={
                'verbose_name': 'Radler',
                'verbose_name_plural': 'Radler',
            },
        ),
        migrations.RemoveField(
            model_name='hourlymetric',
            name='player',
        ),
        migrations.RemoveField(
            model_name='playerdevicecurrentmileage',
            name='player',
        ),
        migrations.RemoveField(
            model_name='playerdevicecurrentmileage',
            name='device',
        ),
        migrations.CreateModel(
            name='CyclistDeviceCurrentMileage',
            fields=[
                ('cyclist', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, primary_key=True, serialize=False, to='api.cyclist', verbose_name='Radler')),
                ('cumulative_mileage', models.DecimalField(decimal_places=5, default=Decimal('0.00000'), max_digits=15, verbose_name='Sitzungs-Distanz (km)')),
                ('start_time', models.DateTimeField(default=django.utils.timezone.now, verbose_name='Startzeit')),
                ('last_activity', models.DateTimeField(auto_now=True)),
                ('device', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='iot.device', verbose_name='Gerät')),
            ],
            options={
                'verbose_name': 'Aktueller Sitzungs-Status',
                'verbose_name_plural': 'Aktuelle Sitzungs-Stände',
            },
        ),
        migrations.AddField(
            model_name='hourlymetric',
            name='cyclist',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='metrics', to='api.cyclist', verbose_name='Radler'),
        ),
        migrations.DeleteModel(
            name='Player',
        ),
        migrations.DeleteModel(
            name='PlayerDeviceCurrentMileage',
        ),
    ]
