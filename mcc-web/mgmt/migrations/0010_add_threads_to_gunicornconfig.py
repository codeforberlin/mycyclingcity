# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    0010_add_threads_to_gunicornconfig.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
# Generated migration for adding threads field to GunicornConfig

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mgmt', '0009_add_enable_request_logging'),
    ]

    operations = [
        migrations.AddField(
            model_name='gunicornconfig',
            name='threads',
            field=models.IntegerField(default=2, help_text='Anzahl der Threads pro Worker (nur bei worker_class=\'gthread\' relevant)', verbose_name='Threads pro Worker'),
        ),
        migrations.AlterField(
            model_name='gunicornconfig',
            name='worker_class',
            field=models.CharField(choices=[('sync', 'sync - Synchronous workers (Standard)'), ('gthread', 'gthread - Threaded workers (empfohlen für I/O-intensive Anwendungen)'), ('gevent', 'gevent - Async workers (benötigt gevent)'), ('eventlet', 'eventlet - Async workers (benötigt eventlet)')], default='sync', help_text='Worker-Klasse für Gunicorn', max_length=20, verbose_name='Worker Klasse'),
        ),
    ]
