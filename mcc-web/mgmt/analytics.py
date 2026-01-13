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
from django.db.models import Sum, Count, Q, F, DecimalField
from django.db.models.functions import TruncHour, TruncDay, TruncDate
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

from api.models import (
    HourlyMetric, EventHistory, Event, Group, Cyclist, CyclistDeviceCurrentMileage, TravelTrack
)
from iot.models import Device
from leaderboard.views import _calculate_group_totals_from_metrics


# Analytics views as standalone functions
@staff_member_required
def analytics_dashboard(request):
    """Main analytics dashboard view."""
    # Get date range from request
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    event_id = request.GET.get('event_id')
    group_id = request.GET.get('group_id')
    player_id = request.GET.get('player_id')
    
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
        'player_id': player_id,
        'track_id': request.GET.get('track_id'),
        'use_event_filter': request.GET.get('use_event_filter', 'false') == 'true',
        'use_group_filter': request.GET.get('use_group_filter', 'true') == 'true',  # Default: true
        'use_player_filter': request.GET.get('use_player_filter', 'true') == 'true',  # Default: true
        'use_track_filter': request.GET.get('use_track_filter', 'false') == 'true',
        'events': Event.objects.all().order_by('-start_time'),
        'groups': Group.objects.filter(is_visible=True).order_by('name'),
        'cyclists': Cyclist.objects.filter(is_visible=True).order_by('user_id'),
        'tracks': TravelTrack.objects.filter(is_active=True).order_by('name'),
    }
    
    return render(request, 'admin/api/analytics_dashboard.html', context)


@staff_member_required
def analytics_data_api(request):
    """API endpoint for chart data and aggregated statistics."""
    start_date = request.GET.get('start_date', '').strip()
    end_date = request.GET.get('end_date', '').strip()
    event_id = request.GET.get('event_id', '').strip()
    group_id = request.GET.get('group_id', '').strip()
    player_id = request.GET.get('player_id', '').strip()
    track_id = request.GET.get('track_id', '').strip()
    use_event_filter = request.GET.get('use_event_filter', 'false').strip().lower() == 'true'
    use_group_filter = request.GET.get('use_group_filter', 'true').strip().lower() == 'true'  # Default: true
    use_player_filter = request.GET.get('use_player_filter', 'true').strip().lower() == 'true'  # Default: true
    use_track_filter = request.GET.get('use_track_filter', 'false').strip().lower() == 'true'
    report_type = request.GET.get('report_type', 'hourly')  # hourly, daily, aggregated
    group_type = request.GET.get('group_type', 'top_groups')  # top_groups or subgroups
    
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
    
    # Build base queryset with optimized queries
    metrics_qs = HourlyMetric.objects.filter(
        timestamp__gte=start_dt,
        timestamp__lte=end_dt
    ).select_related('device', 'cyclist', 'group_at_time')
    
    # Apply filters only if enabled
    if use_event_filter and event_id:
        # Filter by groups participating in event
        try:
            event = Event.objects.get(pk=event_id)
            group_ids = event.group_statuses.values_list('group_id', flat=True)
            metrics_qs = metrics_qs.filter(group_at_time_id__in=group_ids)
        except Event.DoesNotExist:
            pass
    
    if use_group_filter and group_id:
        # Filter by group and all its descendants
        try:
            group = Group.objects.get(pk=group_id)
            descendant_ids = _get_descendant_group_ids(group)
            metrics_qs = metrics_qs.filter(group_at_time_id__in=descendant_ids)
        except Group.DoesNotExist:
            pass
    
    if use_player_filter and player_id:
        metrics_qs = metrics_qs.filter(cyclist_id=player_id)
    
    if use_track_filter and track_id:
        # Filter by groups participating in track
        try:
            track = TravelTrack.objects.get(pk=track_id)
            group_ids = track.group_statuses.values_list('group_id', flat=True)
            metrics_qs = metrics_qs.filter(group_at_time_id__in=group_ids)
        except TravelTrack.DoesNotExist:
            pass
    
    response_data = {}
    
    if report_type == 'hourly':
        # Hourly utilization data
        hourly_data = metrics_qs.annotate(
            hour=TruncHour('timestamp')
        ).values('hour').annotate(
            total_distance=Sum('distance_km', output_field=DecimalField())
        ).order_by('hour')
        
        response_data['hourly'] = {
            'labels': [item['hour'].strftime('%Y-%m-%d %H:00') if item.get('hour') else '' for item in hourly_data],
            'data': [float(item.get('total_distance') or 0) for item in hourly_data],
        }
    
    elif report_type == 'daily':
        # Daily utilization data
        daily_data = metrics_qs.annotate(
            day=TruncDate('timestamp')
        ).values('day').annotate(
            total_distance=Sum('distance_km', output_field=DecimalField())
        ).order_by('day')
        
        response_data['daily'] = {
            'labels': [item['day'].strftime('%Y-%m-%d') if item.get('day') else '' for item in daily_data],
            'data': [float(item.get('total_distance') or 0) for item in daily_data],
        }
    
    elif report_type == 'aggregated':
        # Calculate total_distance and top_groups from HourlyMetric (consistent with Leaderboard)
        # This ensures Analytics shows the same values as the Records Chips
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
        
        # Use HourlyMetric to calculate totals (consistent with Leaderboard)
        # Get all groups as a list for the calculation function
        groups_list = list(all_visible_groups.select_related('parent', 'group_type'))
        
        # Calculate totals from HourlyMetric (with filters applied to metrics)
        # Note: We need to apply filters to the HourlyMetric query, not just the groups
        now = timezone.now()
        
        # Build base HourlyMetric queryset with filters
        total_metrics_qs = HourlyMetric.objects.filter(
            group_at_time__isnull=False
        )
        
        # Apply filters to HourlyMetric query
        if use_event_filter and event_id:
            try:
                event = Event.objects.get(pk=event_id)
                group_ids = event.group_statuses.values_list('group_id', flat=True)
                total_metrics_qs = total_metrics_qs.filter(group_at_time_id__in=group_ids)
            except Event.DoesNotExist:
                pass
        
        if use_group_filter and group_id:
            try:
                group = Group.objects.get(pk=group_id)
                descendant_ids = _get_descendant_group_ids(group)
                total_metrics_qs = total_metrics_qs.filter(group_at_time_id__in=descendant_ids)
            except Group.DoesNotExist:
                pass
        
        if use_player_filter and player_id:
            total_metrics_qs = total_metrics_qs.filter(cyclist_id=player_id)
        
        if use_track_filter and track_id:
            try:
                track = TravelTrack.objects.get(pk=track_id)
                group_ids = track.group_statuses.values_list('group_id', flat=True)
                total_metrics_qs = total_metrics_qs.filter(group_at_time_id__in=group_ids)
            except TravelTrack.DoesNotExist:
                pass
        
        # Calculate total distance from HourlyMetric (sum of all top-level groups)
        # Use the same logic as leaderboard to ensure consistency
        # First, get totals per group from HourlyMetric (only direct metrics, no aggregation yet)
        group_totals_from_metrics = total_metrics_qs.values('group_at_time_id').annotate(
            total=Sum('distance_km', output_field=DecimalField())
        )
        
        # Build a dictionary of group_id -> total (only direct metrics, no parent aggregation yet)
        group_total_dict = {item['group_at_time_id']: float(item['total'] or 0.0) for item in group_totals_from_metrics}
        
        # Propagate to parent groups (hierarchical aggregation)
        # IMPORTANT: Track processed groups to avoid double-counting
        # Process bottom-up: only process each group once by tracking which groups have been processed
        processed_groups = set()
        max_iterations = 10
        iteration = 0
        while iteration < max_iterations:
            iteration += 1
            changed = False
            # Process only groups that haven't been processed yet
            groups_to_process = [gid for gid in group_total_dict.keys() if gid not in processed_groups]
            for group_id_val in groups_to_process:
                try:
                    group = Group.objects.get(id=group_id_val)
                    if group.parent and group.parent.id in [g.id for g in groups_list]:
                        parent_id = group.parent.id
                        if parent_id not in group_total_dict:
                            group_total_dict[parent_id] = 0.0
                        # Add this group's value to parent (only once)
                        group_total_dict[parent_id] += group_total_dict[group_id_val]
                        processed_groups.add(group_id_val)
                        changed = True
                except Group.DoesNotExist:
                    processed_groups.add(group_id_val)  # Mark as processed even if not found
                    pass
            if not changed:
                break
        
        # Calculate total_distance: sum only top-level groups (no parent) to avoid double-counting
        top_level_groups = all_visible_groups.filter(parent__isnull=True)
        total_distance = Decimal('0.00000')
        for group in top_level_groups:
            if group.id in group_total_dict:
                total_distance += Decimal(str(group_total_dict[group.id]))
        
        # Also include EventHistory data only if event filter is enabled
        event_history_total = Decimal('0.00000')
        if use_event_filter and event_id:
            try:
                event = Event.objects.get(pk=event_id)
                event_history_qs = EventHistory.objects.filter(
                    event=event,
                    end_time__gte=start_dt,
                    end_time__lte=end_dt
                )
                if use_group_filter and group_id:
                    try:
                        group = Group.objects.get(pk=group_id)
                        descendant_ids = _get_descendant_group_ids(group)
                        event_history_qs = event_history_qs.filter(group_id__in=descendant_ids)
                    except Group.DoesNotExist:
                        pass
                event_history_total = event_history_qs.aggregate(
                    total=Sum('total_distance_km', output_field=DecimalField())
                )['total'] or Decimal('0.00000')
                total_distance += event_history_total
            except Event.DoesNotExist:
                pass
        
        # Top groups by mileage from HourlyMetric (consistent with Leaderboard)
        groups_qs = Group.objects.filter(is_visible=True)
        
        # Apply filters if enabled
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
        
        # Get top groups by HourlyMetric total (consistent with Leaderboard)
        top_groups = []
        for g in groups_qs.select_related('group_type')[:50]:  # Get more to filter by total
            group_total = group_total_dict.get(g.id, 0.0)
            if group_total > 0:
                top_groups.append({
                    'name': g.name,
                    'type': g.group_type.name if g.group_type else '',
                    'distance': group_total
                })
        
        # Sort by distance and take top 10
        top_groups = sorted(top_groups, key=lambda x: x['distance'], reverse=True)[:10]
        
        # Add EventHistory data only if event filter is enabled
        # This adds historical event data on top of current group totals
        if use_event_filter and event_id:
            try:
                event = Event.objects.get(pk=event_id)
                event_history_qs = EventHistory.objects.filter(
                    event=event,
                    end_time__gte=start_dt,
                    end_time__lte=end_dt
                ).select_related('group')
                if use_group_filter and group_id:
                    try:
                        group = Group.objects.get(pk=group_id)
                        descendant_ids = _get_descendant_group_ids(group)
                        event_history_qs = event_history_qs.filter(group_id__in=descendant_ids)
                    except Group.DoesNotExist:
                        pass
                
                event_groups = list(event_history_qs.values(
                    'group__name', 'group__group_type__name'
                ).annotate(
                    total_distance=Sum('total_distance_km', output_field=DecimalField())
                ).order_by('-total_distance')[:10])
                
                # Merge with current group totals
                # Create a dict from current top_groups
                group_dict = {}
                for item in top_groups:
                    key = (item.get('name'), item.get('type'))
                    if key[0]:  # Only add if name exists
                        group_dict[key] = item.get('distance', 0)
                
                # Add event history data
                for item in event_groups:
                    # Convert group__group_type__name to string (it may be None)
                    group_type_name = item.get('group__group_type__name') or ''
                    key = (item.get('group__name'), group_type_name)
                    if key[0]:  # Only add if name exists
                        event_distance = float(item.get('total_distance') or 0)
                        if key in group_dict:
                            # Add event distance to existing group total
                            group_dict[key] += event_distance
                        else:
                            # New group from event history
                            group_dict[key] = event_distance
                
                # Rebuild top_groups from merged dict
                top_groups = [
                    {
                        'name': name,
                        'type': gtype or '',
                        'distance': distance
                    }
                    for (name, gtype), distance in sorted(group_dict.items(), key=lambda x: x[1], reverse=True)[:10]
                ]
            except Event.DoesNotExist:
                pass
        
        # Top cyclists by mileage
        top_cyclists_qs = metrics_qs.filter(cyclist__isnull=False).values(
            'cyclist__user_id', 'cyclist__id_tag', 'cyclist_id'
        ).annotate(
            total_distance=Sum('distance_km', output_field=DecimalField())
        ).order_by('-total_distance')[:10]
        
        # Get cyclist IDs to fetch their groups
        cyclist_ids = [item.get('cyclist_id') for item in top_cyclists_qs if item.get('cyclist_id')]
        cyclists_with_groups = {}
        if cyclist_ids:
            from django.db.models import Prefetch
            cyclists = Cyclist.objects.filter(id__in=cyclist_ids).prefetch_related('groups')
            for cyclist in cyclists:
                # Get the first visible group, or first group if none visible
                primary_group = cyclist.groups.filter(is_visible=True).first()
                if not primary_group:
                    primary_group = cyclist.groups.first()
                cyclists_with_groups[cyclist.id] = primary_group.name if primary_group else _('No Group')
        
        top_cyclists = list(top_cyclists_qs)
        top_cyclists = [
            {
                'user_id': item.get('cyclist__user_id') or '',
                'id_tag': item.get('cyclist__id_tag') or '',
                'group': cyclists_with_groups.get(item.get('cyclist_id'), _('Unknown')),
                'distance': float(item.get('total_distance') or 0)
            }
            for item in top_cyclists
        ]
        
        # If no cyclist data from HourlyMetric, try current cyclist totals as fallback
        if not top_cyclists or (len(top_cyclists) > 0 and all(c.get('distance', 0) == 0 for c in top_cyclists)):
            cyclists_qs = Cyclist.objects.filter(is_visible=True)
            if player_id:
                cyclists_qs = cyclists_qs.filter(pk=player_id)
            if group_id:
                try:
                    group = Group.objects.get(pk=group_id)
                    descendant_ids = _get_descendant_group_ids(group)
                    cyclists_qs = cyclists_qs.filter(groups__id__in=descendant_ids).distinct()
                except Group.DoesNotExist:
                    pass
            
            # Prefetch groups for cyclists
            cyclists_list = list(cyclists_qs.prefetch_related('groups').order_by('-distance_total')[:10])
            top_cyclists = []
            for c in cyclists_list:
                if c.distance_total and c.distance_total > 0:
                    # Get the first visible group, or first group if none visible
                    primary_group = c.groups.filter(is_visible=True).first()
                    if not primary_group:
                        primary_group = c.groups.first()
                    top_cyclists.append({
                        'user_id': c.user_id,
                        'id_tag': c.id_tag,
                        'group': primary_group.name if primary_group else _('No Group'),
                        'distance': float(c.distance_total or 0)
                    })
        
        # Top devices by mileage
        top_devices_qs = metrics_qs.values(
            'device__name', 'device__display_name'
        ).annotate(
            total_distance=Sum('distance_km', output_field=DecimalField())
        ).order_by('-total_distance')[:10]
        
        top_devices = list(top_devices_qs)
        top_devices = [
            {
                'name': item.get('device__display_name') or item.get('device__name') or '',
                'distance': float(item.get('total_distance') or 0)
            }
            for item in top_devices
        ]
        
        # If no device data from HourlyMetric, try current device totals as fallback
        if not top_devices or (len(top_devices) > 0 and all(d.get('distance', 0) == 0 for d in top_devices)):
            devices_qs = Device.objects.filter(is_visible=True)
            if group_id:
                try:
                    group = Group.objects.get(pk=group_id)
                    devices_qs = devices_qs.filter(group=group)
                except Group.DoesNotExist:
                    pass
            
            top_devices = [
                {
                    'name': d.display_name or d.name,
                    'distance': float(d.distance_total or 0)
                }
                for d in devices_qs.order_by('-distance_total')[:10]
                if d.distance_total and d.distance_total > 0
            ]
        
        # Calculate daily, weekly, monthly, and yearly totals and record holders (analog to badges)
        now = timezone.now()
        
        # Daily: Use filtered date range, or today if not filtered
        # If start_date == end_date, use only that specific day
        # Otherwise, use the filtered date range
        if start_dt.date() == end_dt.date():
            # Single day selected: use that specific day
            daily_start = start_dt.replace(hour=0, minute=0, second=0, microsecond=0)
            daily_end = end_dt.replace(hour=23, minute=59, second=59, microsecond=999999)
        else:
            # Date range selected: use filtered range
            daily_start = start_dt
            daily_end = end_dt
        
        # Apply filters only if enabled (same as main query)
        daily_metrics = HourlyMetric.objects.filter(
            timestamp__gte=daily_start,
            timestamp__lte=daily_end,
            group_at_time__isnull=False
        )
        if use_event_filter and event_id:
            try:
                event = Event.objects.get(pk=event_id)
                group_ids = event.group_statuses.values_list('group_id', flat=True)
                daily_metrics = daily_metrics.filter(group_at_time_id__in=group_ids)
            except Event.DoesNotExist:
                pass
        if use_group_filter and group_id:
            try:
                group = Group.objects.get(pk=group_id)
                descendant_ids = _get_descendant_group_ids(group)
                daily_metrics = daily_metrics.filter(group_at_time_id__in=descendant_ids)
            except Group.DoesNotExist:
                pass
        if use_player_filter and player_id:
            daily_metrics = daily_metrics.filter(cyclist_id=player_id)
        if use_track_filter and track_id:
            try:
                track = TravelTrack.objects.get(pk=track_id)
                group_ids = track.group_statuses.values_list('group_id', flat=True)
                daily_metrics = daily_metrics.filter(group_at_time_id__in=group_ids)
            except TravelTrack.DoesNotExist:
                pass
        
        daily_metrics = daily_metrics.values('group_at_time').annotate(
            daily_total=Sum('distance_km')
        )
        
        # Calculate daily kilometers per group (only for visible groups, like leaderboard)
        # Use only HourlyMetric data (updated every 60 seconds by cronjob)
        daily_km_by_group = {}
        visible_group_ids = set(Group.objects.filter(is_visible=True).values_list('id', flat=True))
        for metric in daily_metrics:
            group_id_val = metric.get('group_at_time')
            if group_id_val and group_id_val in visible_group_ids:
                daily_km_by_group[group_id_val] = float(metric.get('daily_total') or 0.0)
        
        # Aggregate to parent groups (same logic as leaderboard)
        # In leaderboard, aggregation happens for all groups, not just visible ones
        # But we only consider visible groups in the final calculation
        max_iterations = 10  # Prevent infinite loops
        iteration = 0
        filtered_group_ids = None
        if use_group_filter and group_id:
            try:
                filtered_group = Group.objects.get(pk=group_id)
                filtered_group_ids = set(_get_descendant_group_ids(filtered_group))
            except Group.DoesNotExist:
                pass
        
        # Aggregate to parent groups: for each child group, add its value to parent
        # Process bottom-up (children first, then their parents) to avoid double-counting
        # Track which groups we've processed across all iterations to avoid processing the same group twice
        all_processed_groups = set()
        while iteration < max_iterations:
            iteration += 1
            changed = False
            # Process all child groups (groups with a parent) that haven't been processed yet
            for group_id_val in list(daily_km_by_group.keys()):
                if group_id_val in all_processed_groups:
                    continue
                try:
                    group = Group.objects.get(id=group_id_val)
                    if group.parent:
                        parent_id = group.parent.id
                        # If filtering by group_id, only aggregate if parent is in filtered hierarchy
                        if filtered_group_ids is None or parent_id in filtered_group_ids:
                            if parent_id not in daily_km_by_group:
                                daily_km_by_group[parent_id] = 0.0
                                changed = True
                            # Add child's value to parent (only once ever)
                            child_value = daily_km_by_group[group_id_val]
                            daily_km_by_group[parent_id] += child_value
                            all_processed_groups.add(group_id_val)
                except Group.DoesNotExist:
                    pass
            if not changed:
                break
        
        # Find daily record holder - filter by group_type (only visible groups)
        daily_record_holder = None
        daily_record_value = 0.0
        if daily_km_by_group:
            # Filter groups based on group_type (only visible groups, like leaderboard)
            filtered_daily_km = {}
            for gid, km in daily_km_by_group.items():
                try:
                    g = Group.objects.only('parent', 'is_visible').get(id=gid)
                    # Only consider visible groups (like leaderboard)
                    if not g.is_visible:
                        continue
                    if group_type == 'top_groups':
                        # Only top groups (no parent)
                        if not g.parent:
                            filtered_daily_km[gid] = km
                    else:
                        # Only subgroups (has parent)
                        if g.parent:
                            filtered_daily_km[gid] = km
                except Group.DoesNotExist:
                    continue
            
            if filtered_daily_km:
                top_group_id = max(filtered_daily_km.items(), key=lambda x: x[1])[0]
                if filtered_daily_km[top_group_id] > 0:
                    try:
                        top_group = Group.objects.only('id', 'name', 'short_name', 'parent', 'distance_total').get(id=top_group_id)
                        # Get kiosk label (same logic as leaderboard)
                        if top_group.short_name and top_group.short_name.strip():
                            kiosk_label = top_group.short_name.strip()
                        else:
                            kiosk_label = top_group.name
                        # Get parent group name
                        parent_group_name = None
                        if top_group.parent:
                            try:
                                parent_group = Group.objects.only('name').get(id=top_group.parent.id)
                                parent_group_name = parent_group.name
                            except Group.DoesNotExist:
                                pass
                        
                        daily_record_holder = {
                            'name': kiosk_label,
                            'parent_group_name': parent_group_name,
                        }
                        # Use the aggregated daily_km value for this group (from the period calculation)
                        # This shows the actual kilometers collected in this period for this group
                        daily_record_value = filtered_daily_km[top_group_id]
                    except Group.DoesNotExist:
                        pass
        
        # Calculate daily_total: sum only top-level groups (no parent) to avoid double-counting
        # after aggregation to parent groups
        # Note: After aggregation, child groups still exist in daily_km_by_group,
        # but we only count top-level groups to get the correct total
        daily_total = Decimal('0.00000')
        if daily_km_by_group:
            # Get all top-level groups (no parent) and sum their aggregated values
            top_level_group_ids = set(
                Group.objects.filter(is_visible=True, parent__isnull=True).values_list('id', flat=True)
            )
            for group_id_val, km in daily_km_by_group.items():
                # Only count top-level groups to avoid double-counting with child groups
                if group_id_val in top_level_group_ids:
                    daily_total += Decimal(str(km))
        
        # Weekly: Monday to Sunday of current week
        days_since_monday = now.weekday()  # 0 = Monday, 6 = Sunday
        week_start = (now - timedelta(days=days_since_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
        week_end = (week_start + timedelta(days=6)).replace(hour=23, minute=59, second=59, microsecond=999999)
        
        # Apply filters only if enabled
        weekly_metrics = HourlyMetric.objects.filter(
            timestamp__gte=week_start,
            timestamp__lte=week_end,
            group_at_time__isnull=False
        )
        if use_event_filter and event_id:
            try:
                event = Event.objects.get(pk=event_id)
                group_ids = event.group_statuses.values_list('group_id', flat=True)
                weekly_metrics = weekly_metrics.filter(group_at_time_id__in=group_ids)
            except Event.DoesNotExist:
                pass
        if use_group_filter and group_id:
            try:
                group = Group.objects.get(pk=group_id)
                descendant_ids = _get_descendant_group_ids(group)
                weekly_metrics = weekly_metrics.filter(group_at_time_id__in=descendant_ids)
            except Group.DoesNotExist:
                pass
        if use_player_filter and player_id:
            weekly_metrics = weekly_metrics.filter(cyclist_id=player_id)
        if use_track_filter and track_id:
            try:
                track = TravelTrack.objects.get(pk=track_id)
                group_ids = track.group_statuses.values_list('group_id', flat=True)
                weekly_metrics = weekly_metrics.filter(group_at_time_id__in=group_ids)
            except TravelTrack.DoesNotExist:
                pass
        
        weekly_metrics = weekly_metrics.values('group_at_time').annotate(
            weekly_total=Sum('distance_km')
        )
        
        # Calculate weekly kilometers per group (only for visible groups)
        # Use only HourlyMetric data (updated every 60 seconds by cronjob)
        weekly_km_by_group = {}
        visible_group_ids = set(Group.objects.filter(is_visible=True).values_list('id', flat=True))
        for metric in weekly_metrics:
            group_id_val = metric.get('group_at_time')
            if group_id_val and group_id_val in visible_group_ids:
                weekly_km_by_group[group_id_val] = float(metric.get('weekly_total') or 0.0)
        
        # Aggregate to parent groups (same logic as leaderboard)
        max_iterations = 10
        iteration = 0
        filtered_group_ids = None
        if use_group_filter and group_id:
            try:
                filtered_group = Group.objects.get(pk=group_id)
                filtered_group_ids = set(_get_descendant_group_ids(filtered_group))
            except Group.DoesNotExist:
                pass
        
        # Aggregate to parent groups: track processed groups across all iterations
        all_processed_groups = set()
        while iteration < max_iterations:
            iteration += 1
            changed = False
            for group_id_val in list(weekly_km_by_group.keys()):
                if group_id_val in all_processed_groups:
                    continue
                try:
                    group = Group.objects.get(id=group_id_val)
                    if group.parent:
                        parent_id = group.parent.id
                        if filtered_group_ids is None or parent_id in filtered_group_ids:
                            if parent_id not in weekly_km_by_group:
                                weekly_km_by_group[parent_id] = 0.0
                                changed = True
                            child_value = weekly_km_by_group[group_id_val]
                            weekly_km_by_group[parent_id] += child_value
                            all_processed_groups.add(group_id_val)
                except Group.DoesNotExist:
                    pass
            if not changed:
                break
        
        # Find weekly record holder - filter by group_type (only visible groups)
        weekly_record_holder = None
        weekly_record_value = 0.0
        if weekly_km_by_group:
            # Filter groups based on group_type (only visible groups, like leaderboard)
            filtered_weekly_km = {}
            for gid, km in weekly_km_by_group.items():
                try:
                    g = Group.objects.only('parent', 'is_visible').get(id=gid)
                    # Only consider visible groups (like leaderboard)
                    if not g.is_visible:
                        continue
                    if group_type == 'top_groups':
                        # Only top groups (no parent)
                        if not g.parent:
                            filtered_weekly_km[gid] = km
                    else:
                        # Only subgroups (has parent)
                        if g.parent:
                            filtered_weekly_km[gid] = km
                except Group.DoesNotExist:
                    continue
            
            if filtered_weekly_km:
                top_group_id = max(filtered_weekly_km.items(), key=lambda x: x[1])[0]
                if filtered_weekly_km[top_group_id] > 0:
                    try:
                        top_group = Group.objects.only('id', 'name', 'short_name', 'parent', 'distance_total').get(id=top_group_id)
                        # Get kiosk label (same logic as leaderboard)
                        if top_group.short_name and top_group.short_name.strip():
                            kiosk_label = top_group.short_name.strip()
                        else:
                            kiosk_label = top_group.name
                        # Get parent group name
                        parent_group_name = None
                        if top_group.parent:
                            try:
                                parent_group = Group.objects.only('name').get(id=top_group.parent.id)
                                parent_group_name = parent_group.name
                            except Group.DoesNotExist:
                                pass
                        weekly_record_holder = {
                            'name': kiosk_label,
                            'parent_group_name': parent_group_name,
                        }
                        # Use the aggregated weekly_km value for this group (from the period calculation)
                        weekly_record_value = filtered_weekly_km[top_group_id]
                    except Group.DoesNotExist:
                        pass
        
        # Calculate weekly_total: sum only top-level groups (no parent) to avoid double-counting
        weekly_total = Decimal('0.00000')
        if weekly_km_by_group:
            top_level_group_ids = set(
                Group.objects.filter(is_visible=True, parent__isnull=True).values_list('id', flat=True)
            )
            for group_id_val, km in weekly_km_by_group.items():
                if group_id_val in top_level_group_ids:
                    weekly_total += Decimal(str(km))
        
        # Monthly: 1st to last day of current month
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if now.month == 12:
            month_end = now.replace(year=now.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            month_end = now.replace(month=now.month + 1, day=1) - timedelta(days=1)
        month_end = month_end.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        # Apply filters only if enabled
        monthly_metrics = HourlyMetric.objects.filter(
            timestamp__gte=month_start,
            timestamp__lte=month_end,
            group_at_time__isnull=False
        )
        if use_event_filter and event_id:
            try:
                event = Event.objects.get(pk=event_id)
                group_ids = event.group_statuses.values_list('group_id', flat=True)
                monthly_metrics = monthly_metrics.filter(group_at_time_id__in=group_ids)
            except Event.DoesNotExist:
                pass
        if use_group_filter and group_id:
            try:
                group = Group.objects.get(pk=group_id)
                descendant_ids = _get_descendant_group_ids(group)
                monthly_metrics = monthly_metrics.filter(group_at_time_id__in=descendant_ids)
            except Group.DoesNotExist:
                pass
        if use_player_filter and player_id:
            monthly_metrics = monthly_metrics.filter(cyclist_id=player_id)
        if use_track_filter and track_id:
            try:
                track = TravelTrack.objects.get(pk=track_id)
                group_ids = track.group_statuses.values_list('group_id', flat=True)
                monthly_metrics = monthly_metrics.filter(group_at_time_id__in=group_ids)
            except TravelTrack.DoesNotExist:
                pass
        
        monthly_metrics = monthly_metrics.values('group_at_time').annotate(
            monthly_total=Sum('distance_km')
        )
        
        # Calculate monthly kilometers per group (only for visible groups)
        # Use only HourlyMetric data (updated every 60 seconds by cronjob)
        monthly_km_by_group = {}
        visible_group_ids = set(Group.objects.filter(is_visible=True).values_list('id', flat=True))
        for metric in monthly_metrics:
            group_id_val = metric.get('group_at_time')
            if group_id_val and group_id_val in visible_group_ids:
                monthly_km_by_group[group_id_val] = float(metric.get('monthly_total') or 0.0)
        
        # Aggregate to parent groups (same logic as leaderboard)
        max_iterations = 10
        iteration = 0
        filtered_group_ids = None
        if use_group_filter and group_id:
            try:
                filtered_group = Group.objects.get(pk=group_id)
                filtered_group_ids = set(_get_descendant_group_ids(filtered_group))
            except Group.DoesNotExist:
                pass
        
        # Aggregate to parent groups: track processed groups across all iterations
        all_processed_groups = set()
        while iteration < max_iterations:
            iteration += 1
            changed = False
            for group_id_val in list(monthly_km_by_group.keys()):
                if group_id_val in all_processed_groups:
                    continue
                try:
                    group = Group.objects.get(id=group_id_val)
                    if group.parent:
                        parent_id = group.parent.id
                        if filtered_group_ids is None or parent_id in filtered_group_ids:
                            if parent_id not in monthly_km_by_group:
                                monthly_km_by_group[parent_id] = 0.0
                                changed = True
                            child_value = monthly_km_by_group[group_id_val]
                            monthly_km_by_group[parent_id] += child_value
                            all_processed_groups.add(group_id_val)
                except Group.DoesNotExist:
                    pass
            if not changed:
                break
        
        # Find monthly record holder - filter by group_type (only visible groups)
        monthly_record_holder = None
        monthly_record_value = 0.0
        if monthly_km_by_group:
            # Filter groups based on group_type (only visible groups, like leaderboard)
            filtered_monthly_km = {}
            for gid, km in monthly_km_by_group.items():
                try:
                    g = Group.objects.only('parent', 'is_visible').get(id=gid)
                    # Only consider visible groups (like leaderboard)
                    if not g.is_visible:
                        continue
                    if group_type == 'top_groups':
                        # Only top groups (no parent)
                        if not g.parent:
                            filtered_monthly_km[gid] = km
                    else:
                        # Only subgroups (has parent)
                        if g.parent:
                            filtered_monthly_km[gid] = km
                except Group.DoesNotExist:
                    continue
            
            if filtered_monthly_km:
                top_group_id = max(filtered_monthly_km.items(), key=lambda x: x[1])[0]
                if filtered_monthly_km[top_group_id] > 0:
                    try:
                        top_group = Group.objects.only('id', 'name', 'short_name', 'parent').get(id=top_group_id)
                        # Get kiosk label (same logic as leaderboard)
                        if top_group.short_name and top_group.short_name.strip():
                            kiosk_label = top_group.short_name.strip()
                        else:
                            kiosk_label = top_group.name
                        # Get parent group name
                        parent_group_name = None
                        if top_group.parent:
                            try:
                                parent_group = Group.objects.only('name').get(id=top_group.parent.id)
                                parent_group_name = parent_group.name
                            except Group.DoesNotExist:
                                pass
                        monthly_record_holder = {
                            'name': kiosk_label,
                            'parent_group_name': parent_group_name,
                        }
                        # Use the aggregated monthly_km value for this group (from the period calculation)
                        monthly_record_value = filtered_monthly_km[top_group_id]
                    except Group.DoesNotExist:
                        pass
        
        # Calculate monthly_total: sum only top-level groups (no parent) to avoid double-counting
        monthly_total = Decimal('0.00000')
        if monthly_km_by_group:
            top_level_group_ids = set(
                Group.objects.filter(is_visible=True, parent__isnull=True).values_list('id', flat=True)
            )
            for group_id_val, km in monthly_km_by_group.items():
                if group_id_val in top_level_group_ids:
                    monthly_total += Decimal(str(km))
        
        # Yearly: January 1st to December 31st of current year
        year_start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        year_end = now.replace(month=12, day=31, hour=23, minute=59, second=59, microsecond=999999)
        
        # Apply filters only if enabled
        yearly_metrics = HourlyMetric.objects.filter(
            timestamp__gte=year_start,
            timestamp__lte=year_end,
            group_at_time__isnull=False
        )
        if use_event_filter and event_id:
            try:
                event = Event.objects.get(pk=event_id)
                group_ids = event.group_statuses.values_list('group_id', flat=True)
                yearly_metrics = yearly_metrics.filter(group_at_time_id__in=group_ids)
            except Event.DoesNotExist:
                pass
        if use_group_filter and group_id:
            try:
                group = Group.objects.get(pk=group_id)
                descendant_ids = _get_descendant_group_ids(group)
                yearly_metrics = yearly_metrics.filter(group_at_time_id__in=descendant_ids)
            except Group.DoesNotExist:
                pass
        if use_player_filter and player_id:
            yearly_metrics = yearly_metrics.filter(cyclist_id=player_id)
        if use_track_filter and track_id:
            try:
                track = TravelTrack.objects.get(pk=track_id)
                group_ids = track.group_statuses.values_list('group_id', flat=True)
                yearly_metrics = yearly_metrics.filter(group_at_time_id__in=group_ids)
            except TravelTrack.DoesNotExist:
                pass
        
        yearly_metrics = yearly_metrics.values('group_at_time').annotate(
            yearly_total=Sum('distance_km')
        )
        
        # Calculate yearly kilometers per group (only for visible groups)
        # Use only HourlyMetric data (updated every 60 seconds by cronjob)
        yearly_km_by_group = {}
        visible_group_ids = set(Group.objects.filter(is_visible=True).values_list('id', flat=True))
        for metric in yearly_metrics:
            group_id_val = metric.get('group_at_time')
            if group_id_val and group_id_val in visible_group_ids:
                yearly_km_by_group[group_id_val] = float(metric.get('yearly_total') or 0.0)
        
        # Aggregate to parent groups (same logic as leaderboard)
        max_iterations = 10
        iteration = 0
        filtered_group_ids = None
        if use_group_filter and group_id:
            try:
                filtered_group = Group.objects.get(pk=group_id)
                filtered_group_ids = set(_get_descendant_group_ids(filtered_group))
            except Group.DoesNotExist:
                pass
        
        # Aggregate to parent groups: track processed groups across all iterations
        all_processed_groups = set()
        while iteration < max_iterations:
            iteration += 1
            changed = False
            for group_id_val in list(yearly_km_by_group.keys()):
                if group_id_val in all_processed_groups:
                    continue
                try:
                    group = Group.objects.get(id=group_id_val)
                    if group.parent:
                        parent_id = group.parent.id
                        if filtered_group_ids is None or parent_id in filtered_group_ids:
                            if parent_id not in yearly_km_by_group:
                                yearly_km_by_group[parent_id] = 0.0
                                changed = True
                            child_value = yearly_km_by_group[group_id_val]
                            yearly_km_by_group[parent_id] += child_value
                            all_processed_groups.add(group_id_val)
                except Group.DoesNotExist:
                    pass
            if not changed:
                break
        
        # Find yearly record holder - filter by group_type (only visible groups)
        yearly_record_holder = None
        yearly_record_value = 0.0
        if yearly_km_by_group:
            # Filter groups based on group_type (only visible groups, like leaderboard)
            filtered_yearly_km = {}
            for gid, km in yearly_km_by_group.items():
                try:
                    g = Group.objects.only('parent', 'is_visible').get(id=gid)
                    # Only consider visible groups (like leaderboard)
                    if not g.is_visible:
                        continue
                    if group_type == 'top_groups':
                        # Only top groups (no parent)
                        if not g.parent:
                            filtered_yearly_km[gid] = km
                    else:
                        # Only subgroups (has parent)
                        if g.parent:
                            filtered_yearly_km[gid] = km
                except Group.DoesNotExist:
                    continue
            
            if filtered_yearly_km:
                top_group_id = max(filtered_yearly_km.items(), key=lambda x: x[1])[0]
                if filtered_yearly_km[top_group_id] > 0:
                    try:
                        top_group = Group.objects.only('id', 'name', 'short_name', 'parent', 'distance_total').get(id=top_group_id)
                        # Get kiosk label (same logic as leaderboard)
                        if top_group.short_name and top_group.short_name.strip():
                            kiosk_label = top_group.short_name.strip()
                        else:
                            kiosk_label = top_group.name
                        # Get parent group name
                        parent_group_name = None
                        if top_group.parent:
                            try:
                                parent_group = Group.objects.only('name').get(id=top_group.parent.id)
                                parent_group_name = parent_group.name
                            except Group.DoesNotExist:
                                pass
                        yearly_record_holder = {
                            'name': kiosk_label,
                            'parent_group_name': parent_group_name,
                        }
                        # Use the aggregated yearly_km value for this group (from the period calculation)
                        yearly_record_value = filtered_yearly_km[top_group_id]
                    except Group.DoesNotExist:
                        pass
        
        # Calculate yearly_total: sum only top-level groups (no parent) to avoid double-counting
        yearly_total = Decimal('0.00000')
        if yearly_km_by_group:
            top_level_group_ids = set(
                Group.objects.filter(is_visible=True, parent__isnull=True).values_list('id', flat=True)
            )
            for group_id_val, km in yearly_km_by_group.items():
                if group_id_val in top_level_group_ids:
                    yearly_total += Decimal(str(km))
        
        response_data['aggregated'] = {
            'total_distance': float(total_distance),
            'daily_total': float(daily_total),
            'weekly_total': float(weekly_total),
            'monthly_total': float(monthly_total),
            'yearly_total': float(yearly_total),
            'daily_record_holder': daily_record_holder,
            'daily_record_value': float(daily_record_value),
            'weekly_record_holder': weekly_record_holder,
            'weekly_record_value': float(weekly_record_value),
            'monthly_record_holder': monthly_record_holder,
            'monthly_record_value': float(monthly_record_value),
            'yearly_record_holder': yearly_record_holder,
            'yearly_record_value': float(yearly_record_value),
            'top_groups': top_groups,
            'top_cyclists': top_cyclists,
            'top_devices': top_devices,
        }
    
    return JsonResponse(response_data)


@staff_member_required
def export_data(request):
    """Export filtered data as CSV or Excel."""
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    event_id = request.GET.get('event_id')
    group_id = request.GET.get('group_id')
    player_id = request.GET.get('player_id')
    export_format = request.GET.get('format', 'csv')  # csv or excel
    
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
    
    if player_id:
        metrics_qs = metrics_qs.filter(cyclist_id=player_id)
    
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
                'Timestamp', 'Player', 'ID Tag', 'Device', 'Group',
                'Group Type', 'Distance (km)'
            ]
            ws.append(headers)
            
            # Style headers
            for cell in ws[1]:
                cell.font = Font(bold=True)
                cell.alignment = Alignment(horizontal='center')
            
            # Data rows
            for metric in metrics_qs:
                ws.append([
                    metric.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                    metric.cyclist.user_id if metric.cyclist else '',
                    metric.cyclist.id_tag if metric.cyclist else '',
                    metric.device.display_name or metric.device.name,
                    metric.group_at_time.name if metric.group_at_time else '',
                    metric.group_at_time.group_type.name if metric.group_at_time and metric.group_at_time.group_type else '',
                    float(metric.distance_km),
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
            'Timestamp', 'Player', 'ID Tag', 'Device', 'Group',
            'Group Type', 'Distance (km)'
        ])
        
        for metric in metrics_qs:
            # Format distance with comma as decimal separator for German Excel
            distance_str = str(float(metric.distance_km)).replace('.', ',')
            writer.writerow([
                metric.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                metric.cyclist.user_id if metric.cyclist else '',
                metric.cyclist.id_tag if metric.cyclist else '',
                metric.device.display_name or metric.device.name,
                metric.group_at_time.name if metric.group_at_time else '',
                metric.group_at_time.group_type.name if metric.group_at_time and metric.group_at_time.group_type else '',
                distance_str,
            ])
        
        return response


@staff_member_required
def hierarchy_breakdown(request):
    """Hierarchy breakdown view with drill-down capability."""
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
                    'event_history__total_distance_km',
                    filter=Q(
                        event_history__event=event,
                        event_history__end_time__gte=start_dt,
                        event_history__end_time__lte=end_dt
                    ),
                    output_field=DecimalField()
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
                    'event_history__total_distance_km',
                    filter=Q(
                        event_history__event=event,
                        event_history__end_time__gte=start_dt,
                        event_history__end_time__lte=end_dt
                    ),
                    output_field=DecimalField()
                )
            ).filter(total_distance__gt=0).order_by('-total_distance')
            
            context['breakdown_type'] = 'child_groups'
            context['parent_group'] = parent_group
            context['child_groups'] = child_groups
        
        elif group_id:
            # Show players in group - use HourlyMetric for accurate data
            try:
                group = Group.objects.get(pk=group_id)
            except Group.DoesNotExist:
                context['error'] = _('Group not found')
                return render(request, 'admin/api/hierarchy_breakdown.html', context)
            # Get all descendant groups to include all players
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
            
            context['breakdown_type'] = 'cyclists'
            context['group'] = group
            context['cyclists'] = cyclists
    
    return render(request, 'admin/api/hierarchy_breakdown.html', context)


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

