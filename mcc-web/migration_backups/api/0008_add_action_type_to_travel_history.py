# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    0008_add_action_type_to_travel_history.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0007_groupmilestoneachievement'),
    ]

    operations = [
        migrations.AddField(
            model_name='travelhistory',
            name='action_type',
            field=models.CharField(choices=[('assigned', 'Zuordnung'), ('aborted', 'Abgebrochen'), ('completed', 'Beendet'), ('restarted', 'Neu gestartet'), ('removed', 'Entfernt')], default='completed', help_text='Art der Aktion, die zu diesem Historieeintrag geführt hat', max_length=20, verbose_name='Aktionstyp'),
        ),
    ]
