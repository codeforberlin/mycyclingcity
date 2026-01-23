# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    0002_loggingconfig.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
# Generated migration for LoggingConfig model

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('mgmt', '0001_applicationlog'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='LoggingConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('min_log_level', models.CharField(choices=[('DEBUG', 'DEBUG - Alle Logs (DEBUG, INFO, WARNING, ERROR, CRITICAL)'), ('INFO', 'INFO - Informative und kritische Logs (INFO, WARNING, ERROR, CRITICAL)'), ('WARNING', 'WARNING - Nur kritische Logs (WARNING, ERROR, CRITICAL)'), ('ERROR', 'ERROR - Nur Fehler (ERROR, CRITICAL)'), ('CRITICAL', 'CRITICAL - Nur kritische Fehler')], default='WARNING', help_text='Nur Logs mit diesem Level oder höher werden in der Datenbank gespeichert und im Admin GUI angezeigt.', max_length=10, verbose_name='Minimum Log Level')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Zuletzt aktualisiert')),
                ('updated_by', models.ForeignKey(blank=True, help_text='Benutzer, der diese Einstellung zuletzt geändert hat', null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL, verbose_name='Aktualisiert von')),
            ],
            options={
                'verbose_name': 'Logging Configuration',
                'verbose_name_plural': 'Logging Configuration',
            },
        ),
    ]
