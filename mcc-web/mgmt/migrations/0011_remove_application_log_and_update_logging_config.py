# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    0011_remove_application_log_and_update_logging_config.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
# Migration to remove ApplicationLog model and update LoggingConfig

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('mgmt', '0010_add_threads_to_gunicornconfig'),
        migrations.swappable_dependency('auth.User'),
    ]

    operations = [
        # Remove ApplicationLog model
        migrations.DeleteModel(
            name='ApplicationLog',
        ),
        # Update LoggingConfig: remove enable_request_logging, change default to INFO
        migrations.RemoveField(
            model_name='loggingconfig',
            name='enable_request_logging',
        ),
        migrations.AlterField(
            model_name='loggingconfig',
            name='min_log_level',
            field=models.CharField(
                choices=[
                    ('DEBUG', 'DEBUG - Alle Logs (DEBUG, INFO, WARNING, ERROR, CRITICAL)'),
                    ('INFO', 'INFO - Informative und kritische Logs (INFO, WARNING, ERROR, CRITICAL)'),
                    ('WARNING', 'WARNING - Nur kritische Logs (WARNING, ERROR, CRITICAL)'),
                    ('ERROR', 'ERROR - Nur Fehler (ERROR, CRITICAL)'),
                    ('CRITICAL', 'CRITICAL - Nur kritische Fehler'),
                ],
                default='INFO',
                help_text='Nur Logs mit diesem Level oder höher werden in die Log-Dateien geschrieben.',
                max_length=10,
                verbose_name='Minimum Log Level'
            ),
        ),
    ]
