# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    0005_performance_models.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
# Generated migration for performance tracking models

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('mgmt', '0004_extend_gunicornconfig'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='RequestLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('path', models.CharField(db_index=True, help_text='Request path', max_length=500, verbose_name='Path')),
                ('method', models.CharField(choices=[('GET', 'GET'), ('POST', 'POST'), ('PUT', 'PUT'), ('DELETE', 'DELETE'), ('PATCH', 'PATCH'), ('HEAD', 'HEAD'), ('OPTIONS', 'OPTIONS')], db_index=True, max_length=10, verbose_name='Method')),
                ('status_code', models.IntegerField(db_index=True, verbose_name='Status Code')),
                ('response_time_ms', models.FloatField(help_text='Response time in milliseconds', verbose_name='Response Time (ms)')),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True, verbose_name='IP Address')),
                ('user_agent', models.CharField(blank=True, max_length=500, verbose_name='User Agent')),
                ('timestamp', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Timestamp')),
                ('query_string', models.TextField(blank=True, verbose_name='Query String')),
                ('is_error', models.BooleanField(db_index=True, default=False, help_text='True if status code >= 400', verbose_name='Is Error')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL, verbose_name='User')),
            ],
            options={
                'verbose_name': 'Request Log',
                'verbose_name_plural': 'Request Logs',
                'ordering': ['-timestamp'],
            },
        ),
        migrations.CreateModel(
            name='PerformanceMetric',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('period_type', models.CharField(choices=[('hour', 'Hour'), ('day', 'Day'), ('week', 'Week')], db_index=True, max_length=10, verbose_name='Period Type')),
                ('period_start', models.DateTimeField(db_index=True, verbose_name='Period Start')),
                ('total_requests', models.IntegerField(default=0, verbose_name='Total Requests')),
                ('error_count', models.IntegerField(default=0, verbose_name='Error Count')),
                ('avg_response_time_ms', models.FloatField(default=0, verbose_name='Average Response Time (ms)')),
                ('p95_response_time_ms', models.FloatField(default=0, verbose_name='P95 Response Time (ms)')),
                ('p99_response_time_ms', models.FloatField(default=0, verbose_name='P99 Response Time (ms)')),
                ('max_response_time_ms', models.FloatField(default=0, verbose_name='Max Response Time (ms)')),
                ('requests_per_second', models.FloatField(default=0, verbose_name='Requests per Second')),
            ],
            options={
                'verbose_name': 'Performance Metric',
                'verbose_name_plural': 'Performance Metrics',
                'ordering': ['-period_start'],
            },
        ),
        migrations.CreateModel(
            name='AlertRule',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(help_text='Descriptive name for this alert rule', max_length=200, verbose_name='Name')),
                ('alert_type', models.CharField(choices=[('error_rate', 'Error Rate'), ('response_time', 'Response Time'), ('memory_usage', 'Memory Usage'), ('cpu_usage', 'CPU Usage'), ('disk_usage', 'Disk Usage'), ('worker_count', 'Worker Count')], max_length=20, verbose_name='Alert Type')),
                ('threshold', models.FloatField(help_text='Threshold value that triggers the alert', verbose_name='Threshold')),
                ('comparison', models.CharField(choices=[('gt', 'Greater Than'), ('gte', 'Greater Than or Equal'), ('lt', 'Less Than'), ('lte', 'Less Than or Equal')], default='gt', max_length=10, verbose_name='Comparison')),
                ('is_active', models.BooleanField(default=True, help_text='Whether this alert rule is active', verbose_name='Active')),
                ('email_enabled', models.BooleanField(default=False, help_text='Send email when alert is triggered', verbose_name='Email Notifications')),
                ('email_recipients', models.TextField(blank=True, help_text='Comma-separated list of email addresses', verbose_name='Email Recipients')),
                ('cooldown_minutes', models.IntegerField(default=60, help_text='Minimum minutes between alerts', verbose_name='Cooldown (Minutes)')),
                ('last_triggered', models.DateTimeField(blank=True, null=True, verbose_name='Last Triggered')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created At')),
            ],
            options={
                'verbose_name': 'Alert Rule',
                'verbose_name_plural': 'Alert Rules',
                'ordering': ['name'],
            },
        ),
        migrations.AddIndex(
            model_name='requestlog',
            index=models.Index(fields=['path', '-timestamp'], name='mgmt_reques_path_ti_idx'),
        ),
        migrations.AddIndex(
            model_name='requestlog',
            index=models.Index(fields=['status_code', '-timestamp'], name='mgmt_reques_status__idx'),
        ),
        migrations.AddIndex(
            model_name='requestlog',
            index=models.Index(fields=['is_error', '-timestamp'], name='mgmt_reques_is_erro_idx'),
        ),
        migrations.AddIndex(
            model_name='requestlog',
            index=models.Index(fields=['-response_time_ms'], name='mgmt_reques_respons_idx'),
        ),
        migrations.AddIndex(
            model_name='performancemetric',
            index=models.Index(fields=['period_type', '-period_start'], name='mgmt_perfor_period__idx'),
        ),
        migrations.AddConstraint(
            model_name='performancemetric',
            constraint=models.UniqueConstraint(fields=['period_type', 'period_start'], name='mgmt_perfor_period_unique'),
        ),
    ]
