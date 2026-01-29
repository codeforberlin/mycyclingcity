# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    admin_performance.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
"""
Admin interfaces for performance tracking and monitoring.
"""

from django.contrib import admin
from django.contrib import messages
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _, gettext
from django.db.models import Count, Avg, Max, Q
from django.utils import timezone
from datetime import timedelta
from mgmt.models import RequestLog, PerformanceMetric, AlertRule
import statistics


@admin.register(RequestLog)
class RequestLogAdmin(admin.ModelAdmin):
    """Admin interface for request logs."""
    list_display = ('timestamp', 'method', 'path_short', 'status_code', 'response_time_display', 'user', 'is_error_display')
    list_filter = ('method', 'status_code', 'is_error', 'timestamp')
    search_fields = ('path', 'ip_address', 'user_agent')
    readonly_fields = ('timestamp',)
    date_hierarchy = 'timestamp'
    ordering = ['-timestamp']
    list_per_page = 50
    
    def has_module_permission(self, request):
        """Verstecke diese Admin-Klasse für Operatoren."""
        if request.user.is_superuser:
            return True
        return False
    
    def path_short(self, obj):
        """Display shortened path."""
        if len(obj.path) > 50:
            return obj.path[:47] + '...'
        return obj.path
    path_short.short_description = _('Path')
    
    def response_time_display(self, obj):
        """Display response time with color coding."""
        color = '#28a745'  # green
        if obj.response_time_ms > 1000:
            color = '#dc3545'  # red
        elif obj.response_time_ms > 500:
            color = '#ffc107'  # yellow
        return mark_safe(f'<span style="color: {color};">{obj.response_time_ms:.0f}ms</span>')
    response_time_display.short_description = _('Response Time')
    
    def is_error_display(self, obj):
        """Display error status."""
        if obj.is_error:
            return mark_safe('<span style="color: #dc3545;">✗ Error</span>')
        return mark_safe('<span style="color: #28a745;">✓ OK</span>')
    is_error_display.short_description = _('Status')
    
    def has_add_permission(self, request):
        """Prevent manual addition of request logs."""
        return False
    
    def has_change_permission(self, request, obj=None):
        """Prevent editing of request logs."""
        return False


def calculate_percentile(values, percentile):
    """Calculate percentile value from a list of numbers."""
    if not values:
        return 0.0
    sorted_values = sorted(values)
    index = int(len(sorted_values) * percentile / 100)
    if index >= len(sorted_values):
        index = len(sorted_values) - 1
    return sorted_values[index]


def generate_performance_metrics(period_type='hour', hours_back=24):
    """
    Generate performance metrics from RequestLog data.
    
    Args:
        period_type: 'hour', 'day', or 'week'
        hours_back: How many hours back to process
    
    Returns:
        Number of metrics created
    """
    from django.db.models import Avg, Count, Max
    
    now = timezone.now()
    start_time = now - timedelta(hours=hours_back)
    
    # Get all request logs in the time range
    request_logs = RequestLog.objects.filter(timestamp__gte=start_time).order_by('timestamp')
    
    if not request_logs.exists():
        return 0
    
    metrics_created = 0
    
    # Group by period
    if period_type == 'hour':
        # Group by hour
        current_period_start = None
        period_logs = []
        
        for log in request_logs:
            log_period_start = log.timestamp.replace(minute=0, second=0, microsecond=0)
            
            if current_period_start is None:
                current_period_start = log_period_start
                period_logs = [log]
            elif log_period_start == current_period_start:
                period_logs.append(log)
            else:
                # Process previous period
                if period_logs:
                    metric = _create_metric_from_logs(period_type, current_period_start, period_logs)
                    if metric:
                        metrics_created += 1
                
                # Start new period
                current_period_start = log_period_start
                period_logs = [log]
        
        # Process last period
        if period_logs and current_period_start:
            metric = _create_metric_from_logs(period_type, current_period_start, period_logs)
            if metric:
                metrics_created += 1
    
    elif period_type == 'day':
        # Group by day
        current_period_start = None
        period_logs = []
        
        for log in request_logs:
            log_period_start = log.timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
            
            if current_period_start is None:
                current_period_start = log_period_start
                period_logs = [log]
            elif log_period_start == current_period_start:
                period_logs.append(log)
            else:
                # Process previous period
                if period_logs:
                    metric = _create_metric_from_logs(period_type, current_period_start, period_logs)
                    if metric:
                        metrics_created += 1
                
                # Start new period
                current_period_start = log_period_start
                period_logs = [log]
        
        # Process last period
        if period_logs and current_period_start:
            metric = _create_metric_from_logs(period_type, current_period_start, period_logs)
            if metric:
                metrics_created += 1
    
    return metrics_created


def _create_metric_from_logs(period_type, period_start, logs):
    """Create a PerformanceMetric from a list of RequestLog objects."""
    if not logs:
        return None
    
    response_times = [log.response_time_ms for log in logs]
    error_count = sum(1 for log in logs if log.is_error)
    total_requests = len(logs)
    
    # Calculate period duration in seconds
    if period_type == 'hour':
        period_duration_seconds = 3600
    elif period_type == 'day':
        period_duration_seconds = 86400
    elif period_type == 'week':
        period_duration_seconds = 604800
    else:
        period_duration_seconds = 3600
    
    # Calculate metrics
    avg_response_time = statistics.mean(response_times) if response_times else 0.0
    p95_response_time = calculate_percentile(response_times, 95)
    p99_response_time = calculate_percentile(response_times, 99)
    max_response_time = max(response_times) if response_times else 0.0
    requests_per_second = total_requests / period_duration_seconds if period_duration_seconds > 0 else 0.0
    
    # Get or create metric (unique_together: period_type, period_start)
    metric, created = PerformanceMetric.objects.get_or_create(
        period_type=period_type,
        period_start=period_start,
        defaults={
            'total_requests': total_requests,
            'error_count': error_count,
            'avg_response_time_ms': avg_response_time,
            'p95_response_time_ms': p95_response_time,
            'p99_response_time_ms': p99_response_time,
            'max_response_time_ms': max_response_time,
            'requests_per_second': requests_per_second,
        }
    )
    
    # Update if already exists
    if not created:
        metric.total_requests = total_requests
        metric.error_count = error_count
        metric.avg_response_time_ms = avg_response_time
        metric.p95_response_time_ms = p95_response_time
        metric.p99_response_time_ms = p99_response_time
        metric.max_response_time_ms = max_response_time
        metric.requests_per_second = requests_per_second
        metric.save()
    
    return metric


@admin.register(PerformanceMetric)
class PerformanceMetricAdmin(admin.ModelAdmin):
    """Admin interface for performance metrics."""
    list_display = ('period_type', 'period_start', 'total_requests', 'error_count', 'avg_response_time_display', 'p95_response_time_display', 'requests_per_second')
    list_filter = ('period_type', 'period_start')
    readonly_fields = ('period_type', 'period_start', 'total_requests', 'error_count', 'avg_response_time_ms', 'p95_response_time_ms', 'p99_response_time_ms', 'max_response_time_ms', 'requests_per_second')
    date_hierarchy = 'period_start'
    ordering = ['-period_start']
    actions = ['generate_hourly_metrics', 'generate_daily_metrics']
    change_list_template = 'admin/mgmt/performancemetric_change_list.html'
    
    def has_module_permission(self, request):
        """Verstecke diese Admin-Klasse für Operatoren."""
        if request.user.is_superuser:
            return True
        return False
    
    def get_urls(self):
        """Add custom URLs for generating metrics."""
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path('generate/hourly/', self.admin_site.admin_view(self.generate_hourly_view), name='mgmt_performancemetric_generate_hourly'),
            path('generate/daily/', self.admin_site.admin_view(self.generate_daily_view), name='mgmt_performancemetric_generate_daily'),
        ]
        return custom_urls + urls
    
    def changelist_view(self, request, extra_context=None):
        """Add context for the changelist template."""
        extra_context = extra_context or {}
        from django.urls import reverse
        extra_context['generate_hourly_url'] = reverse('admin:mgmt_performancemetric_generate_hourly')
        extra_context['generate_daily_url'] = reverse('admin:mgmt_performancemetric_generate_daily')
        return super().changelist_view(request, extra_context)
    
    def generate_hourly_view(self, request):
        """View to generate hourly metrics."""
        from django.shortcuts import redirect
        count = generate_performance_metrics(period_type='hour', hours_back=168)  # Last 7 days
        self.message_user(
            request,
            gettext(f'Successfully generated {count} hourly performance metrics from RequestLog data.'),
            messages.SUCCESS
        )
        return redirect('admin:mgmt_performancemetric_changelist')
    
    def generate_daily_view(self, request):
        """View to generate daily metrics."""
        from django.shortcuts import redirect
        count = generate_performance_metrics(period_type='day', hours_back=720)  # Last 30 days
        self.message_user(
            request,
            gettext(f'Successfully generated {count} daily performance metrics from RequestLog data.'),
            messages.SUCCESS
        )
        return redirect('admin:mgmt_performancemetric_changelist')
    
    def avg_response_time_display(self, obj):
        """Display average response time."""
        return f"{obj.avg_response_time_ms:.0f}ms"
    avg_response_time_display.short_description = _('Avg Response Time')
    
    def p95_response_time_display(self, obj):
        """Display P95 response time."""
        return f"{obj.p95_response_time_ms:.0f}ms"
    p95_response_time_display.short_description = _('P95 Response Time')
    
    def has_add_permission(self, request):
        """Prevent manual addition of metrics."""
        return False
    
    def has_change_permission(self, request, obj=None):
        """Prevent editing of metrics."""
        return False
    
    def generate_hourly_metrics(self, request, queryset):
        """Generate hourly performance metrics from RequestLog data."""
        count = generate_performance_metrics(period_type='hour', hours_back=168)  # Last 7 days
        self.message_user(
            request,
            gettext(f'Successfully generated {count} hourly performance metrics from RequestLog data.'),
            messages.SUCCESS
        )
    generate_hourly_metrics.short_description = _('Generate hourly metrics from RequestLog data')
    
    def generate_daily_metrics(self, request, queryset):
        """Generate daily performance metrics from RequestLog data."""
        count = generate_performance_metrics(period_type='day', hours_back=720)  # Last 30 days
        self.message_user(
            request,
            gettext(f'Successfully generated {count} daily performance metrics from RequestLog data.'),
            messages.SUCCESS
        )
    generate_daily_metrics.short_description = _('Generate daily metrics from RequestLog data')


@admin.register(AlertRule)
class AlertRuleAdmin(admin.ModelAdmin):
    """Admin interface for alert rules."""
    list_display = ('name', 'alert_type', 'threshold_display', 'is_active', 'email_enabled', 'last_triggered')
    list_filter = ('alert_type', 'is_active', 'email_enabled')
    search_fields = ('name',)
    fieldsets = (
        (_('Grundinformationen'), {
            'fields': ('name', 'alert_type', 'is_active')
        }),
        (_('Warnbedingungen'), {
            'fields': ('threshold', 'comparison')
        }),
        (_('Benachrichtigungen'), {
            'fields': ('email_enabled', 'email_recipients', 'cooldown_minutes')
        }),
        (_('Status'), {
            'fields': ('last_triggered', 'created_at'),
            'classes': ('collapse',)
        }),
    )
    readonly_fields = ('last_triggered', 'created_at')
    
    def has_module_permission(self, request):
        """Verstecke diese Admin-Klasse für Operatoren."""
        if request.user.is_superuser:
            return True
        return False
    
    def threshold_display(self, obj):
        """Display threshold with comparison."""
        comparison_symbols = {
            'gt': '>',
            'gte': '≥',
            'lt': '<',
            'lte': '≤',
        }
        symbol = comparison_symbols.get(obj.comparison, '>')
        return f"{symbol} {obj.threshold}"
    threshold_display.short_description = _('Schwellenwert')
