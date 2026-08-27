# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    analytics.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
"""
Analytics and Reporting system for EventHistory and HourlyMetric data.

Provides comprehensive reporting with hierarchy support, visualizations,
and export functionality.
"""

from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render, redirect
from django.http import HttpResponse, JsonResponse
from django.db.models import Sum, Count, Q, F, DecimalField, IntegerField
from django.db.models.functions import TruncHour, TruncDay, TruncDate, TruncWeek, TruncMonth, TruncYear
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.urls import path, reverse
from decimal import Decimal
from datetime import datetime, timedelta, timezone as dt_timezone, timezone as dt_timezone
from typing import Dict, List, Any, Optional
import csv
import json
import logging

logger = logging.getLogger(__name__)

ANALYTICS_TOP_LIST_LIMIT = 100

from api.models import (
    HourlyMetric, Group, Cyclist, CyclistDeviceCurrentMileage, TravelTrack
)
from eventboard.models import EventHistory, Event
from iot.models import Device
from api.velos import VELOS_PER_KM


def _parse_metric_mode(raw: Optional[str]) -> str:
    """Return 'velos' (default) or 'km'."""
    if raw and str(raw).strip().lower() == 'km':
        return 'km'
    return 'velos'


def _hourly_metric_field(metric_mode: str) -> str:
    return 'distance_km' if metric_mode == 'km' else 'velos'


def _sum_output_field(metric_mode: str):
    return DecimalField() if metric_mode == 'km' else IntegerField()


def _event_history_total_to_metric(total_velos, metric_mode: str) -> float:
    """Convert EventHistory aggregate (stored as Velos) to the active metric."""
    velos = int(total_velos or 0)
    if metric_mode == 'km':
        return velos / VELOS_PER_KM
    return float(velos)


def _analytics_group_km_from_ledger(group: Group, group_type: str) -> float:
    """Group km using the same rules as ranking group headers."""
    from api.helpers import group_km_for_ranking_row, _group_km_for_ranking

    if group_type == 'subgroups':
        return _group_km_for_ranking(group)
    return group_km_for_ranking_row(group)


def _analytics_total_km_from_ledger(top_level_groups) -> Decimal:
    """Sum ranking-style km for top-level groups (no double-counting)."""
    total = Decimal('0.00000')
    for group in top_level_groups:
        total += Decimal(str(_analytics_group_km_from_ledger(group, 'top_groups')))
    return total


def _build_top_groups_from_ledger(
    groups_qs,
    group_type: str,
    *,
    limit: int = ANALYTICS_TOP_LIST_LIMIT,
) -> List[Dict[str, Any]]:
    """Build sorted top-group rows from Group.distance_total (ranking-consistent)."""
    top_groups: List[Dict[str, Any]] = []
    for group in groups_qs.select_related('group_type')[:100]:
        group_total = _analytics_group_km_from_ledger(group, group_type)
        if group_total > 0:
            top_groups.append({
                'group_id': group.id,
                'name': group.name,
                'type': group.group_type.name if group.group_type else '',
                'distance': group_total,
            })
    return sorted(top_groups, key=lambda x: x['distance'], reverse=True)[:limit]


def _primary_group_name_for_cyclist(cyclist: Cyclist) -> str:
    primary_group = cyclist.groups.filter(is_visible=True).first()
    if not primary_group:
        primary_group = cyclist.groups.first()
    return primary_group.name if primary_group else _('Keine Gruppe')


def _apply_analytics_cyclist_filters(
    cyclists_qs,
    *,
    use_group_filter: bool,
    group_id: str,
    use_cyclist_filter: bool,
    cyclist_id: str,
    use_event_filter: bool,
    event_id: str,
    use_track_filter: bool,
    track_id: str,
):
    """Apply optional analytics filters to a Cyclist queryset."""
    if use_cyclist_filter and cyclist_id:
        cyclists_qs = cyclists_qs.filter(pk=cyclist_id)
    if use_group_filter and group_id:
        try:
            group = Group.objects.get(pk=group_id)
            descendant_ids = _get_descendant_group_ids(group)
            cyclists_qs = cyclists_qs.filter(groups__id__in=descendant_ids).distinct()
        except Group.DoesNotExist:
            pass
    if use_event_filter and event_id:
        try:
            event = Event.objects.get(pk=event_id)
            group_ids = event.group_statuses.values_list('group_id', flat=True)
            cyclists_qs = cyclists_qs.filter(groups__id__in=group_ids).distinct()
        except Event.DoesNotExist:
            pass
    if use_track_filter and track_id:
        try:
            track = TravelTrack.objects.get(pk=track_id)
            group_ids = track.group_statuses.values_list('group_id', flat=True)
            cyclists_qs = cyclists_qs.filter(groups__id__in=group_ids).distinct()
        except TravelTrack.DoesNotExist:
            pass
    return cyclists_qs


def _build_top_cyclists_from_ledger(
    *,
    use_group_filter: bool,
    group_id: str,
    use_cyclist_filter: bool,
    cyclist_id: str,
    use_event_filter: bool,
    event_id: str,
    use_track_filter: bool,
    track_id: str,
) -> List[Dict[str, Any]]:
    """Top cyclists from Cyclist.distance_total ledger (km mode, ranking-consistent)."""
    cyclists_qs = Cyclist.objects.filter(is_visible=True, distance_total__gt=0)
    cyclists_qs = _apply_analytics_cyclist_filters(
        cyclists_qs,
        use_group_filter=use_group_filter,
        group_id=group_id,
        use_cyclist_filter=use_cyclist_filter,
        cyclist_id=cyclist_id,
        use_event_filter=use_event_filter,
        event_id=event_id,
        use_track_filter=use_track_filter,
        track_id=track_id,
    )
    cyclists_list = list(
        cyclists_qs.prefetch_related('groups').order_by('-distance_total')[:ANALYTICS_TOP_LIST_LIMIT]
    )
    return [
        {
            'cyclist_id': c.id,
            'user_id': c.user_id,
            'id_tag': c.id_tag,
            'group': _primary_group_name_for_cyclist(c),
            'distance': float(c.distance_total or 0),
        }
        for c in cyclists_list
    ]


def _apply_analytics_device_filters(
    devices_qs,
    *,
    use_group_filter: bool,
    group_id: str,
    use_event_filter: bool,
    event_id: str,
    use_track_filter: bool,
    track_id: str,
):
    """Apply optional analytics filters to a Device queryset."""
    if use_group_filter and group_id:
        try:
            group = Group.objects.get(pk=group_id)
            descendant_ids = _get_descendant_group_ids(group)
            devices_qs = devices_qs.filter(group_id__in=descendant_ids)
        except Group.DoesNotExist:
            pass
    if use_event_filter and event_id:
        try:
            event = Event.objects.get(pk=event_id)
            group_ids = list(event.group_statuses.values_list('group_id', flat=True))
            devices_qs = devices_qs.filter(group_id__in=group_ids)
        except Event.DoesNotExist:
            pass
    if use_track_filter and track_id:
        try:
            track = TravelTrack.objects.get(pk=track_id)
            group_ids = list(track.group_statuses.values_list('group_id', flat=True))
            devices_qs = devices_qs.filter(group_id__in=group_ids)
        except TravelTrack.DoesNotExist:
            pass
    return devices_qs


def _build_top_devices_from_ledger(
    *,
    use_group_filter: bool,
    group_id: str,
    use_event_filter: bool,
    event_id: str,
    use_track_filter: bool,
    track_id: str,
) -> List[Dict[str, Any]]:
    """Top devices from Device.distance_lifetime_km ledger (fleet / loan view)."""
    devices_qs = Device.objects.filter(is_visible=True, distance_lifetime_km__gt=0)
    devices_qs = _apply_analytics_device_filters(
        devices_qs,
        use_group_filter=use_group_filter,
        group_id=group_id,
        use_event_filter=use_event_filter,
        event_id=event_id,
        use_track_filter=use_track_filter,
        track_id=track_id,
    )
    return [
        {
            'device_id': d.id,
            'name': d.display_name or d.name,
            'distance': float(d.distance_lifetime_km or 0),
            'distance_period': float(d.distance_total or 0),
        }
        for d in devices_qs.order_by('-distance_lifetime_km')[:ANALYTICS_TOP_LIST_LIMIT]
    ]


def _analytics_params(request):
    """Unified query parameters from GET or POST."""
    if request.method == 'POST':
        return request.POST
    return request.GET


def _resolve_analytics_filter_flags(
    *,
    use_group_filter: bool,
    group_id: str,
    use_cyclist_filter: bool,
    cyclist_id: str,
    use_event_filter: bool,
    event_id: str,
    use_track_filter: bool,
    track_id: str,
) -> Dict[str, str]:
    """
    Apply a dimension filter only when enabled AND a specific entity is selected.

    Checkbox on with dropdown at "All …" must not restrict results (matches ranking view).
    """
    group_id = (group_id or '').strip()
    cyclist_id = (cyclist_id or '').strip()
    event_id = (event_id or '').strip()
    track_id = (track_id or '').strip()
    return {
        'use_group_filter': use_group_filter and bool(group_id),
        'group_id': group_id,
        'use_cyclist_filter': use_cyclist_filter and bool(cyclist_id),
        'cyclist_id': cyclist_id,
        'use_event_filter': use_event_filter and bool(event_id),
        'event_id': event_id,
        'use_track_filter': use_track_filter and bool(track_id),
        'track_id': track_id,
    }


def _fetch_aggregated_analytics(request, group_type: str = 'top_groups') -> Dict[str, Any]:
    """Reuse analytics_data_api aggregation for PDF/summary exports."""
    from django.test import RequestFactory

    params = _analytics_params(request).copy()
    params['report_type'] = 'aggregated'
    params['group_type'] = group_type
    params.setdefault('use_group_filter', 'false')
    params.setdefault('use_cyclist_filter', 'false')
    params.setdefault('use_event_filter', 'false')
    params.setdefault('use_track_filter', 'false')
    params.setdefault('metric_mode', 'velos')

    internal_request = RequestFactory().get('/admin/analytics/data/', params)
    internal_request.user = request.user
    response = analytics_data_api(internal_request)
    if response.status_code != 200:
        raise ValueError('Analytics aggregation failed')
    payload = json.loads(response.content)
    aggregated = payload.get('aggregated')
    if not aggregated:
        raise ValueError('Analytics aggregation returned no data')
    return aggregated


def _build_export_meta(request, start_date: str, end_date: str, metric_mode: str) -> Dict[str, Any]:
    """Build human-readable metadata for export files."""
    params = _analytics_params(request)
    filters: List[str] = []
    use_event = params.get('use_event_filter', 'false').lower() == 'true'
    use_group = params.get('use_group_filter', 'true').lower() == 'true'
    use_cyclist = params.get('use_cyclist_filter', 'true').lower() == 'true'
    use_track = params.get('use_track_filter', 'false').lower() == 'true'

    if use_event and params.get('event_id'):
        try:
            event = Event.objects.get(pk=params['event_id'])
            filters.append(f"{_('Event')}: {event.name}")
        except Event.DoesNotExist:
            pass
    if use_group and params.get('group_id'):
        try:
            group = Group.objects.get(pk=params['group_id'])
            filters.append(f"{_('Gruppe')}: {group.name}")
        except Group.DoesNotExist:
            pass
    if use_cyclist and params.get('cyclist_id'):
        try:
            cyclist = Cyclist.objects.get(pk=params['cyclist_id'])
            filters.append(f"{_('Radler')}: {cyclist.user_id}")
        except Cyclist.DoesNotExist:
            pass
    if use_track and params.get('track_id'):
        try:
            track = TravelTrack.objects.get(pk=params['track_id'])
            filters.append(f"{_('Strecke')}: {track.name}")
        except TravelTrack.DoesNotExist:
            pass

    group_type = params.get('group_type', 'top_groups')
    return {
        'start_date': start_date,
        'end_date': end_date,
        'metric_mode': metric_mode,
        'generated_at_display': timezone.localtime(timezone.now()).strftime('%d.%m.%Y %H:%M'),
        'filters': filters,
        'group_type_label': _('TOP-Gruppen') if group_type == 'top_groups' else _('Leaf-Gruppen'),
    }


# Analytics views as standalone functions
@staff_member_required
def analytics_dashboard(request):
    """Main analytics dashboard view."""
    # Block access for operators
    if not request.user.is_superuser:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden(_("Zugriff verweigert. Nur System-Administratoren haben Zugriff auf diese Funktion."))
    # Get date range from request
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    event_id = request.GET.get('event_id')
    group_id = request.GET.get('group_id')
    cyclist_id = request.GET.get('cyclist_id')
    
    # Default to last 30 days if not specified
    if not start_date:
        start_date = (timezone.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    if not end_date:
        end_date = timezone.now().strftime('%Y-%m-%d')
    
    # Parse dates
    try:
        start_dt = timezone.make_aware(datetime.strptime(start_date, '%Y-%m-%d'))
        end_dt = timezone.make_aware(datetime.strptime(end_date, '%Y-%m-%d').replace(
            hour=23, minute=59, second=59
        ))
    except ValueError:
        start_dt = timezone.now() - timedelta(days=30)
        end_dt = timezone.now()
    
    context = {
        'title': _('Historical Reports & Analytics'),
        'start_date': start_date,
        'end_date': end_date,
        'event_id': event_id,
        'group_id': group_id,
        'cyclist_id': cyclist_id,
        'track_id': request.GET.get('track_id'),
        'use_event_filter': request.GET.get('use_event_filter', 'false') == 'true',
        'use_group_filter': request.GET.get('use_group_filter', 'false') == 'true',
        'use_cyclist_filter': request.GET.get('use_cyclist_filter', 'false') == 'true',
        'use_track_filter': request.GET.get('use_track_filter', 'false') == 'true',
        'events': Event.objects.all().order_by('-start_time'),
        'groups': Group.objects.filter(is_visible=True).order_by('name'),
        'cyclists': Cyclist.objects.filter(is_visible=True).order_by('user_id'),
        'tracks': TravelTrack.objects.filter(is_active=True).order_by('name'),
        'metric_mode': _parse_metric_mode(request.GET.get('metric_mode')),
    }
    
    return render(request, 'admin/api/analytics_dashboard.html', context)


@staff_member_required
def analytics_data_api(request):
    """API endpoint for chart data and aggregated statistics."""
    # Block access for operators
    if not request.user.is_superuser:
        return JsonResponse({'error': _("Zugriff verweigert")}, status=403)
    start_date = request.GET.get('start_date', '').strip()
    end_date = request.GET.get('end_date', '').strip()
    event_id = request.GET.get('event_id', '').strip()
    group_id = request.GET.get('group_id', '').strip()
    cyclist_id = request.GET.get('cyclist_id', '').strip()
    track_id = request.GET.get('track_id', '').strip()
    use_event_filter = request.GET.get('use_event_filter', 'false').strip().lower() == 'true'
    use_group_filter = request.GET.get('use_group_filter', 'false').strip().lower() == 'true'
    use_cyclist_filter = request.GET.get('use_cyclist_filter', 'false').strip().lower() == 'true'
    use_track_filter = request.GET.get('use_track_filter', 'false').strip().lower() == 'true'
    report_type = request.GET.get('report_type', 'hourly')  # hourly, daily, aggregated
    group_type = request.GET.get('group_type', 'top_groups')  # top_groups or subgroups
    metric_mode = _parse_metric_mode(request.GET.get('metric_mode'))
    metric_field = _hourly_metric_field(metric_mode)
    sum_output_field = _sum_output_field(metric_mode)

    resolved_filters = _resolve_analytics_filter_flags(
        use_group_filter=use_group_filter,
        group_id=group_id,
        use_cyclist_filter=use_cyclist_filter,
        cyclist_id=cyclist_id,
        use_event_filter=use_event_filter,
        event_id=event_id,
        use_track_filter=use_track_filter,
        track_id=track_id,
    )
    use_group_filter = resolved_filters['use_group_filter']
    group_id = resolved_filters['group_id']
    use_cyclist_filter = resolved_filters['use_cyclist_filter']
    cyclist_id = resolved_filters['cyclist_id']
    use_event_filter = resolved_filters['use_event_filter']
    event_id = resolved_filters['event_id']
    use_track_filter = resolved_filters['use_track_filter']
    track_id = resolved_filters['track_id']
    
    # Parse dates with fallback to default range
    if not start_date or not end_date:
        start_dt = timezone.now() - timedelta(days=30)
        end_dt = timezone.now()
    else:
        try:
            start_dt = timezone.make_aware(datetime.strptime(start_date, '%Y-%m-%d'))
            end_dt = timezone.make_aware(datetime.strptime(end_date, '%Y-%m-%d').replace(
                hour=23, minute=59, second=59
            ))
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid date format: {e}, using default range")
            start_dt = timezone.now() - timedelta(days=30)
            end_dt = timezone.now()
    
    filter_kwargs = {
        'use_event_filter': use_event_filter,
        'event_id': event_id,
        'use_group_filter': use_group_filter,
        'group_id': group_id,
        'use_cyclist_filter': use_cyclist_filter,
        'cyclist_id': cyclist_id,
        'use_track_filter': use_track_filter,
        'track_id': track_id,
    }

    # Build base queryset with optimized queries (always scoped to the selected date range)
    metrics_qs = _build_filtered_hourly_metrics_qs(
        start_dt,
        end_dt,
        select_related=True,
        **filter_kwargs,
    )
    
    response_data = {'metric_mode': metric_mode}
    
    if report_type == 'hourly':
        # Hourly utilization data
        hourly_data = metrics_qs.annotate(
            hour=TruncHour('timestamp')
        ).values('hour').annotate(
            total_value=Sum(metric_field, output_field=sum_output_field)
        ).order_by('hour')
        
        response_data['hourly'] = {
            'labels': [item['hour'].strftime('%Y-%m-%d %H:00') if item.get('hour') else '' for item in hourly_data],
            'data': [float(item.get('total_value') or 0) for item in hourly_data],
        }
    
    elif report_type == 'daily':
        # Daily utilization data
        daily_data = metrics_qs.annotate(
            day=TruncDate('timestamp')
        ).values('day').annotate(
            total_value=Sum(metric_field, output_field=sum_output_field)
        ).order_by('day')
        
        response_data['daily'] = {
            'labels': [item['day'].strftime('%Y-%m-%d') if item.get('day') else '' for item in daily_data],
            'data': [float(item.get('total_value') or 0) for item in daily_data],
        }

    elif report_type == 'daily_by_group':
        from mgmt.analytics_charts import build_timeseries_by_group

        response_data['daily_by_group'] = build_timeseries_by_group(
            metrics_qs,
            period_annotation={'day': TruncDate('timestamp')},
            period_key='day',
            period_label_fmt=lambda dt: dt.strftime('%Y-%m-%d'),
            group_type=group_type,
            metric_field=metric_field,
            sum_output_field=sum_output_field,
        )

    elif report_type == 'hourly_by_group':
        from mgmt.analytics_charts import build_timeseries_by_group

        response_data['hourly_by_group'] = build_timeseries_by_group(
            metrics_qs,
            period_annotation={'hour': TruncHour('timestamp')},
            period_key='hour',
            period_label_fmt=lambda dt: dt.strftime('%Y-%m-%d %H:00'),
            group_type=group_type,
            metric_field=metric_field,
            sum_output_field=sum_output_field,
        )
    
    elif report_type == 'aggregated':
        # Aggregated stats: Velos from HourlyMetric (date range); group km from ledger (ranking).
        # Get all visible groups (with filters applied)
        all_visible_groups = Group.objects.filter(is_visible=True)
        
        # Apply filters if enabled
        if use_group_filter and group_id:
            try:
                group = Group.objects.get(pk=group_id)
                descendant_ids = _get_descendant_group_ids(group)
                all_visible_groups = all_visible_groups.filter(id__in=descendant_ids)
            except Group.DoesNotExist:
                pass
        
        if use_event_filter and event_id:
            try:
                event = Event.objects.get(pk=event_id)
                group_ids = event.group_statuses.values_list('group_id', flat=True)
                all_visible_groups = all_visible_groups.filter(id__in=group_ids)
            except Event.DoesNotExist:
                pass
        
        if use_track_filter and track_id:
            try:
                track = TravelTrack.objects.get(pk=track_id)
                group_ids = track.group_statuses.values_list('group_id', flat=True)
                all_visible_groups = all_visible_groups.filter(id__in=group_ids)
            except TravelTrack.DoesNotExist:
                pass
        
        now = timezone.now()

        groups_qs = Group.objects.filter(is_visible=True)
        if use_group_filter and group_id:
            try:
                group = Group.objects.get(pk=group_id)
                descendant_ids = _get_descendant_group_ids(group)
                groups_qs = groups_qs.filter(id__in=descendant_ids)
            except Group.DoesNotExist:
                pass
        if use_event_filter and event_id:
            try:
                event = Event.objects.get(pk=event_id)
                group_ids = event.group_statuses.values_list('group_id', flat=True)
                groups_qs = groups_qs.filter(id__in=group_ids)
            except Event.DoesNotExist:
                pass
        if use_track_filter and track_id:
            try:
                track = TravelTrack.objects.get(pk=track_id)
                group_ids = track.group_statuses.values_list('group_id', flat=True)
                groups_qs = groups_qs.filter(id__in=group_ids)
            except TravelTrack.DoesNotExist:
                pass

        groups_table_qs = _filter_groups_for_analytics_table(groups_qs, group_type)

        if metric_mode == 'km':
            # Group km: ledger (Group.distance_total), same as ranking — not HourlyMetric sums.
            top_level_groups = all_visible_groups.filter(parent__isnull=True)
            total_distance = _analytics_total_km_from_ledger(top_level_groups)
            top_groups = _build_top_groups_from_ledger(groups_table_qs, group_type)
        else:
            # Velos totals from HourlyMetric in the selected date range.
            groups_list = list(all_visible_groups.select_related('parent', 'group_type'))
            total_metrics_qs = _build_filtered_hourly_metrics_qs(
                start_dt,
                end_dt,
                require_group_at_time=True,
                **filter_kwargs,
            )
            group_totals_from_metrics = total_metrics_qs.values('group_at_time_id').annotate(
                total=Sum(metric_field, output_field=sum_output_field)
            )
            group_total_dict = {
                item['group_at_time_id']: float(item['total'] or 0.0)
                for item in group_totals_from_metrics
            }

            processed_groups = set()
            max_iterations = 10
            iteration = 0
            while iteration < max_iterations:
                iteration += 1
                changed = False
                groups_to_process = [
                    gid for gid in group_total_dict.keys() if gid not in processed_groups
                ]
                for group_id_val in groups_to_process:
                    try:
                        group = Group.objects.get(id=group_id_val)
                        if group.parent and group.parent.id in [g.id for g in groups_list]:
                            parent_id = group.parent.id
                            if parent_id not in group_total_dict:
                                group_total_dict[parent_id] = 0.0
                            group_total_dict[parent_id] += group_total_dict[group_id_val]
                            processed_groups.add(group_id_val)
                            changed = True
                    except Group.DoesNotExist:
                        processed_groups.add(group_id_val)
                if not changed:
                    break

            top_level_groups = all_visible_groups.filter(parent__isnull=True)
            total_distance = Decimal('0.00000')
            for group in top_level_groups:
                if group.id in group_total_dict:
                    total_distance += Decimal(str(group_total_dict[group.id]))

            if use_event_filter and event_id:
                try:
                    event = Event.objects.get(pk=event_id)
                    event_history_qs = EventHistory.objects.filter(
                        event=event,
                        end_time__gte=start_dt,
                        end_time__lte=end_dt,
                    )
                    if use_group_filter and group_id:
                        try:
                            group = Group.objects.get(pk=group_id)
                            descendant_ids = _get_descendant_group_ids(group)
                            event_history_qs = event_history_qs.filter(group_id__in=descendant_ids)
                        except Group.DoesNotExist:
                            pass
                    event_history_total_raw = event_history_qs.aggregate(
                        total=Sum('total_velos', output_field=IntegerField())
                    )['total'] or 0
                    total_distance += Decimal(str(
                        _event_history_total_to_metric(event_history_total_raw, metric_mode)
                    ))
                except Event.DoesNotExist:
                    pass

            top_groups = []
            for g in groups_table_qs.select_related('group_type')[:100]:
                group_total = group_total_dict.get(g.id, 0.0)
                if group_total > 0:
                    top_groups.append({
                        'group_id': g.id,
                        'name': g.name,
                        'type': g.group_type.name if g.group_type else '',
                        'distance': group_total,
                    })
            top_groups = sorted(top_groups, key=lambda x: x['distance'], reverse=True)[:ANALYTICS_TOP_LIST_LIMIT]

            if use_event_filter and event_id:
                try:
                    event = Event.objects.get(pk=event_id)
                    event_history_qs = EventHistory.objects.filter(
                        event=event,
                        end_time__gte=start_dt,
                        end_time__lte=end_dt,
                    ).select_related('group')
                    if use_group_filter and group_id:
                        try:
                            group = Group.objects.get(pk=group_id)
                            descendant_ids = _get_descendant_group_ids(group)
                            event_history_qs = event_history_qs.filter(group_id__in=descendant_ids)
                        except Group.DoesNotExist:
                            pass

                    event_groups = list(event_history_qs.values(
                        'group_id', 'group__name', 'group__group_type__name',
                    ).annotate(
                        total_distance=Sum('total_velos', output_field=IntegerField())
                    ).order_by('-total_distance'))

                    allowed_group_ids = set(
                        _filter_groups_for_analytics_table(
                            Group.objects.filter(id__in=[row['group_id'] for row in event_groups]),
                            group_type,
                        ).values_list('id', flat=True)
                    )

                    group_dict = {}
                    for item in top_groups:
                        key = (item.get('name'), item.get('type'))
                        if key[0]:
                            group_dict[key] = item.get('distance', 0)

                    for item in event_groups:
                        if item.get('group_id') not in allowed_group_ids:
                            continue
                        group_type_name = item.get('group__group_type__name') or ''
                        key = (item.get('group__name'), group_type_name)
                        if key[0]:
                            event_distance = _event_history_total_to_metric(
                                item.get('total_distance'), metric_mode
                            )
                            if key in group_dict:
                                group_dict[key] += event_distance
                            else:
                                group_dict[key] = event_distance

                    top_groups = [
                        {
                            'name': name,
                            'type': gtype or '',
                            'distance': distance,
                        }
                        for (name, gtype), distance in sorted(
                            group_dict.items(), key=lambda x: x[1], reverse=True
                        )[:ANALYTICS_TOP_LIST_LIMIT]
                    ]
                except Event.DoesNotExist:
                    pass
        
        # Top cyclists and devices — km: ledger; velos: HourlyMetric in date range.
        ledger_filter_kwargs = {
            'use_group_filter': use_group_filter,
            'group_id': group_id,
            'use_cyclist_filter': use_cyclist_filter,
            'cyclist_id': cyclist_id,
            'use_event_filter': use_event_filter,
            'event_id': event_id,
            'use_track_filter': use_track_filter,
            'track_id': track_id,
        }
        if metric_mode == 'km':
            top_cyclists = _build_top_cyclists_from_ledger(**ledger_filter_kwargs)
            top_devices = _build_top_devices_from_ledger(
                use_group_filter=use_group_filter,
                group_id=group_id,
                use_event_filter=use_event_filter,
                event_id=event_id,
                use_track_filter=use_track_filter,
                track_id=track_id,
            )
        else:
            top_cyclists_qs = metrics_qs.filter(cyclist__isnull=False).values(
                'cyclist__user_id', 'cyclist__id_tag', 'cyclist_id'
            ).annotate(
                total_distance=Sum(metric_field, output_field=sum_output_field)
            ).order_by('-total_distance')[:ANALYTICS_TOP_LIST_LIMIT]

            cyclist_ids = [
                item.get('cyclist_id') for item in top_cyclists_qs if item.get('cyclist_id')
            ]
            cyclists_with_groups = {}
            if cyclist_ids:
                from django.db.models import Prefetch
                cyclists = Cyclist.objects.filter(id__in=cyclist_ids).prefetch_related('groups')
                for cyclist in cyclists:
                    cyclists_with_groups[cyclist.id] = _primary_group_name_for_cyclist(cyclist)

            top_cyclists = [
                {
                    'cyclist_id': item.get('cyclist_id'),
                    'user_id': item.get('cyclist__user_id') or '',
                    'id_tag': item.get('cyclist__id_tag') or '',
                    'group': cyclists_with_groups.get(item.get('cyclist_id'), _('Unknown')),
                    'distance': float(item.get('total_distance') or 0),
                }
                for item in top_cyclists_qs
            ]

            top_devices_qs = metrics_qs.values(
                'device_id', 'device__name', 'device__display_name'
            ).annotate(
                total_distance=Sum(metric_field, output_field=sum_output_field)
            ).order_by('-total_distance')[:ANALYTICS_TOP_LIST_LIMIT]

            top_devices = [
                {
                    'device_id': item.get('device_id'),
                    'name': item.get('device__display_name') or item.get('device__name') or '',
                    'distance': float(item.get('total_distance') or 0),
                }
                for item in top_devices_qs
            ]
        
        # Period tiles: current (leaderboard-aligned) + historical peak.
        now = timezone.now()

        filtered_group_ids = None
        if use_group_filter and group_id:
            try:
                filtered_group = Group.objects.get(pk=group_id)
                filtered_group_ids = set(_get_descendant_group_ids(filtered_group))
            except Group.DoesNotExist:
                pass

        filter_kwargs_common = dict(
            use_event_filter=use_event_filter,
            event_id=event_id,
            use_group_filter=use_group_filter,
            group_id=group_id,
            use_cyclist_filter=use_cyclist_filter,
            cyclist_id=cyclist_id,
            use_track_filter=use_track_filter,
            track_id=track_id,
        )

        current_periods = _compute_current_period_tiles(
            group_type=group_type,
            metric_mode=metric_mode,
            now=now,
            **filter_kwargs_common,
        )

        if metric_mode == 'km':
            yearly_holder, yearly_value, yearly_total = _compute_yearly_record_from_ledger(
                group_type=group_type,
                use_group_filter=use_group_filter,
                group_id=group_id,
                use_event_filter=use_event_filter,
                event_id=event_id,
                use_track_filter=use_track_filter,
                track_id=track_id,
            )
            current_periods['yearly'] = {
                'holder': yearly_holder,
                'value': yearly_value,
                'total': yearly_total,
            }
            yearly_km_source = 'ledger'
        else:
            yearly_km_source = 'hourly_metric'

        peak_metrics = _apply_analytics_metric_filters(
            HourlyMetric.objects.all(),
            **filter_kwargs_common,
        )

        daily_peak_holder, daily_peak_value, daily_peak_period, _daily_peak_total = (
            _compute_historical_peak_period(
                peak_metrics,
                trunc_func=TruncDate,
                trunc_kind='day',
                metric_field=metric_field,
                sum_output_field=sum_output_field,
                group_type=group_type,
                filtered_group_ids=filtered_group_ids,
            )
        )

        weekly_peak_holder, weekly_peak_value, weekly_peak_period, _weekly_peak_total = (
            _compute_historical_peak_period(
                peak_metrics,
                trunc_func=TruncWeek,
                trunc_kind='week',
                metric_field=metric_field,
                sum_output_field=sum_output_field,
                group_type=group_type,
                filtered_group_ids=filtered_group_ids,
            )
        )

        monthly_peak_holder, monthly_peak_value, monthly_peak_period, _monthly_peak_total = (
            _compute_historical_peak_period(
                peak_metrics,
                trunc_func=TruncMonth,
                trunc_kind='month',
                metric_field=metric_field,
                sum_output_field=sum_output_field,
                group_type=group_type,
                filtered_group_ids=filtered_group_ids,
            )
        )

        yearly_peak_holder, yearly_peak_value, yearly_peak_period, _yearly_peak_total = (
            _compute_historical_peak_period(
                peak_metrics,
                trunc_func=TruncYear,
                trunc_kind='year',
                metric_field=metric_field,
                sum_output_field=sum_output_field,
                group_type=group_type,
                filtered_group_ids=filtered_group_ids,
            )
        )

        daily_current = current_periods['daily']
        weekly_current = current_periods['weekly']
        monthly_current = current_periods['monthly']
        yearly_current = current_periods['yearly']

        response_data['aggregated'] = {
            'metric_mode': metric_mode,
            'group_km_source': 'ledger' if metric_mode == 'km' else 'hourly_metric',
            'cyclist_km_source': 'ledger' if metric_mode == 'km' else 'hourly_metric',
            'device_km_source': 'ledger' if metric_mode == 'km' else 'hourly_metric',
            'yearly_km_source': yearly_km_source,
            'total_distance': float(total_distance),
            'daily_total': float(daily_current['total']),
            'weekly_total': float(weekly_current['total']),
            'monthly_total': float(monthly_current['total']),
            'yearly_total': float(yearly_current['total']),
            'daily_current_holder': daily_current['holder'],
            'daily_current_value': float(daily_current['value']),
            'weekly_current_holder': weekly_current['holder'],
            'weekly_current_value': float(weekly_current['value']),
            'monthly_current_holder': monthly_current['holder'],
            'monthly_current_value': float(monthly_current['value']),
            'yearly_current_holder': yearly_current['holder'],
            'yearly_current_value': float(yearly_current['value']),
            'daily_peak_holder': daily_peak_holder,
            'daily_peak_value': float(daily_peak_value),
            'daily_peak_period': daily_peak_period,
            'weekly_peak_holder': weekly_peak_holder,
            'weekly_peak_value': float(weekly_peak_value),
            'weekly_peak_period': weekly_peak_period,
            'monthly_peak_holder': monthly_peak_holder,
            'monthly_peak_value': float(monthly_peak_value),
            'monthly_peak_period': monthly_peak_period,
            'yearly_peak_holder': yearly_peak_holder,
            'yearly_peak_value': float(yearly_peak_value),
            'yearly_peak_period': yearly_peak_period,
            # Backward-compatible aliases (peak = historical record).
            'daily_record_holder': daily_peak_holder,
            'daily_record_value': float(daily_peak_value),
            'daily_record_date': daily_peak_period,
            'weekly_record_holder': weekly_peak_holder,
            'weekly_record_value': float(weekly_peak_value),
            'monthly_record_holder': monthly_peak_holder,
            'monthly_record_value': float(monthly_peak_value),
            'yearly_record_holder': yearly_peak_holder,
            'yearly_record_value': float(yearly_peak_value),
            'top_groups': top_groups,
            'top_cyclists': top_cyclists,
            'top_devices': top_devices,
        }
    
    return JsonResponse(response_data)


@staff_member_required
def export_data(request):
    """Export filtered data as CSV, Excel, or PDF summary report."""
    # Block access for operators
    if not request.user.is_superuser:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden(_("Zugriff verweigert. Nur System-Administratoren haben Zugriff auf diese Funktion."))
    params = _analytics_params(request)
    start_date = params.get('start_date')
    end_date = params.get('end_date')
    event_id = params.get('event_id')
    group_id = params.get('group_id')
    cyclist_id = params.get('cyclist_id')
    export_format = params.get('format', 'csv')  # csv, excel, or pdf
    metric_mode = _parse_metric_mode(params.get('metric_mode'))
    value_column = _('Distance (km)') if metric_mode == 'km' else _('Velos')

    if export_format == 'pdf':
        try:
            from mgmt.analytics_pdf import build_analytics_pdf, _decode_chart_image

            group_type = params.get('group_type', 'top_groups')
            aggregated = _fetch_aggregated_analytics(request, group_type=group_type)
            meta = _build_export_meta(request, start_date or '', end_date or '', metric_mode)
            chart_images = {
                'daily': _decode_chart_image(params.get('daily_chart_image', '')),
                'hourly': _decode_chart_image(params.get('hourly_chart_image', '')),
            }
            pdf_bytes = build_analytics_pdf(aggregated, meta, chart_images=chart_images)
            response = HttpResponse(pdf_bytes, content_type='application/pdf')
            safe_start = (start_date or 'start').replace('/', '-')
            safe_end = (end_date or 'end').replace('/', '-')
            filename = f'analytics_report_{safe_start}_to_{safe_end}.pdf'
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response
        except ImportError:
            return HttpResponse(
                _('PDF-Export nicht verfügbar: reportlab ist nicht installiert.'),
                status=503,
                content_type='text/plain; charset=utf-8',
            )
        except ValueError as exc:
            logger.exception('Analytics PDF export failed: %s', exc)
            return HttpResponse(
                _('PDF-Export fehlgeschlagen.'),
                status=500,
                content_type='text/plain; charset=utf-8',
            )
    
    # Parse dates
    try:
        start_dt = timezone.make_aware(datetime.strptime(start_date, '%Y-%m-%d'))
        end_dt = timezone.make_aware(datetime.strptime(end_date, '%Y-%m-%d').replace(
            hour=23, minute=59, second=59
        ))
    except (ValueError, TypeError):
        start_dt = timezone.now() - timedelta(days=30)
        end_dt = timezone.now()
    
    # Build queryset
    metrics_qs = HourlyMetric.objects.filter(
        timestamp__gte=start_dt,
        timestamp__lte=end_dt
    ).select_related('device', 'cyclist', 'group_at_time')
    
    # Apply filters
    if event_id:
        try:
            event = Event.objects.get(pk=event_id)
            group_ids = event.group_statuses.values_list('group_id', flat=True)
            metrics_qs = metrics_qs.filter(group_at_time_id__in=group_ids)
        except Event.DoesNotExist:
            pass
    
    if group_id:
        try:
            group = Group.objects.get(pk=group_id)
            descendant_ids = _get_descendant_group_ids(group)
            metrics_qs = metrics_qs.filter(group_at_time_id__in=descendant_ids)
        except Group.DoesNotExist:
            pass
    
    if cyclist_id:
        metrics_qs = metrics_qs.filter(cyclist_id=cyclist_id)
    
    # Order by timestamp
    metrics_qs = metrics_qs.order_by('timestamp')
    
    if export_format == 'excel':
        # Excel export using openpyxl (if available)
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Font, Alignment
            
            wb = Workbook()
            ws = wb.active
            ws.title = "Mileage Data"
            
            # Headers
            headers = [
                'Timestamp', 'Cyclist', 'ID Tag', 'Device', 'Group',
                'Group Type', str(value_column),
            ]
            ws.append(headers)
            
            # Style headers
            for cell in ws[1]:
                cell.font = Font(bold=True)
                cell.alignment = Alignment(horizontal='center')
            
            # Data rows
            for metric in metrics_qs:
                metric_value = (
                    float(metric.distance_km)
                    if metric_mode == 'km'
                    else int(metric.velos or 0)
                )
                ws.append([
                    metric.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                    metric.cyclist.user_id if metric.cyclist else '',
                    metric.cyclist.id_tag if metric.cyclist else '',
                    metric.device.display_name or metric.device.name,
                    metric.group_at_time.name if metric.group_at_time else '',
                    metric.group_at_time.group_type.name if metric.group_at_time and metric.group_at_time.group_type else '',
                    metric_value,
                ])
            
            # Create response
            response = HttpResponse(
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            filename = f'mileage_report_{start_date}_to_{end_date}.xlsx'
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            wb.save(response)
            return response
            
        except ImportError:
            # Fallback to CSV if openpyxl not available
            export_format = 'csv'
    
    if export_format == 'csv':
        # CSV export for German Excel (semicolon delimiter, comma decimal)
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        filename = f'mileage_report_{start_date}_to_{end_date}.csv'
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        # Use semicolon delimiter for German Excel compatibility
        writer = csv.writer(response, delimiter=';')
        writer.writerow([
            'Timestamp', 'Cyclist', 'ID Tag', 'Device', 'Group',
            'Group Type', str(value_column),
        ])
        
        for metric in metrics_qs:
            if metric_mode == 'km':
                value_str = str(float(metric.distance_km)).replace('.', ',')
            else:
                value_str = str(int(metric.velos or 0))
            writer.writerow([
                metric.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                metric.cyclist.user_id if metric.cyclist else '',
                metric.cyclist.id_tag if metric.cyclist else '',
                metric.device.display_name or metric.device.name,
                metric.group_at_time.name if metric.group_at_time else '',
                metric.group_at_time.group_type.name if metric.group_at_time and metric.group_at_time.group_type else '',
                value_str,
            ])
        
        return response


@staff_member_required
def hierarchy_breakdown(request):
    """Hierarchy breakdown view with drill-down capability."""
    # Block access for operators
    if not request.user.is_superuser:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden(_("Zugriff verweigert. Nur System-Administratoren haben Zugriff auf diese Funktion."))
    event_id = request.GET.get('event_id')
    parent_group_id = request.GET.get('parent_group_id')
    group_id = request.GET.get('group_id')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    # Parse dates
    try:
        start_dt = timezone.make_aware(datetime.strptime(start_date, '%Y-%m-%d'))
        end_dt = timezone.make_aware(datetime.strptime(end_date, '%Y-%m-%d').replace(
            hour=23, minute=59, second=59
        ))
    except (ValueError, TypeError):
        start_dt = timezone.now() - timedelta(days=30)
        end_dt = timezone.now()
    
    context = {
        'title': _('Hierarchy Breakdown'),
        'start_date': start_date or (timezone.now() - timedelta(days=30)).strftime('%Y-%m-%d'),
        'end_date': end_date or timezone.now().strftime('%Y-%m-%d'),
        'event_id': event_id,
        'parent_group_id': parent_group_id,
        'group_id': group_id,
        'events': Event.objects.all().order_by('-start_time'),
    }
    
    # Get breakdown data
    if event_id:
        try:
            event = Event.objects.get(pk=event_id)
            context['event'] = event
        except Event.DoesNotExist:
            context['error'] = _('Event not found')
            return render(request, 'admin/api/hierarchy_breakdown.html', context)
        
        # Get top-level groups (parent groups)
        if not parent_group_id and not group_id:
            # Show parent groups - use EventHistory for event-based data
            parent_groups = Group.objects.filter(
                parent__isnull=True,
                is_visible=True
            ).annotate(
                total_distance=Sum(
                    'event_history__total_velos',
                    filter=Q(
                        event_history__event=event,
                        event_history__end_time__gte=start_dt,
                        event_history__end_time__lte=end_dt
                    ),
                    output_field=IntegerField()
                )
            ).filter(total_distance__gt=0).order_by('-total_distance')
            
            context['breakdown_type'] = 'parent_groups'
            context['parent_groups'] = parent_groups
        
        elif parent_group_id and not group_id:
            # Show child groups of parent
            try:
                parent_group = Group.objects.get(pk=parent_group_id)
            except Group.DoesNotExist:
                context['error'] = _('Parent group not found')
                return render(request, 'admin/api/hierarchy_breakdown.html', context)
            
            child_groups = Group.objects.filter(
                parent=parent_group,
                is_visible=True
            ).annotate(
                total_distance=Sum(
                    'event_history__total_velos',
                    filter=Q(
                        event_history__event=event,
                        event_history__end_time__gte=start_dt,
                        event_history__end_time__lte=end_dt
                    ),
                    output_field=IntegerField()
                )
            ).filter(total_distance__gt=0).order_by('-total_distance')
            
            context['breakdown_type'] = 'child_groups'
            context['parent_group'] = parent_group
            context['child_groups'] = child_groups
        
        elif group_id:
            # Show cyclists in group - use HourlyMetric for accurate data
            try:
                group = Group.objects.get(pk=group_id)
            except Group.DoesNotExist:
                context['error'] = _('Group not found')
                return render(request, 'admin/api/hierarchy_breakdown.html', context)
            # Get all descendant groups to include all cyclists
            descendant_ids = _get_descendant_group_ids(group)
            
            cyclists = Cyclist.objects.filter(
                groups__id__in=descendant_ids,
                is_visible=True
            ).annotate(
                total_distance=Sum(
                    'metrics__distance_km',
                    filter=Q(
                        metrics__group_at_time_id__in=descendant_ids,
                        metrics__timestamp__gte=start_dt,
                        metrics__timestamp__lte=end_dt
                    ),
                    output_field=DecimalField()
                )
            ).filter(total_distance__gt=0).distinct().order_by('-total_distance')
            
            context['breakdown_type'] = 'players'  # Keep for template compatibility
            context['group'] = group
            context['cyclists'] = cyclists
    
    return render(request, 'admin/api/hierarchy_breakdown.html', context)


def _propagate_group_totals_to_parents(
    totals_by_group: Dict[int, float],
    filtered_group_ids: Optional[set] = None,
    max_iterations: int = 10,
) -> None:
    """Roll up child group totals to parents (bottom-up, each child once)."""
    processed_groups: set = set()
    for _ in range(max_iterations):
        changed = False
        for group_id_val in list(totals_by_group.keys()):
            if group_id_val in processed_groups:
                continue
            try:
                group = Group.objects.get(id=group_id_val)
                if group.parent:
                    parent_id = group.parent.id
                    if filtered_group_ids is None or parent_id in filtered_group_ids:
                        if parent_id not in totals_by_group:
                            totals_by_group[parent_id] = 0.0
                        totals_by_group[parent_id] += totals_by_group[group_id_val]
                        processed_groups.add(group_id_val)
                        changed = True
            except Group.DoesNotExist:
                processed_groups.add(group_id_val)
        if not changed:
            break


def _filter_group_totals_for_table_level(
    totals_by_group: Dict[int, float],
    group_type: str,
) -> Dict[int, float]:
    """Keep only TOP-level or leaf groups for record/badge comparison."""
    filtered: Dict[int, float] = {}
    for group_id_val, total in totals_by_group.items():
        try:
            group = Group.objects.only('parent', 'is_visible').get(id=group_id_val)
            if not group.is_visible:
                continue
            if group_type == 'top_groups':
                if not group.parent:
                    filtered[group_id_val] = total
            elif group.parent:
                filtered[group_id_val] = total
        except Group.DoesNotExist:
            continue
    return filtered


def _group_record_holder_from_id(group_id: int) -> Dict[str, Any]:
    """Build kiosk-style holder dict for analytics record tiles."""
    top_group = Group.objects.only('id', 'name', 'short_name', 'parent').get(id=group_id)
    if top_group.short_name and top_group.short_name.strip():
        kiosk_label = top_group.short_name.strip()
    else:
        kiosk_label = top_group.name
    parent_group_name = None
    if top_group.parent:
        try:
            parent_group_name = Group.objects.only('name').get(id=top_group.parent.id).name
        except Group.DoesNotExist:
            pass
    return {
        'name': kiosk_label,
        'parent_group_name': parent_group_name,
    }


def _top_level_period_sum(totals_by_group: Dict[int, float]) -> Decimal:
    """Sum period totals for visible top-level groups (no double-counting)."""
    top_level_group_ids = set(
        Group.objects.filter(is_visible=True, parent__isnull=True).values_list('id', flat=True)
    )
    period_total = Decimal('0.00000')
    for gid, val in totals_by_group.items():
        if gid in top_level_group_ids:
            period_total += Decimal(str(val))
    return period_total


def _compute_current_period_tiles(
    *,
    group_type: str,
    metric_mode: str,
    now,
    use_group_filter: bool = False,
    group_id: str = '',
    use_event_filter: bool = False,
    event_id: str = '',
    use_cyclist_filter: bool = False,
    cyclist_id: str = '',
    use_track_filter: bool = False,
    track_id: str = '',
) -> Dict[str, Dict[str, Any]]:
    """
    Current calendar periods aligned with the public leaderboard.

    Uses HourlyMetric for today / this week / this month / this year, with
    analytics filters applied (group, event, track, cyclist).
    """
    metric_field = _hourly_metric_field(metric_mode)
    sum_output_field = _sum_output_field(metric_mode)

    filtered_group_ids = None
    if use_group_filter and group_id:
        try:
            filtered_group = Group.objects.get(pk=group_id)
            filtered_group_ids = set(_get_descendant_group_ids(filtered_group))
        except Group.DoesNotExist:
            pass

    filter_kwargs = dict(
        use_event_filter=use_event_filter,
        event_id=event_id,
        use_group_filter=use_group_filter,
        group_id=group_id,
        use_cyclist_filter=use_cyclist_filter,
        cyclist_id=cyclist_id,
        use_track_filter=use_track_filter,
        track_id=track_id,
    )

    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    days_since_monday = now.weekday()
    week_start = (now - timedelta(days=days_since_monday)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    week_end = (week_start + timedelta(days=6)).replace(
        hour=23, minute=59, second=59, microsecond=999999
    )
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if now.month == 12:
        month_end = now.replace(year=now.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        month_end = now.replace(month=now.month + 1, day=1) - timedelta(days=1)
    month_end = month_end.replace(hour=23, minute=59, second=59, microsecond=999999)
    year_start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    year_end = now.replace(month=12, day=31, hour=23, minute=59, second=59, microsecond=999999)

    period_windows = {
        'daily': (today_start, None),
        'weekly': (week_start, week_end),
        'monthly': (month_start, month_end),
        'yearly': (year_start, year_end),
    }

    result: Dict[str, Dict[str, Any]] = {}
    for period_key, (window_start, window_end) in period_windows.items():
        metrics_qs = HourlyMetric.objects.filter(timestamp__gte=window_start)
        if window_end is not None:
            metrics_qs = metrics_qs.filter(timestamp__lte=window_end)
        metrics_qs = _apply_analytics_metric_filters(metrics_qs, **filter_kwargs)
        holder, value, total = _compute_period_record_from_hourly(
            metrics_qs,
            metric_field=metric_field,
            sum_output_field=sum_output_field,
            group_type=group_type,
            filtered_group_ids=filtered_group_ids,
        )
        result[period_key] = {
            'holder': holder,
            'value': value,
            'total': total,
        }
    return result


def _format_peak_period_label(trunc_kind: str, period) -> Optional[str]:
    """Human-readable label for a historical peak period."""
    if period is None:
        return None
    if trunc_kind == 'day':
        return period.isoformat() if hasattr(period, 'isoformat') else str(period)
    if trunc_kind == 'week':
        iso = period.isocalendar()
        return f"KW {iso[1]} · {iso[0]}"
    if trunc_kind == 'month':
        return period.strftime('%m/%Y')
    if trunc_kind == 'year':
        return str(getattr(period, 'year', period))
    return str(period)


def _compute_historical_peak_period(
    metrics_qs,
    *,
    trunc_func,
    trunc_kind: str,
    metric_field: str,
    sum_output_field,
    group_type: str,
    filtered_group_ids: Optional[set] = None,
) -> tuple:
    """
    Best single calendar period (day/week/month/year) ever recorded in metrics_qs.

    Returns (holder, value, period_label, top_level_total_for_peak_period).
    """
    rows = metrics_qs.filter(group_at_time__isnull=False).annotate(
        period=trunc_func('timestamp'),
    ).values('group_at_time', 'period').annotate(
        period_total=Sum(metric_field, output_field=sum_output_field),
    )

    visible_group_ids = set(Group.objects.filter(is_visible=True).values_list('id', flat=True))
    by_group_period: Dict[tuple, float] = {}
    for row in rows:
        gid = row.get('group_at_time')
        period = row.get('period')
        if gid and period and gid in visible_group_ids:
            by_group_period[(gid, period)] = float(row.get('period_total') or 0.0)

    if not by_group_period:
        return None, 0.0, None, Decimal('0.00000')

    best_group_id = None
    best_value = 0.0
    best_period = None
    for period in {p for (_, p) in by_group_period.keys()}:
        period_totals = {gid: val for (gid, p), val in by_group_period.items() if p == period}
        _propagate_group_totals_to_parents(period_totals, filtered_group_ids)
        filtered = _filter_group_totals_for_table_level(period_totals, group_type)
        for gid, val in filtered.items():
            if val > best_value:
                best_value = val
                best_group_id = gid
                best_period = period

    peak_holder = None
    if best_group_id and best_value > 0:
        peak_holder = _group_record_holder_from_id(best_group_id)

    peak_total = Decimal('0.00000')
    if best_period is not None:
        period_totals = {
            gid: val for (gid, p), val in by_group_period.items() if p == best_period
        }
        _propagate_group_totals_to_parents(period_totals, filtered_group_ids)
        peak_total = _top_level_period_sum(period_totals)

    period_label = _format_peak_period_label(trunc_kind, best_period)
    return peak_holder, best_value, period_label, peak_total


def _apply_analytics_metric_filters(
    qs,
    *,
    use_event_filter: bool,
    event_id: str,
    use_group_filter: bool,
    group_id: str,
    use_cyclist_filter: bool,
    cyclist_id: str,
    use_track_filter: bool,
    track_id: str,
):
    """Apply standard analytics filters to an HourlyMetric queryset."""
    if use_event_filter and event_id:
        try:
            event = Event.objects.get(pk=event_id)
            group_ids = event.group_statuses.values_list('group_id', flat=True)
            qs = qs.filter(group_at_time_id__in=group_ids)
        except Event.DoesNotExist:
            pass
    if use_group_filter and group_id:
        try:
            group = Group.objects.get(pk=group_id)
            descendant_ids = _get_descendant_group_ids(group)
            qs = qs.filter(group_at_time_id__in=descendant_ids)
        except Group.DoesNotExist:
            pass
    if use_cyclist_filter and cyclist_id:
        qs = qs.filter(cyclist_id=cyclist_id)
    if use_track_filter and track_id:
        try:
            track = TravelTrack.objects.get(pk=track_id)
            group_ids = track.group_statuses.values_list('group_id', flat=True)
            qs = qs.filter(group_at_time_id__in=group_ids)
        except TravelTrack.DoesNotExist:
            pass
    return qs


def _compute_period_record_from_hourly(
    metrics_qs,
    *,
    metric_field: str,
    sum_output_field,
    group_type: str,
    filtered_group_ids: Optional[set] = None,
) -> tuple:
    """
    Best group total for a fixed calendar window (week / month / year) from HourlyMetric.

    Metrics are attributed to group_at_time, then rolled up to parents.
    """
    rows = metrics_qs.filter(group_at_time__isnull=False).values('group_at_time').annotate(
        period_total=Sum(metric_field, output_field=sum_output_field),
    )
    visible_group_ids = set(Group.objects.filter(is_visible=True).values_list('id', flat=True))
    totals_by_group: Dict[int, float] = {}
    for row in rows:
        gid = row.get('group_at_time')
        if gid and gid in visible_group_ids:
            totals_by_group[gid] = float(row.get('period_total') or 0.0)

    _propagate_group_totals_to_parents(totals_by_group, filtered_group_ids)
    filtered = _filter_group_totals_for_table_level(totals_by_group, group_type)

    record_holder = None
    record_value = 0.0
    if filtered:
        best_group_id = max(filtered.items(), key=lambda x: x[1])[0]
        if filtered[best_group_id] > 0:
            record_holder = _group_record_holder_from_id(best_group_id)
            record_value = filtered[best_group_id]

    period_total = Decimal('0.00000')
    top_level_group_ids = set(
        Group.objects.filter(is_visible=True, parent__isnull=True).values_list('id', flat=True)
    )
    for gid, val in totals_by_group.items():
        if gid in top_level_group_ids:
            period_total += Decimal(str(val))

    return record_holder, record_value, period_total


def _compute_yearly_record_from_ledger(
    *,
    group_type: str,
    use_group_filter: bool = False,
    group_id: str = '',
    use_event_filter: bool = False,
    event_id: str = '',
    use_track_filter: bool = False,
    track_id: str = '',
) -> tuple:
    """
    Yearly km tile from Group ledger (same source as ranking / top-groups table).

    HourlyMetric undercounts vs the official period ledger (e.g. FEZitty 1288 vs 1503).
    """
    groups_qs = Group.objects.filter(is_visible=True)
    if use_group_filter and group_id:
        try:
            group = Group.objects.get(pk=group_id)
            groups_qs = groups_qs.filter(id__in=_get_descendant_group_ids(group))
        except Group.DoesNotExist:
            pass
    if use_event_filter and event_id:
        try:
            event = Event.objects.get(pk=event_id)
            groups_qs = groups_qs.filter(id__in=event.group_statuses.values_list('group_id', flat=True))
        except Event.DoesNotExist:
            pass
    if use_track_filter and track_id:
        try:
            track = TravelTrack.objects.get(pk=track_id)
            groups_qs = groups_qs.filter(id__in=track.group_statuses.values_list('group_id', flat=True))
        except TravelTrack.DoesNotExist:
            pass

    table_qs = _filter_groups_for_analytics_table(groups_qs, group_type)
    best_group = None
    best_value = 0.0
    for group in table_qs.select_related('group_type', 'parent'):
        value = _analytics_group_km_from_ledger(group, group_type)
        if value > best_value:
            best_value = value
            best_group = group

    # Overall total always uses TOP-level ranking km (no double-counting).
    yearly_total = Decimal('0.00000')
    top_level_qs = groups_qs.filter(parent__isnull=True)
    for group in top_level_qs:
        yearly_total += Decimal(str(_analytics_group_km_from_ledger(group, 'top_groups')))

    record_holder = None
    if best_group and best_value > 0:
        record_holder = _group_record_holder_from_id(best_group.id)
    return record_holder, best_value, yearly_total


def _compute_daily_record_in_range(
    metrics_qs,
    *,
    metric_field: str,
    sum_output_field,
    group_type: str,
    filtered_group_ids: Optional[set] = None,
):
    """
    Best single calendar day for one group within metrics_qs (HourlyMetric).

    Matches the daily utilization chart: per-day sums, not the whole filter range.
    """
    from datetime import date as date_type

    rows = metrics_qs.filter(group_at_time__isnull=False).annotate(
        day=TruncDate('timestamp'),
    ).values('group_at_time', 'day').annotate(
        day_total=Sum(metric_field, output_field=sum_output_field),
    )

    visible_group_ids = set(Group.objects.filter(is_visible=True).values_list('id', flat=True))
    by_group_day: Dict[tuple, float] = {}
    for row in rows:
        gid = row.get('group_at_time')
        day = row.get('day')
        if gid and day and gid in visible_group_ids:
            by_group_day[(gid, day)] = float(row.get('day_total') or 0.0)

    if not by_group_day:
        return None, 0.0, None, Decimal('0.00000')

    best_group_id = None
    best_value = 0.0
    best_day: Optional[date_type] = None
    for day in {d for (_, d) in by_group_day.keys()}:
        day_totals = {gid: val for (gid, d), val in by_group_day.items() if d == day}
        _propagate_group_totals_to_parents(day_totals, filtered_group_ids)
        filtered = _filter_group_totals_for_table_level(day_totals, group_type)
        for gid, val in filtered.items():
            if val > best_value:
                best_value = val
                best_group_id = gid
                best_day = day

    daily_record_holder = None
    if best_group_id and best_value > 0:
        daily_record_holder = _group_record_holder_from_id(best_group_id)

    daily_total = Decimal('0.00000')
    if best_day:
        day_totals = {gid: val for (gid, d), val in by_group_day.items() if d == best_day}
        _propagate_group_totals_to_parents(day_totals, filtered_group_ids)
        top_level_group_ids = set(
            Group.objects.filter(is_visible=True, parent__isnull=True).values_list('id', flat=True)
        )
        for gid, val in day_totals.items():
            if gid in top_level_group_ids:
                daily_total += Decimal(str(val))

    record_date = best_day.isoformat() if best_day else None
    return daily_record_holder, best_value, record_date, daily_total


def _filter_groups_for_analytics_table(groups_qs, group_type: str):
    """
    Restrict the groups table to one hierarchy level.

    - top_groups: TOP/master groups only (no parent)
    - subgroups: leaf groups only (no child groups)
    """
    from django.db.models import Count

    qs = groups_qs.annotate(_child_count=Count('children'))
    if group_type == 'top_groups':
        return qs.filter(parent__isnull=True)
    return qs.filter(_child_count=0)


def _build_filtered_hourly_metrics_qs(
    start_dt: datetime,
    end_dt: datetime,
    *,
    use_event_filter: bool = False,
    event_id: str = '',
    use_group_filter: bool = False,
    group_id: str = '',
    use_cyclist_filter: bool = False,
    cyclist_id: str = '',
    use_track_filter: bool = False,
    track_id: str = '',
    require_group_at_time: bool = False,
    select_related: bool = False,
):
    """HourlyMetric queryset for analytics with date range and optional filters."""
    qs = HourlyMetric.objects.filter(
        timestamp__gte=start_dt,
        timestamp__lte=end_dt,
    )
    if require_group_at_time:
        qs = qs.filter(group_at_time__isnull=False)
    if select_related:
        qs = qs.select_related('device', 'cyclist', 'group_at_time')

    if use_event_filter and event_id:
        try:
            event = Event.objects.get(pk=event_id)
            group_ids = event.group_statuses.values_list('group_id', flat=True)
            qs = qs.filter(group_at_time_id__in=group_ids)
        except Event.DoesNotExist:
            pass

    if use_group_filter and group_id:
        try:
            group = Group.objects.get(pk=group_id)
            descendant_ids = _get_descendant_group_ids(group)
            qs = qs.filter(group_at_time_id__in=descendant_ids)
        except Group.DoesNotExist:
            pass

    if use_cyclist_filter and cyclist_id:
        qs = qs.filter(cyclist_id=cyclist_id)

    if use_track_filter and track_id:
        try:
            track = TravelTrack.objects.get(pk=track_id)
            group_ids = track.group_statuses.values_list('group_id', flat=True)
            qs = qs.filter(group_at_time_id__in=group_ids)
        except TravelTrack.DoesNotExist:
            pass

    return qs


def _get_descendant_group_ids(group: Group) -> List[int]:
    """Recursively get all descendant group IDs including the group itself."""
    descendant_ids = [group.id]
    
    def get_children(parent_id: int):
        children = Group.objects.filter(parent_id=parent_id, is_visible=True).values_list('id', flat=True)
        for child_id in children:
            descendant_ids.append(child_id)
            get_children(child_id)
    
    get_children(group.id)
    return descendant_ids


class AnalyticsAdmin:
    """Admin integration for Analytics dashboard."""
    
    def __init__(self, admin_site):
        self.admin_site = admin_site
    
    def get_urls(self):
        """Register analytics URLs."""
        from django.urls import path
        urls = [
            path('analytics/', self.admin_site.admin_view(analytics_dashboard), name='api_analytics_dashboard'),
            path('analytics/data/', self.admin_site.admin_view(analytics_data_api), name='api_analytics_data_api'),
            path('analytics/export/', self.admin_site.admin_view(export_data), name='api_analytics_export'),
            path('analytics/hierarchy/', self.admin_site.admin_view(hierarchy_breakdown), name='api_analytics_hierarchy'),
        ]
        return urls

