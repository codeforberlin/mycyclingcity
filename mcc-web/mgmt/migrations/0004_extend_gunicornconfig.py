# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    0004_extend_gunicornconfig.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
# Generated migration for extending GunicornConfig model

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mgmt', '0003_gunicornconfig'),
    ]

    operations = [
        migrations.AddField(
            model_name='gunicornconfig',
            name='workers',
            field=models.IntegerField(default=0, help_text='Anzahl der Worker-Prozesse (0 = automatisch: CPU * 2 + 1)', verbose_name='Worker Anzahl'),
        ),
        migrations.AddField(
            model_name='gunicornconfig',
            name='worker_class',
            field=models.CharField(choices=[('sync', 'sync - Synchronous workers (Standard)'), ('gevent', 'gevent - Async workers (benötigt gevent)'), ('eventlet', 'eventlet - Async workers (benötigt eventlet)')], default='sync', help_text='Worker-Klasse für Gunicorn', max_length=20, verbose_name='Worker Klasse'),
        ),
        migrations.AddField(
            model_name='gunicornconfig',
            name='timeout',
            field=models.IntegerField(default=30, help_text='Worker-Timeout in Sekunden', verbose_name='Timeout (Sekunden)'),
        ),
        migrations.AddField(
            model_name='gunicornconfig',
            name='graceful_timeout',
            field=models.IntegerField(default=30, help_text='Timeout für graceful shutdown', verbose_name='Graceful Timeout (Sekunden)'),
        ),
        migrations.AddField(
            model_name='gunicornconfig',
            name='keepalive',
            field=models.IntegerField(default=2, help_text='Keepalive-Timeout für Verbindungen', verbose_name='Keepalive (Sekunden)'),
        ),
        migrations.AddField(
            model_name='gunicornconfig',
            name='max_requests',
            field=models.IntegerField(default=1000, help_text='Anzahl Requests nach denen ein Worker neu gestartet wird (0 = deaktiviert)', verbose_name='Max Requests'),
        ),
        migrations.AddField(
            model_name='gunicornconfig',
            name='max_requests_jitter',
            field=models.IntegerField(default=50, help_text='Zufällige Variation für max_requests', verbose_name='Max Requests Jitter'),
        ),
        migrations.AddField(
            model_name='gunicornconfig',
            name='preload_app',
            field=models.BooleanField(default=True, help_text='Lädt Anwendungscode vor dem Forken der Worker', verbose_name='Preload App'),
        ),
        migrations.AddField(
            model_name='gunicornconfig',
            name='bind_address',
            field=models.CharField(default='127.0.0.1:8001', help_text='Adresse und Port, an die Gunicorn gebunden wird (z.B. 127.0.0.1:8001)', max_length=100, verbose_name='Bind Adresse'),
        ),
    ]
