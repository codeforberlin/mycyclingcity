# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    helpers.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
"""
Project: MyCyclingCity
Generation: AI-based

Shared helper functions for building group hierarchies and data structures.
Used by map, ranking, and leaderboard apps.
"""

from typing import List, Dict, Any, Optional
from django.db.models import QuerySet, Sum, Max, Q
from django.utils import timezone
from functools import reduce
from datetime import timedelta
import operator
import logging
from api.models import Group, Cyclist, CyclistDeviceCurrentMileage, HourlyMetric, YearEndSnapshot
from eventboard.models import Event, GroupEventStatus
from eventboard.utils import get_all_subgroup_ids
from iot.models import Device

logger = logging.getLogger(__name__)


def are_all_parents_visible(group: Group) -> bool:
    """
    Check if all parent groups in the hierarchy are visible.
    
    Args:
        group: The group to check.
    
    Returns:
        True if the group and all its parents are visible, False otherwise.
    """
    visited = set()
    current = group
    
    # First check the group itself
    if not current.is_visible:
        return False
    
    # Then check all parent groups recursively
    while current and current.parent_id:
        if current.id in visited:
            # Circular reference detected, break to avoid infinite loop
            break
        visited.add(current.id)
        
        # Load parent if not already loaded (select_related only loads direct parent)
        if not hasattr(current, 'parent') or current.parent is None:
            try:
                current.parent = Group.objects.get(id=current.parent_id)
            except Group.DoesNotExist:
                break
        
        # Move to parent and check if it's visible
        current = current.parent
        if current:
            if current.id in visited:
                break
            visited.add(current.id)
            if not current.is_visible:
                return False
    
    return True


def _get_latest_snapshot_date_for_groups(group_ids: List[int]) -> Dict[int, Optional[timezone.datetime]]:
    """
    Get the latest snapshot date for each group (considering all subgroups).
    
    Args:
        group_ids: List of group IDs to check
    
    Returns:
        Dictionary mapping group_id to latest snapshot_date (or None if no snapshot exists)
    """
    if not group_ids:
        return {}
    
    # For each group, find its TOP group and get the latest snapshot
    result: Dict[int, Optional[timezone.datetime]] = {}
    
    for group_id in group_ids:
        try:
            group = Group.objects.get(id=group_id)
        except Group.DoesNotExist:
            result[group_id] = None
            continue
        
        # Find TOP group
        top_group = group
        visited = set()
        while top_group.parent and top_group.id not in visited:
            visited.add(top_group.id)
            top_group = top_group.parent
        
        # Get all subgroup IDs for this TOP group
        all_subgroup_ids = get_all_subgroup_ids(top_group)
        all_subgroup_ids.append(top_group.id)
        
        # Find latest snapshot for this TOP group (not undone)
        latest_snapshot = YearEndSnapshot.objects.filter(
            group=top_group,
            is_undone=False
        ).order_by('-snapshot_date').first()
        
        if latest_snapshot:
            # Apply this snapshot date to all subgroups
            for sub_id in all_subgroup_ids:
                if sub_id in group_ids:
                    # Only set if not already set or if this is newer
                    if sub_id not in result or (result[sub_id] is None or latest_snapshot.snapshot_date > result[sub_id]):
                        result[sub_id] = latest_snapshot.snapshot_date
        else:
            # No snapshot, set to None for all subgroups
            for sub_id in all_subgroup_ids:
                if sub_id in group_ids and sub_id not in result:
                    result[sub_id] = None
    
    return result


def filter_metrics_by_snapshot(queryset: QuerySet, group_ids: List[int], field_name: str = 'group_at_time_id') -> QuerySet:
    """
    Filter HourlyMetric queryset to exclude metrics before latest snapshot date.
    
    This function applies snapshot filtering to a queryset by checking each group's
    latest snapshot date and only including metrics after that date.
    
    Args:
        queryset: HourlyMetric queryset to filter
        group_ids: List of group IDs to check for snapshots
        field_name: Field name to use for group filtering (default: 'group_at_time_id')
                   Use 'group_at_time_id' for group metrics, 'cyclist__groups__id' for cyclist metrics
    
    Returns:
        Filtered queryset with snapshot-aware filtering applied
    """
    if not group_ids:
        return queryset
    
    # Get snapshot dates for all groups
    snapshot_dates = _get_latest_snapshot_date_for_groups(group_ids)
    
    # Build Q objects for filtering
    # For each group, if it has a snapshot, only include metrics after that date
    q_objects = []
    
    for group_id in group_ids:
        snapshot_date = snapshot_dates.get(group_id)
        if snapshot_date:
            # Only include metrics after snapshot date for this group
            q_objects.append(
                Q(**{field_name: group_id, 'timestamp__gt': snapshot_date})
            )
        else:
            # No snapshot, include all metrics for this group
            q_objects.append(Q(**{field_name: group_id}))
    
    if q_objects:
        # Combine all Q objects with OR (metrics matching any group condition)
        return queryset.filter(reduce(operator.or_, q_objects))
    
    return queryset


def invalidate_cache_for_top_group(top_group: Group):
    """
    Invalidate all cache entries related to a TOP group and its subgroups.
    
    This function clears cache for:
    - Group totals (leaderboard)
    - Cyclist totals (ranking)
    - Device totals (ranking)
    - All subgroups and their descendants
    
    Args:
        top_group: The TOP group for which to invalidate cache
    """
    from django.core.cache import cache
    from eventboard.utils import get_all_subgroup_ids
    
    # Get all subgroup IDs (including TOP group itself)
    all_subgroup_ids = get_all_subgroup_ids(top_group)
    all_subgroup_ids.append(top_group.id)
    
    # Get all cyclists in these groups
    all_cyclist_ids = list(Cyclist.objects.filter(groups__id__in=all_subgroup_ids).values_list('id', flat=True).distinct())
    
    # Get all devices in these groups
    all_device_ids = list(Device.objects.filter(group__id__in=all_subgroup_ids).values_list('id', flat=True))
    
    # Invalidate group totals cache (leaderboard)
    # Cache keys follow pattern: 'leaderboard_group_totals_{group_ids}_{timestamp}_desc{flag}'
    # We need to clear all possible combinations, so we'll use a pattern-based approach
    # Since we can't easily list all cache keys, we'll clear by pattern matching
    # For simplicity, we'll clear all leaderboard caches (they'll be regenerated on next request)
    cache_patterns = [
        'leaderboard_group_totals_*',
        'ranking_cyclist_totals_*',
        'ranking_device_totals_*',
        'ranking_group_totals_*',
    ]
    
    # Django cache doesn't support pattern deletion directly, so we'll use a workaround:
    # Set a version number that changes, or clear specific known keys
    # For now, we'll clear the most common patterns by trying to delete known key formats
    
    # Clear cache for specific group IDs (most efficient approach)
    group_ids_str = "-".join(map(str, sorted(all_subgroup_ids)))
    now = timezone.now()
    
    # Try to clear common cache key patterns
    for hour_offset in range(24):  # Clear last 24 hours of cache
        timestamp = (now - timedelta(hours=hour_offset)).strftime("%Y%m%d%H")
        for desc_flag in [0, 1]:
            cache_key = f'leaderboard_group_totals_{group_ids_str}_{timestamp}_desc{desc_flag}'
            cache.delete(cache_key)
    
    # Clear cyclist totals cache
    if all_cyclist_ids:
        cyclist_ids_str = "-".join(map(str, sorted(all_cyclist_ids)))
        for hour_offset in range(24):
            timestamp = (now - timedelta(hours=hour_offset)).strftime("%Y%m%d%H")
            cache_key = f'ranking_cyclist_totals_{cyclist_ids_str}_{timestamp}'
            cache.delete(cache_key)
    
    # Clear device totals cache
    if all_device_ids:
        device_ids_str = "-".join(map(str, sorted(all_device_ids)))
        for hour_offset in range(24):
            timestamp = (now - timedelta(hours=hour_offset)).strftime("%Y%m%d%H")
            cache_key = f'ranking_device_totals_{device_ids_str}_{timestamp}'
            cache.delete(cache_key)
    
    # Clear group totals cache (from helpers.py)
    for hour_offset in range(24):
        timestamp = (now - timedelta(hours=hour_offset)).strftime("%Y%m%d%H")
        cache_key = f'ranking_group_totals_{group_ids_str}_{timestamp}'
        cache.delete(cache_key)
    
    logger.info(f"Invalidated cache for TOP group '{top_group.name}' (ID: {top_group.id}) and {len(all_subgroup_ids)} subgroups")


def filter_cyclist_metrics_by_snapshot(queryset: QuerySet, cyclist_ids: List[int]) -> QuerySet:
    """
    Filter HourlyMetric queryset for cyclists, excluding metrics before latest snapshot date.
    
    This function determines snapshot dates based on the groups each cyclist belongs to,
    then filters metrics accordingly.
    
    Args:
        queryset: HourlyMetric queryset to filter (should already be filtered by cyclist)
        cyclist_ids: List of cyclist IDs
    
    Returns:
        Filtered queryset with snapshot-aware filtering applied
    """
    if not cyclist_ids:
        return queryset
    
    # Get groups for each cyclist
    cyclist_groups_map: Dict[int, List[int]] = {}
    for cyclist in Cyclist.objects.filter(id__in=cyclist_ids):
        cyclist_groups_map[cyclist.id] = list(cyclist.groups.values_list('id', flat=True))
    
    # Get snapshot dates for all groups
    all_group_ids = set()
    for group_ids in cyclist_groups_map.values():
        all_group_ids.update(group_ids)
    
    snapshot_dates = _get_latest_snapshot_date_for_groups(list(all_group_ids))
    
    # For each cyclist, find the latest snapshot date from their groups
    cyclist_snapshot_dates: Dict[int, Optional[timezone.datetime]] = {}
    for cyclist_id, group_ids in cyclist_groups_map.items():
        latest_date = None
        for group_id in group_ids:
            group_date = snapshot_dates.get(group_id)
            if group_date and (latest_date is None or group_date > latest_date):
                latest_date = group_date
        cyclist_snapshot_dates[cyclist_id] = latest_date
    
    # Build Q objects for filtering
    q_objects = []
    for cyclist_id in cyclist_ids:
        snapshot_date = cyclist_snapshot_dates.get(cyclist_id)
        if snapshot_date:
            # Only include metrics after snapshot date for this cyclist
            q_objects.append(
                Q(cyclist_id=cyclist_id, timestamp__gt=snapshot_date)
            )
        else:
            # No snapshot, include all metrics for this cyclist
            q_objects.append(Q(cyclist_id=cyclist_id))
    
    if q_objects:
        return queryset.filter(reduce(operator.or_, q_objects))
    
    return queryset


def _calculate_cyclist_totals_from_metrics(cyclists: List[Cyclist], use_cache: bool = True) -> Dict[int, float]:
    """
    Calculate total kilometers for cyclists from HourlyMetric.
    
    This ensures ranking tables use the same data source as the leaderboard.
    Results are cached for 55 seconds (just under cronjob interval of 60s) to improve performance.
    
    Takes into account year-end snapshots: only metrics after the latest snapshot date are counted.
    
    Args:
        cyclists: List of Cyclist objects to calculate totals for
        use_cache: Whether to use cache (default: True)
    
    Returns:
        Dictionary mapping cyclist_id to total kilometers
    """
    cyclist_ids = [c.id for c in cyclists]
    if not cyclist_ids:
        return {}
    
    # Sanitize cyclist IDs for cache key
    cyclist_ids_str = "-".join(map(str, sorted(cyclist_ids)))
    
    # Try to get from cache first
    cache_key = f'ranking_cyclist_totals_{cyclist_ids_str}_{timezone.now().strftime("%Y%m%d%H")}'
    if use_cache:
        from django.core.cache import cache
        cached_result = cache.get(cache_key)
        if cached_result is not None:
            return cached_result
    
    # Get groups for each cyclist to find snapshot dates
    cyclist_groups_map: Dict[int, List[int]] = {}
    for cyclist in cyclists:
        cyclist_groups_map[cyclist.id] = list(cyclist.groups.values_list('id', flat=True))
    
    # Get snapshot dates for all groups
    all_group_ids = set()
    for group_ids in cyclist_groups_map.values():
        all_group_ids.update(group_ids)
    
    snapshot_dates = _get_latest_snapshot_date_for_groups(list(all_group_ids))
    
    # For each cyclist, find the latest snapshot date from their groups
    cyclist_snapshot_dates: Dict[int, Optional[timezone.datetime]] = {}
    for cyclist_id, group_ids in cyclist_groups_map.items():
        latest_date = None
        for group_id in group_ids:
            group_date = snapshot_dates.get(group_id)
            if group_date and (latest_date is None or group_date > latest_date):
                latest_date = group_date
        cyclist_snapshot_dates[cyclist_id] = latest_date
    
    # Calculate TOTAL: Sum of HourlyMetric entries after the latest snapshot date for each cyclist
    result: Dict[int, float] = {}
    
    for cyclist_id in cyclist_ids:
        snapshot_date = cyclist_snapshot_dates.get(cyclist_id)
        
        # Build query filter
        metric_filter = {'cyclist_id': cyclist_id}
        if snapshot_date:
            metric_filter['timestamp__gt'] = snapshot_date
        
        total_metrics = HourlyMetric.objects.filter(**metric_filter).aggregate(
            total=Sum('distance_km')
        )
        
        result[cyclist_id] = float(total_metrics['total'] or 0.0)
    
    # Cache the result for 55 seconds
    if use_cache:
        from django.core.cache import cache
        cache.set(cache_key, result, 55)
    
    return result


def _calculate_device_totals_from_metrics(devices: List[Device], use_cache: bool = True) -> Dict[int, float]:
    """
    Calculate total kilometers for devices from HourlyMetric.
    
    This ensures ranking tables use the same data source as the leaderboard.
    Results are cached for 55 seconds (just under cronjob interval of 60s) to improve performance.
    
    Takes into account year-end snapshots: only metrics after the latest snapshot date are counted.
    
    Args:
        devices: List of Device objects to calculate totals for
        use_cache: Whether to use cache (default: True)
    
    Returns:
        Dictionary mapping device_id to total kilometers
    """
    device_ids = [d.id for d in devices]
    if not device_ids:
        return {}
    
    # Sanitize device IDs for cache key
    device_ids_str = "-".join(map(str, sorted(device_ids)))
    
    # Try to get from cache first
    cache_key = f'ranking_device_totals_{device_ids_str}_{timezone.now().strftime("%Y%m%d%H")}'
    if use_cache:
        from django.core.cache import cache
        cached_result = cache.get(cache_key)
        if cached_result is not None:
            return cached_result
    
    # Get groups for each device to find snapshot dates
    device_groups_map: Dict[int, Optional[int]] = {}
    for device in devices:
        device_groups_map[device.id] = device.group_id if device.group else None
    
    # Get snapshot dates for all groups
    all_group_ids = [gid for gid in device_groups_map.values() if gid is not None]
    snapshot_dates = _get_latest_snapshot_date_for_groups(all_group_ids)
    
    # Calculate TOTAL: Sum of HourlyMetric entries after the latest snapshot date for each device
    result: Dict[int, float] = {}
    
    for device_id in device_ids:
        group_id = device_groups_map.get(device_id)
        snapshot_date = snapshot_dates.get(group_id) if group_id else None
        
        # Build query filter
        metric_filter = {'device_id': device_id}
        if snapshot_date:
            metric_filter['timestamp__gt'] = snapshot_date
        
        total_metrics = HourlyMetric.objects.filter(**metric_filter).aggregate(
            total=Sum('distance_km')
        )
        
        result[device_id] = float(total_metrics['total'] or 0.0)
    
    # Cache the result for 55 seconds
    if use_cache:
        from django.core.cache import cache
        cache.set(cache_key, result, 55)
    
    return result


def _calculate_group_totals_from_metrics(groups: List[Group], use_cache: bool = True) -> Dict[int, float]:
    """
    Calculate total kilometers for groups from HourlyMetric.
    
    This ensures ranking tables use the same data source as the leaderboard.
    Results are cached for 55 seconds (just under cronjob interval of 60s) to improve performance.
    
    Takes into account year-end snapshots: only metrics after the latest snapshot date are counted.
    
    Args:
        groups: List of Group objects to calculate totals for
        use_cache: Whether to use cache (default: True)
    
    Returns:
        Dictionary mapping group_id to total kilometers
    """
    group_ids = [g.id for g in groups]
    if not group_ids:
        return {}
    
    # Sanitize group IDs for cache key
    group_ids_str = "-".join(map(str, sorted(group_ids)))
    
    # Try to get from cache first
    cache_key = f'ranking_group_totals_{group_ids_str}_{timezone.now().strftime("%Y%m%d%H")}'
    if use_cache:
        from django.core.cache import cache
        cached_result = cache.get(cache_key)
        if cached_result is not None:
            return cached_result
    
    # Get snapshot dates for all groups
    snapshot_dates = _get_latest_snapshot_date_for_groups(group_ids)
    
    # Calculate TOTAL: Sum of HourlyMetric entries after the latest snapshot date for each group
    result: Dict[int, float] = {}
    
    for group_id in group_ids:
        snapshot_date = snapshot_dates.get(group_id)
        
        # Build query filter
        metric_filter = {'group_at_time_id': group_id}
        if snapshot_date:
            metric_filter['timestamp__gt'] = snapshot_date
        
        total_metrics = HourlyMetric.objects.filter(**metric_filter).aggregate(
            total=Sum('distance_km')
        )
        
        result[group_id] = float(total_metrics['total'] or 0.0)
    
    # Propagate values to parent groups (hierarchical aggregation)
    # Process from leaf groups upward to ensure correct aggregation
    for group in groups:
        if group.id in result and group.parent and group.parent.id in group_ids:
            parent_id = group.parent.id
            if parent_id not in result:
                result[parent_id] = 0.0
            result[parent_id] += result[group.id]
    
    # Initialize missing groups with 0.0
    for group_id in group_ids:
        if group_id not in result:
            result[group_id] = 0.0
    
    # Cache the result for 55 seconds
    if use_cache:
        from django.core.cache import cache
        cache.set(cache_key, result, 55)
    
    return result


def build_group_hierarchy(
    target_group: Optional[Group] = None,
    kiosk: bool = False,
    show_cyclists: bool = True
) -> List[Dict[str, Any]]:
    """
    Build a hierarchical data structure of groups with their members and subgroups.
    
    Args:
        target_group: Optional specific group to filter by.
        kiosk: Whether in kiosk mode (filters groups with distance_total > 0).
        show_cyclists: Whether to include cyclist data in the hierarchy.
    
    Returns:
        List of dictionaries containing group hierarchy data.
    """
    group_filter = {'is_visible': True}
    
    if target_group:
        parent_groups = Group.objects.filter(id=target_group.id, **group_filter).order_by('name')
    else:
        parent_groups = Group.objects.filter(parent__isnull=True, **group_filter).order_by('name')
        # In kiosk mode, only show parent groups with distance_total > 0
        if kiosk:
            parent_groups = parent_groups.filter(distance_total__gt=0)
    
    # Calculate group totals from HourlyMetric for all groups at once
    all_groups_list = list(parent_groups)
    # Also collect all subgroups for calculation
    for p_group in parent_groups:
        all_groups_list.extend(list(p_group.children.filter(is_visible=True)))
    
    group_totals = _calculate_group_totals_from_metrics(all_groups_list, use_cache=True)
    
    hierarchy = []
    for p_group in parent_groups:
        p_filter = {'is_visible': True}
        if kiosk:
            p_filter['distance_total__gt'] = 0
        
        direct_members = []
        if show_cyclists:
            direct_qs = p_group.members.filter(**p_filter).select_related(
                'cyclistdevicecurrentmileage'
            )
            direct_members_list = list(direct_qs)
            
            # Calculate totals from HourlyMetric for all cyclists at once
            cyclist_totals = _calculate_cyclist_totals_from_metrics(direct_members_list, use_cache=True)
            
            direct_members = []
            for m in direct_members_list:
                session_km = 0
                try:
                    if hasattr(m, 'cyclistdevicecurrentmileage') and m.cyclistdevicecurrentmileage:
                        session_km = float(m.cyclistdevicecurrentmileage.cumulative_mileage)
                except (AttributeError, ValueError, TypeError):
                    pass
                # Use total from HourlyMetric instead of distance_total from model
                total_km = cyclist_totals.get(m.id, 0.0)
                direct_members.append({
                    'name': m.user_id,
                    'km': round(total_km, 3),
                    'session_km': round(session_km, 3)
                })
            
            # Sort by km (from HourlyMetric) descending
            direct_members = sorted(direct_members, key=lambda x: x['km'], reverse=True)
        
        # Filter subgroups: in kiosk mode, only show groups with distance_total > 0
        # Sort by name to match the group menu sorting
        subgroups_qs = p_group.children.filter(is_visible=True).order_by('name')
        if kiosk:
            subgroups_qs = subgroups_qs.filter(distance_total__gt=0)
        
        subgroups_data = []
        for sub in subgroups_qs:
            sub_member_data = []
            if show_cyclists:
                m_qs = sub.members.filter(**p_filter).select_related(
                    'cyclistdevicecurrentmileage'
                )
                sub_members_list = list(m_qs)
                
                # Calculate totals from HourlyMetric for all cyclists at once
                cyclist_totals = _calculate_cyclist_totals_from_metrics(sub_members_list, use_cache=True)
                
                sub_member_data = []
                for m in sub_members_list:
                    session_km = 0
                    try:
                        if hasattr(m, 'cyclistdevicecurrentmileage') and m.cyclistdevicecurrentmileage:
                            session_km = float(m.cyclistdevicecurrentmileage.cumulative_mileage)
                    except (AttributeError, ValueError, TypeError):
                        pass
                    # Use total from HourlyMetric instead of distance_total from model
                    total_km = cyclist_totals.get(m.id, 0.0)
                    sub_member_data.append({
                        'name': m.user_id,
                        'km': round(total_km, 3),
                        'session_km': round(session_km, 3)
                    })
                
                # Sort by km (from HourlyMetric) descending
                sub_member_data = sorted(sub_member_data, key=lambda x: x['km'], reverse=True)
            # Use total from HourlyMetric instead of distance_total from model
            sub_total_km = group_totals.get(sub.id, 0.0)
            # In kiosk mode, only add subgroup if it has distance_total > 0 or has members with distance_total > 0
            if not kiosk or (sub_total_km > 0 or len(sub_member_data) > 0):
                subgroups_data.append({
                    'id': sub.id,  # Add subgroup ID for filtering
                    'name': sub.name,
                    'km': round(sub_total_km, 3),
                    'members': sub_member_data
                })
        
        # Sort subgroups by distance_total (sorted descending) - no limit
        subgroups_data = sorted(subgroups_data, key=lambda x: x['km'], reverse=True)
        
        # Use total from HourlyMetric instead of distance_total from model
        p_group_total_km = group_totals.get(p_group.id, 0.0)
        if not kiosk or (p_group_total_km > 0 or subgroups_data or direct_members):
            hierarchy.append({
                'id': p_group.id,  # Add group ID for filtering
                'name': p_group.name,
                'km': round(p_group_total_km, 3),
                'direct_members': direct_members,
                'subgroups': subgroups_data
            })
    
    # Sort hierarchy by km (from HourlyMetric) descending - no limit
    # This matches the mobile version sorting behavior
    hierarchy = sorted(hierarchy, key=lambda x: x['km'], reverse=True)
    
    return hierarchy


def build_events_data(kiosk: bool = False) -> List[Dict[str, Any]]:
    """
    Build event data structure for display.
    
    Args:
        kiosk: Whether in kiosk mode (filters groups with distance > 0).
    
    Returns:
        List of dictionaries containing event data.
    """
    from django.utils import timezone
    # Event is already imported at top of file from eventboard.models
    
    now = timezone.now()
    active_events = Event.objects.filter(is_active=True, is_visible_on_map=True)
    # Filter by should_be_displayed() instead of is_currently_active()
    # This allows showing events after end_time until hide_after_date
    active_events = [e for e in active_events if e.should_be_displayed()]
    events_data = []
    
    for event in active_events:
        # Get all groups participating in this event
        event_groups = []
        for status in event.group_statuses.select_related('group').all():
            # In kiosk mode, only show groups with current_distance_km > 0
            if kiosk and float(status.current_distance_km) <= 0:
                continue
            event_groups.append({
                'name': status.group.name,
                'km': round(float(status.current_distance_km), 3),
                'group_id': status.group.id
            })
        # In kiosk mode, only add event if it has groups with distance > 0
        if event_groups and (not kiosk or len(event_groups) > 0):
            # Sort groups by distance (descending) and limit to top 10
            event_groups_sorted = sorted(event_groups, key=lambda x: x['km'], reverse=True)[:10]
            # Calculate total kilometers for this event (from all groups, not just top 10)
            total_km = sum(g['km'] for g in event_groups)
            # Check if event has ended (end_time reached)
            is_ended = event.end_time and now > event.end_time
            events_data.append({
                'id': event.id,
                'name': event.name,
                'event_type': event.get_event_type_display(),
                'description': event.description or '',
                'start_time': event.start_time,
                'end_time': event.end_time,
                'total_km': round(total_km, 3),
                'is_ended': is_ended,
                'groups': event_groups_sorted
            })
    
    return events_data


