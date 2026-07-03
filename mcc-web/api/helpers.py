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


def get_external_display_settings_context() -> Dict[str, Any]:
    """Return admin-controlled km display flags for external GUIs."""
    from api.models import ExternalDisplaySettings

    settings_obj = ExternalDisplaySettings.get_settings()
    return {
        'show_km_in_leaderboard_footer': settings_obj.show_km_in_leaderboard_footer,
        'show_km_in_ranking_headers': settings_obj.show_km_in_ranking_headers,
        'km_display_decimals': settings_obj.km_display_decimals,
    }


def sum_display_totals_from_groups_data(groups_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Sum Velos and km from leaderboard-style group dicts (filtered view).

    Uses the same per-group values already prepared for the UI (HourlyMetric-based
    where applicable).
    """
    return {
        'total_velos': sum(int(g.get('velos_total', 0) or 0) for g in groups_data),
        'total_km': sum(float(g.get('distance_total', 0) or 0) for g in groups_data),
    }


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


def _cyclist_member_entry(
    cyclist: Cyclist,
    cyclist_totals: Dict[int, float],
    cyclist_velos_totals: Dict[int, int],
) -> Dict[str, Any]:
    """Build a single cyclist dict for group hierarchy tables."""
    total_km = cyclist_totals.get(cyclist.id, 0.0)
    # Sum of HourlyMetric.velos (mcc_worker syncs active sessions periodically).
    # Do not add session_velos here — after worker sync the current hour is already included.
    total_velos = int(cyclist_velos_totals.get(cyclist.id, 0))
    session_velos = int(get_cyclist_session_velos(cyclist))
    return {
        'name': cyclist.user_id,
        'km': round(total_km, 3),
        'velos': total_velos,
        'session_velos': session_velos,
    }


def _group_velos_for_ranking(
    _group: Group,
    member_entries: List[Dict[str, Any]],
    child_entries: Optional[List[Dict[str, Any]]] = None,
    group_metric_velos: int = 0,
) -> int:
    """
    Velos total for map/ranking group rows from HourlyMetric sums.

    Leaf groups: sum of member metric totals, or group_at_time metrics when members
    are not loaded (e.g. show_cyclists=False).
    Parent groups: sum of visible child group totals (or direct members if no children).
    """
    members_velos = sum(int(m.get('velos', 0)) for m in member_entries)
    children_velos = sum(int(c.get('velos', 0)) for c in (child_entries or []))
    leaf_velos = max(members_velos, int(group_metric_velos or 0))

    if child_entries is not None:
        if child_entries:
            return children_velos
        return leaf_velos

    return leaf_velos


def _group_km_for_ranking(
    _group: Group,
    member_entries: List[Dict[str, Any]],
    child_entries: Optional[List[Dict[str, Any]]] = None,
    group_metric_km: float = 0.0,
) -> float:
    """Km total for map/ranking group rows (HourlyMetric-based, mirrors Velos logic)."""
    members_km = sum(float(m.get('km', 0) or 0) for m in member_entries)
    children_km = sum(float(c.get('km', 0) or 0) for c in (child_entries or []))
    leaf_km = max(members_km, float(group_metric_km or 0))

    if child_entries is not None:
        if child_entries:
            return children_km
        return leaf_km

    return leaf_km


def _members_for_group(
    group: Group,
    member_filter: Dict[str, Any],
    show_cyclists: bool,
) -> List[Dict[str, Any]]:
    """Return sorted cyclist member entries for a group."""
    if not show_cyclists:
        return []
    members_qs = group.members.filter(**member_filter).select_related(
        'cyclistdevicecurrentmileage',
        'cyclistdevicecurrentmileage__device',
        'cyclistdevicecurrentmileage__device__configuration',
    )
    members_list = list(members_qs)
    cyclist_totals = _calculate_cyclist_totals_from_metrics(members_list, use_cache=True)
    cyclist_velos_totals = _calculate_cyclist_velos_from_metrics(members_list, use_cache=True)
    members = [
        _cyclist_member_entry(m, cyclist_totals, cyclist_velos_totals)
        for m in members_list
    ]
    return sorted(members, key=lambda x: x['velos'], reverse=True)


def build_hierarchy_from_parent_groups(
    parent_groups,
    kiosk: bool = False,
    show_cyclists: bool = True,
) -> List[Dict[str, Any]]:
    """
    Build hierarchy data from a parent-group queryset (map/ranking shared helper).

    All Velos totals come from HourlyMetric (synced by mcc_worker for active sessions).
    Parent groups: sum of child group metric totals.
    """
    group_filter = {'is_visible': True}
    member_filter = {'is_visible': True}
    if kiosk:
        member_filter['distance_total__gt'] = 0

    hierarchy = []
    groups_for_metrics: List[Group] = []
    for p_group in parent_groups:
        groups_for_metrics.append(p_group)
        groups_for_metrics.extend(list(p_group.children.filter(**group_filter)))
    group_velos_by_id = _calculate_group_velos_from_metrics(groups_for_metrics, use_cache=True)
    group_km_by_id = _calculate_group_totals_from_metrics(groups_for_metrics, use_cache=True)

    for p_group in parent_groups:
        direct_members = _members_for_group(p_group, member_filter, show_cyclists)

        subgroups_qs = p_group.children.filter(**group_filter).order_by('name')

        subgroups_data = []
        for sub in subgroups_qs:
            sub_member_data = _members_for_group(sub, member_filter, show_cyclists)
            sub_velos = _group_velos_for_ranking(
                sub,
                sub_member_data,
                group_metric_velos=group_velos_by_id.get(sub.id, 0),
            )
            sub_km = _group_km_for_ranking(
                sub,
                sub_member_data,
                group_metric_km=group_km_by_id.get(sub.id, 0.0),
            )
            if not kiosk or (sub_velos > 0 or sub_member_data):
                subgroups_data.append({
                    'id': sub.id,
                    'name': sub.name,
                    'km': round(float(sub_km), 3),
                    'velos': sub_velos,
                    'members': sub_member_data,
                })

        subgroups_data = sorted(subgroups_data, key=lambda x: x['velos'], reverse=True)
        p_velos = _group_velos_for_ranking(
            p_group,
            direct_members,
            child_entries=subgroups_data,
            group_metric_velos=group_velos_by_id.get(p_group.id, 0),
        )
        p_km = _group_km_for_ranking(
            p_group,
            direct_members,
            child_entries=subgroups_data,
            group_metric_km=group_km_by_id.get(p_group.id, 0.0),
        )
        if not kiosk or (p_velos > 0 or subgroups_data or direct_members):
            hierarchy.append({
                'id': p_group.id,
                'name': p_group.name,
                'km': round(float(p_km), 3),
                'velos': p_velos,
                'direct_members': direct_members,
                'subgroups': subgroups_data,
            })

    return sorted(hierarchy, key=lambda x: x['velos'], reverse=True)


def build_group_hierarchy(
    target_group: Optional[Group] = None,
    kiosk: bool = False,
    show_cyclists: bool = True
) -> List[Dict[str, Any]]:
    """
    Build a hierarchical data structure of groups with their members and subgroups.
    
    Args:
        target_group: Optional specific group to filter by.
        kiosk: Whether in kiosk mode (hides groups with zero metric Velos).
        show_cyclists: Whether to include cyclist data in the hierarchy.
    
    Returns:
        List of dictionaries containing group hierarchy data.
    """
    group_filter = {'is_visible': True}
    
    if target_group:
        parent_groups = Group.objects.filter(id=target_group.id, **group_filter).order_by('name')
    else:
        parent_groups = Group.objects.filter(parent__isnull=True, **group_filter).order_by('name')

    return build_hierarchy_from_parent_groups(
        parent_groups,
        kiosk=kiosk,
        show_cyclists=show_cyclists,
    )


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
            # In kiosk mode, only show groups with current_velos > 0
            if kiosk and int(status.current_velos) <= 0:
                continue
            event_groups.append({
                'name': status.group.name,
                'velos': int(status.current_velos),
                'group_id': status.group.id
            })
        # In kiosk mode, only add event if it has groups with Velos > 0
        if event_groups and (not kiosk or len(event_groups) > 0):
            event_groups_sorted = sorted(event_groups, key=lambda x: x['velos'], reverse=True)[:10]
            total_velos = sum(g['velos'] for g in event_groups)
            is_ended = event.end_time and now > event.end_time
            events_data.append({
                'id': event.id,
                'name': event.name,
                'event_type': event.get_event_type_display(),
                'description': event.description or '',
                'start_time': event.start_time,
                'end_time': event.end_time,
                'total_velos': total_velos,
                'is_ended': is_ended,
                'groups': event_groups_sorted
            })
    
    return events_data


def _get_cyclist_velos_balance(cyclist: Cyclist) -> int:
    """Return redeemable Velos balance for a cyclist."""
    return int(cyclist.velos_balance or 0)


def get_cyclist_session_velos(cyclist: Cyclist) -> int:
    """Velos earned in the cyclist's active device session (not yet redeemed)."""
    from api.velos import calculate_session_velos

    try:
        session = cyclist.cyclistdevicecurrentmileage
    except CyclistDeviceCurrentMileage.DoesNotExist:
        return 0
    if not session or not session.cumulative_mileage:
        return 0
    return calculate_session_velos(session.cumulative_mileage, session.device)


def get_cyclist_session_km(cyclist: Cyclist):
    """Return cumulative session distance in km for the cyclist's active device session."""
    from decimal import Decimal

    try:
        session = cyclist.cyclistdevicecurrentmileage
    except CyclistDeviceCurrentMileage.DoesNotExist:
        return Decimal('0.00000')
    return session.cumulative_mileage or Decimal('0.00000')


def snapshot_session_velos(cyclist: Cyclist) -> int:
    """Snapshot session Velos before ending a device session (e.g. game round stop)."""
    return get_cyclist_session_velos(cyclist)


def get_group_velos_ledger(groups: List[Group]) -> Dict[int, int]:
    """
    Return permanent group Velos ledger totals (leaderboard ranking source).

    Uses Group.velos_total, not the sum of member velos_balance values.
    """
    return {group.id: int(group.velos_total or 0) for group in groups}


def _calculate_cyclist_velos_from_metrics(
    cyclists: List[Cyclist],
    use_cache: bool = True,
) -> Dict[int, int]:
    """Sum HourlyMetric.velos per cyclist (archival/historical totals)."""
    cyclist_ids = [c.id for c in cyclists]
    if not cyclist_ids:
        return {}

    cyclist_ids_str = "-".join(map(str, sorted(cyclist_ids)))
    cache_key = f'ranking_cyclist_velos_{cyclist_ids_str}_{timezone.now().strftime("%Y%m%d%H")}'
    if use_cache:
        from django.core.cache import cache
        cached_result = cache.get(cache_key)
        if cached_result is not None:
            return cached_result

    cyclist_groups_map: Dict[int, List[int]] = {}
    for cyclist in cyclists:
        cyclist_groups_map[cyclist.id] = list(cyclist.groups.values_list('id', flat=True))

    all_group_ids = set()
    for group_ids in cyclist_groups_map.values():
        all_group_ids.update(group_ids)

    snapshot_dates = _get_latest_snapshot_date_for_groups(list(all_group_ids))
    cyclist_snapshot_dates: Dict[int, Optional[timezone.datetime]] = {}
    for cyclist_id, group_ids in cyclist_groups_map.items():
        latest_date = None
        for group_id in group_ids:
            group_date = snapshot_dates.get(group_id)
            if group_date and (latest_date is None or group_date > latest_date):
                latest_date = group_date
        cyclist_snapshot_dates[cyclist_id] = latest_date

    result: Dict[int, int] = {}
    for cyclist_id in cyclist_ids:
        snapshot_date = cyclist_snapshot_dates.get(cyclist_id)
        metric_filter = {'cyclist_id': cyclist_id}
        if snapshot_date:
            metric_filter['timestamp__gt'] = snapshot_date
        total_metrics = HourlyMetric.objects.filter(**metric_filter).aggregate(
            total=Sum('velos'),
        )
        result[cyclist_id] = int(total_metrics['total'] or 0)

    if use_cache:
        from django.core.cache import cache
        cache.set(cache_key, result, 55)

    return result


def _calculate_group_velos_from_metrics(
    groups: List[Group],
    use_cache: bool = True,
) -> Dict[int, int]:
    """Sum HourlyMetric.velos by group_at_time (historical group attribution)."""
    group_ids = [g.id for g in groups]
    if not group_ids:
        return {}

    group_ids_str = "-".join(map(str, sorted(group_ids)))
    cache_key = f'ranking_group_velos_{group_ids_str}_{timezone.now().strftime("%Y%m%d%H")}'
    if use_cache:
        from django.core.cache import cache
        cached_result = cache.get(cache_key)
        if cached_result is not None:
            return cached_result

    snapshot_dates = _get_latest_snapshot_date_for_groups(group_ids)
    result: Dict[int, int] = {}

    for group_id in group_ids:
        snapshot_date = snapshot_dates.get(group_id)
        metric_filter = {'group_at_time_id': group_id}
        if snapshot_date:
            metric_filter['timestamp__gt'] = snapshot_date
        total_metrics = HourlyMetric.objects.filter(**metric_filter).aggregate(
            total=Sum('velos'),
        )
        result[group_id] = int(total_metrics['total'] or 0)

    for group in groups:
        if group.id in result and group.parent and group.parent.id in group_ids:
            parent_id = group.parent.id
            result[parent_id] = result.get(parent_id, 0) + result[group.id]

    for group_id in group_ids:
        result.setdefault(group_id, 0)

    if use_cache:
        from django.core.cache import cache
        cache.set(cache_key, result, 55)

    return result


def _calculate_group_velos_periods(
    groups: List[Group],
    now: Optional[timezone.datetime] = None,
    use_cache: bool = True,
) -> Dict[int, Dict[str, int]]:
    """
    Aggregate HourlyMetric.velos per group for total/daily/weekly/monthly/yearly windows.
    """
    if now is None:
        now = timezone.now()

    group_ids = [g.id for g in groups]
    if not group_ids:
        return {}

    group_ids_str = "-".join(map(str, sorted(group_ids)))
    cache_key = f'leaderboard_group_velos_{group_ids_str}_{now.strftime("%Y%m%d%H")}'
    if use_cache:
        from django.core.cache import cache
        cached_result = cache.get(cache_key)
        if cached_result is not None:
            return cached_result

    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    days_since_monday = now.weekday()
    week_start = (now - timedelta(days=days_since_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    year_start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)

    snapshot_dates = _get_latest_snapshot_date_for_groups(group_ids)
    result: Dict[int, Dict[str, int]] = {
        gid: {'total': 0, 'daily': 0, 'weekly': 0, 'monthly': 0, 'yearly': 0}
        for gid in group_ids
    }

    period_filters = {
        'total': {},
        'daily': {'timestamp__gte': today_start},
        'weekly': {'timestamp__gte': week_start},
        'monthly': {'timestamp__gte': month_start},
        'yearly': {'timestamp__gte': year_start},
    }

    for group_id in group_ids:
        snapshot_date = snapshot_dates.get(group_id)
        for period_name, extra_filter in period_filters.items():
            metric_filter = {'group_at_time_id': group_id, **extra_filter}
            if snapshot_date:
                metric_filter['timestamp__gt'] = snapshot_date
            total_metrics = HourlyMetric.objects.filter(**metric_filter).aggregate(
                total=Sum('velos'),
            )
            result[group_id][period_name] = int(total_metrics['total'] or 0)

    _propagate_group_velos_periods_to_parents(groups, result)

    if use_cache:
        from django.core.cache import cache
        cache.set(cache_key, result, 55)

    return result


def _propagate_group_velos_periods_to_parents(
    groups: List[Group],
    result: Dict[int, Dict[str, int]],
) -> None:
    """Roll up leaf-group HourlyMetric Velos totals to parent groups in *result*."""
    period_keys = ('total', 'daily', 'weekly', 'monthly', 'yearly')

    def propagate_to_parents(group_id: int, visited: Optional[set] = None) -> None:
        if visited is None:
            visited = set()
        if group_id in visited:
            return
        visited.add(group_id)

        for group in groups:
            if group.id != group_id or not group.parent:
                continue
            parent_id = group.parent.id
            if group_id not in result or parent_id not in result:
                continue
            for period_name in period_keys:
                result[parent_id][period_name] += result[group_id][period_name]
            propagate_to_parents(parent_id, visited)

    for group in groups:
        if group.id in result:
            propagate_to_parents(group.id)


def get_cyclist_by_identifier(identifier: str) -> Optional[Cyclist]:
    """Resolve a cyclist by user_id or id_tag (case-insensitive)."""
    from django.db.models import Q

    try:
        return Cyclist.objects.get(
            Q(user_id__iexact=identifier) | Q(id_tag__iexact=identifier)
        )
    except Cyclist.DoesNotExist:
        return None


def _cyclist_effective_snapshot_start(cyclist: Cyclist) -> Optional[timezone.datetime]:
    group_ids = list(cyclist.groups.values_list('id', flat=True))
    if not group_ids:
        return None
    snapshot_dates = _get_latest_snapshot_date_for_groups(group_ids)
    latest_date = None
    for group_id in group_ids:
        group_date = snapshot_dates.get(group_id)
        if group_date and (latest_date is None or group_date > latest_date):
            latest_date = group_date
    return latest_date


def get_cyclist_velos_total(cyclist: Cyclist, use_cache: bool = False) -> int:
    """Lifetime Velos from HourlyMetric (respecting year-end snapshots)."""
    totals = _calculate_cyclist_velos_from_metrics([cyclist], use_cache=use_cache)
    return int(totals.get(cyclist.id, 0))


def get_cyclist_velos_period(
    cyclist: Cyclist,
    start_dt: timezone.datetime,
    end_dt: timezone.datetime,
) -> int:
    """Sum HourlyMetric.velos for a cyclist in a date range plus overlapping session."""
    period_velos = HourlyMetric.objects.filter(
        cyclist=cyclist,
        timestamp__gte=start_dt,
        timestamp__lte=end_dt,
        group_at_time__isnull=False,
    ).aggregate(total=Sum('velos'))['total'] or 0

    try:
        session = cyclist.cyclistdevicecurrentmileage
    except CyclistDeviceCurrentMileage.DoesNotExist:
        return int(period_velos)

    if (
        session
        and session.cumulative_mileage
        and session.last_activity
        and start_dt <= session.last_activity <= end_dt
        and (not session.start_time or session.start_time <= end_dt)
    ):
        period_velos += get_cyclist_session_velos(cyclist)

    return int(period_velos)


def get_cyclist_velos_daily(cyclist: Cyclist, now: Optional[timezone.datetime] = None) -> int:
    """Velos earned today (metrics + active session)."""
    if now is None:
        now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    snapshot_date = _cyclist_effective_snapshot_start(cyclist)
    effective_start = max(today_start, snapshot_date) if snapshot_date else today_start

    daily_velos = HourlyMetric.objects.filter(
        cyclist=cyclist,
        timestamp__gte=effective_start,
        group_at_time__isnull=False,
    ).aggregate(total=Sum('velos'))['total'] or 0

    try:
        session = cyclist.cyclistdevicecurrentmileage
    except CyclistDeviceCurrentMileage.DoesNotExist:
        return int(daily_velos)

    if (
        session
        and session.cumulative_mileage
        and session.last_activity
        and session.last_activity >= today_start
    ):
        daily_velos += get_cyclist_session_velos(cyclist)

    return int(daily_velos)


def build_cyclist_velos_api_fields(
    cyclist: Cyclist,
    *,
    include_session: bool = False,
    include_daily: bool = False,
    period_start: Optional[timezone.datetime] = None,
    period_end: Optional[timezone.datetime] = None,
) -> Dict[str, int]:
    """Standard Velos fields for cyclist API responses."""
    fields: Dict[str, int] = {
        'velos_balance': _get_cyclist_velos_balance(cyclist),
        'velos_total': get_cyclist_velos_total(cyclist),
    }
    if include_session:
        fields['session_velos'] = get_cyclist_session_velos(cyclist)
    if include_daily:
        fields['velos_daily'] = get_cyclist_velos_daily(cyclist)
    if period_start and period_end:
        fields['velos_period'] = get_cyclist_velos_period(cyclist, period_start, period_end)
    return fields


def build_group_velos_api_fields(group: Group) -> Dict[str, int]:
    """Ledger Velos fields for group API responses."""
    return {
        'velos_total': int(group.velos_total or 0),
        'velos_spendable': int(group.velos_spendable or 0),
    }


