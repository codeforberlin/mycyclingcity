# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    0003_gunicornconfig.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
# Generated migration for GunicornConfig model

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('mgmt', '0002_loggingconfig'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='GunicornConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('log_level', models.CharField(choices=[('debug', 'DEBUG - Sehr detaillierte Ausgaben'), ('info', 'INFO - Informative Meldungen (Standard)'), ('warning', 'WARNING - Nur Warnungen'), ('error', 'ERROR - Nur Fehler'), ('critical', 'CRITICAL - Nur kritische Fehler')], default='info', help_text='Gunicorn Log-Level. Änderungen erfordern einen Server-Neustart.', max_length=10, verbose_name='Log Level')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Zuletzt aktualisiert')),
                ('updated_by', models.ForeignKey(blank=True, help_text='Benutzer, der diese Einstellung zuletzt geändert hat', null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL, verbose_name='Aktualisiert von')),
            ],
            options={
                'verbose_name': 'Gunicorn Configuration',
                'verbose_name_plural': 'Gunicorn Configuration',
            },
        ),
    ]
