# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    models_performance.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
"""
Models for performance tracking and request analysis.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model

User = get_user_model()


class RequestLog(models.Model):
    """
    Log of HTTP requests for performance analysis.
    
    Stores request information for analysis of slow requests,
    error patterns, and performance bottlenecks.
    """
    METHOD_CHOICES = [
        ('GET', 'GET'),
        ('POST', 'POST'),
        ('PUT', 'PUT'),
        ('DELETE', 'DELETE'),
        ('PATCH', 'PATCH'),
        ('HEAD', 'HEAD'),
        ('OPTIONS', 'OPTIONS'),
    ]
    
    path = models.CharField(
        max_length=500,
        db_index=True,
        verbose_name=_("Path"),
        help_text=_("Request path")
    )
    
    method = models.CharField(
        max_length=10,
        choices=METHOD_CHOICES,
        db_index=True,
        verbose_name=_("Method")
    )
    
    status_code = models.IntegerField(
        db_index=True,
        verbose_name=_("Status-Code")
    )
    
    response_time_ms = models.FloatField(
        verbose_name=_("Response Time (ms)"),
        help_text=_("Response time in milliseconds")
    )
    
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("User")
    )
    
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name=_("IP Address")
    )
    
    user_agent = models.CharField(
        max_length=500,
        blank=True,
        verbose_name=_("User Agent")
    )
    
    timestamp = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name=_("Timestamp")
    )
    
    query_string = models.TextField(
        blank=True,
        verbose_name=_("Query String")
    )
    
    is_error = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name=_("Is Error"),
        help_text=_("True if status code >= 400")
    )
    
    class Meta:
        verbose_name = _("Request Log")
        verbose_name_plural = _("Request Logs")
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['path', '-timestamp']),
            models.Index(fields=['status_code', '-timestamp']),
            models.Index(fields=['is_error', '-timestamp']),
            models.Index(fields=['-response_time_ms']),
        ]
    
    def __str__(self):
        return f"{self.method} {self.path} - {self.status_code} ({self.response_time_ms:.0f}ms)"


class PerformanceMetric(models.Model):
    """
    Aggregated performance metrics for time periods.
    
    Stores aggregated metrics for analysis and reporting.
    """
    PERIOD_CHOICES = [
        ('hour', _('Hour')),
        ('day', _('Day')),
        ('week', _('Week')),
    ]
    
    period_type = models.CharField(
        max_length=10,
        choices=PERIOD_CHOICES,
        db_index=True,
        verbose_name=_("Period Type")
    )
    
    period_start = models.DateTimeField(
        db_index=True,
        verbose_name=_("Period Start")
    )
    
    total_requests = models.IntegerField(
        default=0,
        verbose_name=_("Total Requests")
    )
    
    error_count = models.IntegerField(
        default=0,
        verbose_name=_("Fehleranzahl")
    )
    
    avg_response_time_ms = models.FloatField(
        default=0,
        verbose_name=_("Average Response Time (ms)")
    )
    
    p95_response_time_ms = models.FloatField(
        default=0,
        verbose_name=_("P95 Response Time (ms)")
    )
    
    p99_response_time_ms = models.FloatField(
        default=0,
        verbose_name=_("P99 Response Time (ms)")
    )
    
    max_response_time_ms = models.FloatField(
        default=0,
        verbose_name=_("Max Response Time (ms)")
    )
    
    requests_per_second = models.FloatField(
        default=0,
        verbose_name=_("Requests per Second")
    )
    
    class Meta:
        verbose_name = _("Performance Metric")
        verbose_name_plural = _("Performance Metrics")
        ordering = ['-period_start']
        unique_together = [['period_type', 'period_start']]
        indexes = [
            models.Index(fields=['period_type', '-period_start']),
        ]
    
    def __str__(self):
        return f"{self.period_type} - {self.period_start}: {self.total_requests} requests"


class AlertRule(models.Model):
    """
    Alert rules for monitoring server health and performance.
    
    Defines conditions that trigger alerts when met.
    """
    ALERT_TYPE_CHOICES = [
        ('error_rate', _('Fehlerrate')),
        ('response_time', _('Response Time')),
        ('memory_usage', _('Memory Usage')),
        ('cpu_usage', _('CPU Usage')),
        ('disk_usage', _('Disk Usage')),
        ('worker_count', _('Worker Count')),
    ]
    
    name = models.CharField(
        max_length=200,
        verbose_name=_("Name"),
        help_text=_("Descriptive name for this alert rule")
    )
    
    alert_type = models.CharField(
        max_length=20,
        choices=ALERT_TYPE_CHOICES,
        verbose_name=_("Alert Type")
    )
    
    threshold = models.FloatField(
        verbose_name=_("Threshold"),
        help_text=_("Threshold value that triggers the alert")
    )
    
    comparison = models.CharField(
        max_length=10,
        choices=[
            ('gt', _('Greater Than')),
            ('gte', _('Greater Than or Equal')),
            ('lt', _('Less Than')),
            ('lte', _('Less Than or Equal')),
        ],
        default='gt',
        verbose_name=_("Comparison")
    )
    
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Aktiv"),
        help_text=_("Whether this alert rule is active")
    )
    
    email_enabled = models.BooleanField(
        default=False,
        verbose_name=_("Email Notifications"),
        help_text=_("Send email when alert is triggered")
    )
    
    email_recipients = models.TextField(
        blank=True,
        verbose_name=_("Email Recipients"),
        help_text=_("Comma-separated list of email addresses")
    )
    
    cooldown_minutes = models.IntegerField(
        default=60,
        verbose_name=_("Cooldown (Minutes)"),
        help_text=_("Minimum minutes between alerts")
    )
    
    last_triggered = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Last Triggered")
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Created At")
    )
    
    class Meta:
        verbose_name = _("Alert Rule")
        verbose_name_plural = _("Alert Rules")
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} ({self.get_alert_type_display()})"
