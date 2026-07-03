# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('game', '0006_timer_expired'),
    ]

    operations = [
        migrations.AddField(
            model_name='gameroom',
            name='stop_session_km',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Eingefrorene Session-km beim Spielstopp (z.B. {'cyclist1': 1.25})",
                verbose_name='Stopp-Session-km',
            ),
        ),
        migrations.AddField(
            model_name='gameroom',
            name='stop_session_velos',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Eingefrorene Session-Velos beim Spielstopp (z.B. {'cyclist1': 120})",
                verbose_name='Stopp-Session-Velos',
            ),
        ),
    ]
