# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    0001_applicationlog.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
# Generated migration for ApplicationLog model

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='ApplicationLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('level', models.CharField(choices=[('DEBUG', 'DEBUG'), ('INFO', 'INFO'), ('WARNING', 'WARNING'), ('ERROR', 'ERROR'), ('CRITICAL', 'CRITICAL')], db_index=True, max_length=10, verbose_name='Level')),
                ('logger_name', models.CharField(db_index=True, max_length=100, verbose_name='Logger Name', help_text='Name of the logger that generated this log entry')),
                ('message', models.TextField(verbose_name='Message', help_text='The log message')),
                ('module', models.CharField(blank=True, max_length=200, verbose_name='Module', help_text='Module where the log was generated')),
                ('timestamp', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Timestamp')),
                ('exception_info', models.TextField(blank=True, null=True, verbose_name='Exception Info', help_text='Exception traceback if available')),
                ('extra_data', models.JSONField(blank=True, null=True, verbose_name='Extra Data', help_text='Additional context data as JSON')),
            ],
            options={
                'verbose_name': 'Application Log',
                'verbose_name_plural': 'Application Logs',
                'ordering': ['-timestamp'],
            },
        ),
        migrations.AddIndex(
            model_name='applicationlog',
            index=models.Index(fields=['level', '-timestamp'], name='mgmt_applic_level_t_8a1b2c_idx'),
        ),
        migrations.AddIndex(
            model_name='applicationlog',
            index=models.Index(fields=['logger_name', '-timestamp'], name='mgmt_applic_logger__d3e4f5_idx'),
        ),
        migrations.AddIndex(
            model_name='applicationlog',
            index=models.Index(fields=['-timestamp'], name='mgmt_applic_timesta_6g7h8i_idx'),
        ),
    ]
