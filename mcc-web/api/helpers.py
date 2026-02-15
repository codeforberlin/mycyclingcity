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
from django.db.models import QuerySet, Sum
from django.utils import timezone
from api.models import Group, Cyclist, CyclistDeviceCurrentMileage, HourlyMetric
from eventboard.models import Event, GroupEventStatus
from iot.models import Device


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


def _calculate_cyclist_totals_from_metrics(cyclists: List[Cyclist], use_cache: bool = True) -> Dict[int, float]:
    """
    Calculate total kilometers for cyclists from HourlyMetric.
    
    This ensures ranking tables use the same data source as the leaderboard.
    Results are cached for 55 seconds (just under cronjob interval of 60s) to improve performance.
    
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
    
    # Calculate TOTAL: Sum of ALL HourlyMetric entries for each cyclist
    result: Dict[int, float] = {}
    
    total_metrics = HourlyMetric.objects.filter(
        cyclist_id__in=cyclist_ids
    ).values('cyclist_id').annotate(
        total=Sum('distance_km')
    )
    
    for metric in total_metrics:
        cyclist_id = metric['cyclist_id']
        if cyclist_id:
            result[cyclist_id] = float(metric['total'] or 0.0)
    
    # Initialize missing cyclists with 0.0
    for cyclist_id in cyclist_ids:
        if cyclist_id not in result:
            result[cyclist_id] = 0.0
    
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
    
    # Calculate TOTAL: Sum of ALL HourlyMetric entries for each device
    result: Dict[int, float] = {}
    
    total_metrics = HourlyMetric.objects.filter(
        device_id__in=device_ids
    ).values('device_id').annotate(
        total=Sum('distance_km')
    )
    
    for metric in total_metrics:
        device_id = metric['device_id']
        if device_id:
            result[device_id] = float(metric['total'] or 0.0)
    
    # Initialize missing devices with 0.0
    for device_id in device_ids:
        if device_id not in result:
            result[device_id] = 0.0
    
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
    
    # Calculate TOTAL: Sum of ALL HourlyMetric entries for each group
    result: Dict[int, float] = {}
    
    total_metrics = HourlyMetric.objects.filter(
        group_at_time_id__in=group_ids
    ).values('group_at_time_id').annotate(
        total=Sum('distance_km')
    )
    
    for metric in total_metrics:
        group_id = metric['group_at_time_id']
        if group_id and group_id in group_ids:
            result[group_id] = float(metric['total'] or 0.0)
    
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


