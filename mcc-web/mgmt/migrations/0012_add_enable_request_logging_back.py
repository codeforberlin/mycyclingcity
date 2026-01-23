# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    0012_add_enable_request_logging_back.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
# Migration to add enable_request_logging field back to LoggingConfig

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mgmt', '0011_remove_application_log_and_update_logging_config'),
    ]

    operations = [
        migrations.AddField(
            model_name='loggingconfig',
            name='enable_request_logging',
            field=models.BooleanField(
                default=False,
                help_text='Wenn aktiviert, werden alle HTTP-Requests in der Datenbank gespeichert (RequestLog). Deaktivieren Sie dies, um die Datenbank nicht zu überladen.',
                verbose_name='Request Logs aktivieren'
            ),
        ),
    ]
