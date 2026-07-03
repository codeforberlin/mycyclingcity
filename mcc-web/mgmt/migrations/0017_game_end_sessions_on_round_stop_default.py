# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.db import migrations, models


def enable_end_sessions_on_round_stop(apps, schema_editor):
    GameConfiguration = apps.get_model('mgmt', 'GameConfiguration')
    GameConfiguration.objects.filter(pk=1).update(end_device_sessions_on_round_stop=True)


class Migration(migrations.Migration):

    dependencies = [
        ('mgmt', '0016_fezitty_game_workflow'),
    ]

    operations = [
        migrations.AlterField(
            model_name='gameconfiguration',
            name='end_device_sessions_on_round_stop',
            field=models.BooleanField(
                default=True,
                help_text='Zusätzlich beim Spiel stoppen (oder Timer-Auto-Stopp) Geräte-Sessions beenden.',
                verbose_name='Geräte-Sessions bei Spielstopp beenden',
            ),
        ),
        migrations.RunPython(enable_end_sessions_on_round_stop, migrations.RunPython.noop),
    ]
