# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    views.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
"""
Project: MyCyclingCity
Generation: AI-based

Views for leaderboard app - handles animated high-score tiles and leaderboard displays.
"""

import json
from typing import Any, List, Dict, Optional
from django.shortcuts import render
from django.http import HttpRequest, HttpResponse
from django.utils import timezone
from datetime import timedelta
from django.db.models import Sum

from api.models import (
    Group, TravelTrack, Cyclist, GroupTravelStatus, 
    CyclistDeviceCurrentMileage, Milestone, TravelHistory, 
    Event, GroupEventStatus, HourlyMetric
)
from iot.models import Device
from api.helpers import are_all_parents_visible
from decimal import Decimal
from django.core.cache import cache
import logging

logger = logging.getLogger(__name__)


def _calculate_group_totals_from_metrics(groups: List[Group], now: timezone.datetime, use_cache: bool = True, include_descendants: bool = False) -> Dict[int, Dict[str, float]]:
    """
    Calculate all aggregated values (total, daily, weekly, monthly, yearly) for groups from HourlyMetric.
    
    This ensures all components (Record-Chips, Group-Chips, Banner) use the same data source.
    Results are cached for 55 seconds (just under cronjob interval of 60s) to improve performance.
    
    Args:
        groups: List of Group objects to calculate totals for
        now: Current datetime for time-based calculations
        use_cache: Whether to use cache (default: True)
        include_descendants: If True, recursively collect all descendant groups and include
                           their metrics in the calculation. This is useful for top-level groups
                           that don't have direct HourlyMetric entries but their children do.
    
    Returns:
        Dictionary mapping group_id to dict with keys: 'total', 'daily', 'weekly', 'monthly', 'yearly'
        If include_descendants=True, the returned dict includes all descendant groups, but the
        result dict keys are still only the original groups (for backward compatibility).
    """
    group_ids = [g.id for g in groups]
    if not group_ids:
        return {}
    
    # If include_descendants is True, recursively collect all descendant groups
    if include_descendants:
        def get_all_descendant_ids(ancestor_id: int, visited: set = None) -> set:
            """Recursively get all descendant group IDs (only visible groups)."""
            if visited is None:
                visited = set()
            
            # Prevent infinite loops
            if ancestor_id in visited:
                return set()
            visited.add(ancestor_id)
            
            descendant_ids = {ancestor_id}  # Include the ancestor group itself
            
            # Get direct children (only visible ones)
            direct_children = Group.objects.filter(
                parent_id=ancestor_id,
                is_visible=True
            ).values_list('id', flat=True)
            descendant_ids.update(direct_children)
            
            # Recursively get children of children (prevent infinite loops)
            for child_id in direct_children:
                if child_id not in visited:
                    descendant_ids.update(get_all_descendant_ids(child_id, visited))
            
            return descendant_ids
        
        # Collect all descendant IDs for all groups
        all_group_ids = set(group_ids)
        for group_id in group_ids:
            all_group_ids.update(get_all_descendant_ids(group_id))
        group_ids = list(all_group_ids)
    
    # Sanitize group IDs for cache key: Convert list to URL-safe string format
    # This prevents CacheKeyWarning from cache backends (Memcached/Redis) that don't accept
    # illegal characters like brackets, spaces, and commas in list string representations
    if not isinstance(group_ids, (list, tuple)):
        group_ids = list(group_ids) if hasattr(group_ids, '__iter__') else [group_ids]
    group_ids_str = "-".join(map(str, sorted(group_ids)))
    
    # Try to get from cache first (cache key includes group IDs and include_descendants flag to ensure consistency)
    cache_key = f'leaderboard_group_totals_{group_ids_str}_{now.strftime("%Y%m%d%H")}_desc{int(include_descendants)}'
    if use_cache:
        cached_result = cache.get(cache_key)
        if cached_result is not None:
            logger.debug(f"Using cached group totals for {len(group_ids)} groups")
            return cached_result
    
    # Calculate time boundaries
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    days_since_monday = now.weekday()
    week_start = (now - timedelta(days=days_since_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
    week_end = (week_start + timedelta(days=6)).replace(hour=23, minute=59, second=59, microsecond=999999)
    
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if now.month == 12:
        month_end = now.replace(year=now.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        month_end = now.replace(month=now.month + 1, day=1) - timedelta(days=1)
    month_end = month_end.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    year_start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    year_end = now.replace(month=12, day=31, hour=23, minute=59, second=59, microsecond=999999)
    
    # Initialize result dictionary
    # If include_descendants=True, we calculate for all descendant groups but only return
    # results for the original groups (for backward compatibility)
    original_group_ids = [g.id for g in groups]
    result: Dict[int, Dict[str, float]] = {gid: {'total': 0.0, 'daily': 0.0, 'weekly': 0.0, 'monthly': 0.0, 'yearly': 0.0} for gid in original_group_ids}
    
    # Also initialize for all group_ids (including descendants) for calculation
    calculation_result: Dict[int, Dict[str, float]] = {gid: {'total': 0.0, 'daily': 0.0, 'weekly': 0.0, 'monthly': 0.0, 'yearly': 0.0} for gid in group_ids}
    
    # Calculate TOTAL: Sum of ALL HourlyMetric entries for each group
    total_metrics = HourlyMetric.objects.filter(
        group_at_time_id__in=group_ids
    ).values('group_at_time_id').annotate(
        total=Sum('distance_km')
    )
    for metric in total_metrics:
        group_id = metric['group_at_time_id']
        if group_id in calculation_result:
            calculation_result[group_id]['total'] = float(metric['total'] or 0.0)
    
    # Calculate DAILY: Sum of HourlyMetric entries for today
    daily_metrics = HourlyMetric.objects.filter(
        timestamp__gte=today_start,
        group_at_time_id__in=group_ids
    ).values('group_at_time_id').annotate(
        daily_total=Sum('distance_km')
    )
    for metric in daily_metrics:
        group_id = metric['group_at_time_id']
        if group_id in calculation_result:
            calculation_result[group_id]['daily'] = float(metric['daily_total'] or 0.0)
    
    # Calculate WEEKLY: Sum of HourlyMetric entries for this week
    weekly_metrics = HourlyMetric.objects.filter(
        timestamp__gte=week_start,
        timestamp__lte=week_end,
        group_at_time_id__in=group_ids
    ).values('group_at_time_id').annotate(
        weekly_total=Sum('distance_km')
    )
    for metric in weekly_metrics:
        group_id = metric['group_at_time_id']
        if group_id in calculation_result:
            calculation_result[group_id]['weekly'] = float(metric['weekly_total'] or 0.0)
    
    # Calculate MONTHLY: Sum of HourlyMetric entries for this month
    monthly_metrics = HourlyMetric.objects.filter(
        timestamp__gte=month_start,
        timestamp__lte=month_end,
        group_at_time_id__in=group_ids
    ).values('group_at_time_id').annotate(
        monthly_total=Sum('distance_km')
    )
    for metric in monthly_metrics:
        group_id = metric['group_at_time_id']
        if group_id in calculation_result:
            calculation_result[group_id]['monthly'] = float(metric['monthly_total'] or 0.0)
    
    # Calculate YEARLY: Sum of HourlyMetric entries for this year
    yearly_metrics = HourlyMetric.objects.filter(
        timestamp__gte=year_start,
        timestamp__lte=year_end,
        group_at_time_id__in=group_ids
    ).values('group_at_time_id').annotate(
        yearly_total=Sum('distance_km')
    )
    for metric in yearly_metrics:
        group_id = metric['group_at_time_id']
        if group_id in calculation_result:
            calculation_result[group_id]['yearly'] = float(metric['yearly_total'] or 0.0)
    
    # If include_descendants=True, aggregate all descendant values into the original groups
    if include_descendants:
        # For each original group, sum up all its descendants' values
        for original_group in groups:
            original_id = original_group.id
            
            def get_all_descendant_ids_for_aggregation(ancestor_id: int, visited: set = None) -> set:
                """Recursively get all descendant group IDs for aggregation."""
                if visited is None:
                    visited = set()
                if ancestor_id in visited:
                    return set()
                visited.add(ancestor_id)
                
                descendant_ids = {ancestor_id}  # Include the ancestor itself
                direct_children = Group.objects.filter(
                    parent_id=ancestor_id,
                    is_visible=True
                ).values_list('id', flat=True)
                descendant_ids.update(direct_children)
                
                for child_id in direct_children:
                    if child_id not in visited:
                        descendant_ids.update(get_all_descendant_ids_for_aggregation(child_id, visited))
                
                return descendant_ids
            
            # Get all descendant IDs for this original group
            all_descendant_ids = get_all_descendant_ids_for_aggregation(original_id)
            
            # Aggregate all descendant values into the original group
            for desc_id in all_descendant_ids:
                if desc_id in calculation_result:
                    result[original_id]['total'] += calculation_result[desc_id]['total']
                    result[original_id]['daily'] += calculation_result[desc_id]['daily']
                    result[original_id]['weekly'] += calculation_result[desc_id]['weekly']
                    result[original_id]['monthly'] += calculation_result[desc_id]['monthly']
                    result[original_id]['yearly'] += calculation_result[desc_id]['yearly']
    else:
        # Normal mode: just copy from calculation_result to result
        for group_id in original_group_ids:
            if group_id in calculation_result:
                result[group_id] = calculation_result[group_id]
    
    # Propagate values to parent groups (hierarchical aggregation)
    # This is only needed if include_descendants=False, because if include_descendants=True,
    # we've already aggregated all descendants into the original groups above
    if not include_descendants:
        # Process from leaf groups upward to ensure correct aggregation
        # First, collect all parent-child relationships
        parent_child_map: Dict[int, List[int]] = {}
        for group in groups:
            if group.parent and group.parent.id in result:
                parent_id = group.parent.id
                group_id = group.id
                if group_id in result:
                    if parent_id not in parent_child_map:
                        parent_child_map[parent_id] = []
                    parent_child_map[parent_id].append(group_id)
        
        # Recursively propagate values upward through the hierarchy
        def propagate_to_parents(group_id: int, visited: set = None):
            """Recursively propagate group values to all parent groups."""
            if visited is None:
                visited = set()
            if group_id in visited:
                return  # Prevent infinite loops
            visited.add(group_id)
            
            # Find parent of this group
            for group in groups:
                if group.id == group_id and group.parent and group.parent.id in result:
                    parent_id = group.parent.id
                    if group_id in result and parent_id in result:
                        # Add this group's values to parent
                        result[parent_id]['total'] += result[group_id]['total']
                        result[parent_id]['daily'] += result[group_id]['daily']
                        result[parent_id]['weekly'] += result[group_id]['weekly']
                        result[parent_id]['monthly'] += result[group_id]['monthly']
                        result[parent_id]['yearly'] += result[group_id]['yearly']
                        # Recursively propagate to parent's parent
                        propagate_to_parents(parent_id, visited)
        
        # Propagate for all groups
        for group in groups:
            if group.id in result:
                propagate_to_parents(group.id)
    
    # Cache the result for 55 seconds (just under cronjob interval of 60s)
    # This ensures cache is invalidated when new HourlyMetric data arrives
    if use_cache:
        cache.set(cache_key, result, 55)
        logger.debug(f"Cached group totals for {len(result)} groups (expires in 55s)")
    
    logger.debug(f"Calculated totals from HourlyMetric for {len(result)} groups")
    return result


def _leaderboard_implementation(request: HttpRequest) -> HttpResponse:
    """
    Internal implementation of leaderboard logic.
    
    This function contains the full leaderboard implementation.
    
    Args:
        request: HTTP request object.
    
    Returns:
        HTTP response with leaderboard page.
    """
    now = timezone.now()
    view_param = request.GET.get('view', 'leaderboard')  # Default to leaderboard
    parent_name = request.GET.get('group')  # Get parent group name from URL parameter
    sort_by = request.GET.get('sort', 'daily')  # Get sort parameter: 'daily' or 'total' (default: 'daily')
    
    # Get map data for embedded map view
    # Travel data (Tracks & Avatars)
    active_tracks = TravelTrack.objects.filter(is_active=True, is_visible_on_map=True)
    # Filter by time if start_time or end_time is set
    active_tracks = [t for t in active_tracks if t.is_currently_active()]
    tracks_data = []
    milestones_data = []
    for track in active_tracks:
        if track.geojson_data:
            tracks_data.append({'id': track.id, 'name': track.name, 'points': json.loads(track.geojson_data)})
        # Show all milestones (reached and unreached) with GPS coordinates, excluding start point (0 km)
        for m in track.milestones.filter(gps_latitude__isnull=False, gps_longitude__isnull=False).exclude(distance_km=0).select_related('winner_group', 'winner_group__parent'):
            # Get parent group name if winner_group has a parent
            parent_group_name = None
            if m.winner_group and m.winner_group.parent:
                parent_group_name = m.winner_group.parent.name
            
            milestones_data.append({
                'id': m.id,
                'name': m.name,
                'lat': float(m.gps_latitude),
                'lon': float(m.gps_longitude),
                'km': float(m.distance_km),
                'text': m.reward_text or "",
                'is_reached': m.winner_group is not None,
                'winner_group_name': m.winner_group.name if m.winner_group else None,
                'winner_parent_group_name': parent_group_name,  # TOP-Gruppe
                'reached_at': m.reached_at.isoformat() if m.reached_at else None,
                'track_id': track.id,
                'track_total_length_km': float(track.total_length_km)
            })
    
    # Get devices data
    devices_data = []
    for device in Device.objects.filter(is_visible=True):
        if device.gps_latitude and device.gps_longitude:
            devices_data.append({
                'id': device.id,
                'name': device.display_name or device.name,
                'lat': float(device.gps_latitude),
                'lon': float(device.gps_longitude),
                'distance_total': float(device.distance_total),
                'last_active': device.last_active.isoformat() if device.last_active else None
            })
    
    # Get group avatars data (simplified - just get all groups with travel status)
    group_avatars = []
    track_ids = [t.id for t in active_tracks]
    statuses = GroupTravelStatus.objects.filter(track_id__in=track_ids).select_related('group', 'track')
    for status in statuses:
        if status.current_travel_distance > 0:
            group_avatars.append({
                'name': status.group.name,
                'km': float(status.current_travel_distance),
                'track_id': status.track.id
            })
    
    # Get active cyclists for ticker (active in last 60 seconds)
    # If a parent group filter is active, only show cyclists from that parent's subgroups
    active_cutoff = now - timedelta(seconds=60)
    active_cyclists_qs = Cyclist.objects.filter(
        is_visible=True,
        last_active__isnull=False,
        last_active__gte=active_cutoff
    ).select_related('cyclistdevicecurrentmileage').prefetch_related('groups').order_by('-last_active')
    
    # Filter cyclists by parent group if filter is active
    if parent_name:
        try:
            parent_group = Group.objects.get(name__iexact=parent_name, is_visible=True)
            
            # Recursively find all descendant group IDs (same logic as banner)
            def get_all_descendant_ids(ancestor_id: int, visited: set = None) -> set:
                """Recursively get all descendant group IDs."""
                if visited is None:
                    visited = set()
                
                descendant_ids = set()
                # Start with direct children (only visible ones)
                direct_children = Group.objects.filter(
                    parent_id=ancestor_id,
                    is_visible=True
                ).values_list('id', flat=True)
                descendant_ids.update(direct_children)
                
                # Recursively get children of children (prevent infinite loops)
                for child_id in direct_children:
                    if child_id not in visited:
                        visited.add(child_id)
                        descendant_ids.update(get_all_descendant_ids(child_id, visited))
                
                return descendant_ids
            
            # Get all descendant IDs (only visible groups)
            subgroup_ids = get_all_descendant_ids(parent_group.id)
            
            # Filter cyclists to only those in the filtered subgroups
            # CRITICAL: Only show cyclists from groups that belong to the filtered parent
            if subgroup_ids:
                active_cyclists_qs = active_cyclists_qs.filter(groups__id__in=subgroup_ids).distinct()
            else:
                # No subgroups found - no cyclists shown
                active_cyclists_qs = Cyclist.objects.none()
        except Group.DoesNotExist:
            # Parent group not found or not visible - no cyclists shown
            active_cyclists_qs = Cyclist.objects.none()
    
    active_cyclists = []
    # Get the filtered parent group if filter is active (for additional verification)
    filtered_parent_group = None
    filtered_descendant_ids = set()
    if parent_name:
        try:
            filtered_parent_group = Group.objects.get(name__iexact=parent_name, is_visible=True)
            # Recursively find all descendant group IDs (same logic as banner)
            def get_all_descendant_ids_for_ticker(ancestor_id: int, visited: set = None) -> set:
                """Recursively get all descendant group IDs (only visible groups)."""
                if visited is None:
                    visited = set()
                
                descendant_ids = set()
                # Start with direct children (only visible ones)
                direct_children = Group.objects.filter(
                    parent_id=ancestor_id,
                    is_visible=True
                ).values_list('id', flat=True)
                descendant_ids.update(direct_children)
                
                # Recursively get children of children (prevent infinite loops)
                for child_id in direct_children:
                    if child_id not in visited:
                        visited.add(child_id)
                        descendant_ids.update(get_all_descendant_ids_for_ticker(child_id, visited))
                
                return descendant_ids
            
            filtered_descendant_ids = get_all_descendant_ids_for_ticker(filtered_parent_group.id)
        except Group.DoesNotExist:
            pass
    
    for cyclist in active_cyclists_qs:
        # Get primary group (first group) and its top parent name
        primary_group = cyclist.groups.first()
        if not primary_group:
            continue
        
        # CRITICAL: If filter is active, verify that the cyclist's group belongs to the filtered parent
        if filtered_parent_group and filtered_descendant_ids:
            if primary_group.id not in filtered_descendant_ids:
                # Cyclist's group doesn't belong to filtered parent - skip
                continue
            # Additional check: verify by traversing parent chain
            def is_descendant_for_ticker(group, ancestor):
                """Check if group is a descendant of ancestor by traversing parent chain."""
                visited = set()
                current = group
                while current and current.parent_id and current.id not in visited:
                    visited.add(current.id)
                    if current.parent_id == ancestor.id:
                        return True
                    try:
                        current = current.parent
                    except (Group.DoesNotExist, AttributeError):
                        break
                return False
            
            if not is_descendant_for_ticker(primary_group, filtered_parent_group):
                # Cyclist's group is not a descendant of filtered parent - skip
                continue
        
        # Only include cyclist if all parent groups are visible
        if not are_all_parents_visible(primary_group):
            continue
        
        # Get the group label to display in ticker
        # If no filter: show top parent group's kiosk label
        # If filter active: show primary group's kiosk label
        group_kiosk_label = ''
        if not parent_name:
            # No filter: show top parent group's kiosk label
            try:
                # Use top_parent_name property to get the name, then find the group
                top_parent_name = primary_group.top_parent_name
                # Find the top parent group by name (should be unique per group_type)
                # Traverse up to find the actual top parent group object
                top_parent = primary_group
                visited = set()
                while top_parent and top_parent.parent_id and top_parent.id not in visited:
                    visited.add(top_parent.id)
                    # Load parent if needed
                    if not hasattr(top_parent, 'parent') or top_parent.parent is None:
                        if top_parent.parent_id:
                            try:
                                top_parent.parent = Group.objects.get(id=top_parent.parent_id)
                            except Group.DoesNotExist:
                                break
                        else:
                            break
                    top_parent = top_parent.parent
                    if not top_parent:
                        break
                
                # Get kiosk label from top parent (reload to ensure short_name is available)
                if top_parent and top_parent.id != primary_group.id:
                    top_parent = Group.objects.get(id=top_parent.id)
                    group_kiosk_label = top_parent.get_kiosk_label()
                else:
                    # No parent found, use primary group
                    group_kiosk_label = primary_group.get_kiosk_label()
            except (RecursionError, AttributeError, RuntimeError, Group.DoesNotExist):
                # Fallback to primary group's kiosk label
                try:
                    group_kiosk_label = primary_group.get_kiosk_label()
                except:
                    group_kiosk_label = primary_group.name
        else:
            # Filter active: show primary group's kiosk label
            try:
                group_kiosk_label = primary_group.get_kiosk_label()
            except (RecursionError, AttributeError, RuntimeError):
                # Fallback to group name if recursion occurs
                group_kiosk_label = primary_group.name
        
        # Get session kilometers from CyclistDeviceCurrentMileage
        session_km = 0.0
        try:
            mileage_obj = cyclist.cyclistdevicecurrentmileage
            if mileage_obj and mileage_obj.cumulative_mileage is not None:
                session_km = float(mileage_obj.cumulative_mileage)
        except (AttributeError, CyclistDeviceCurrentMileage.DoesNotExist):
            session_km = 0.0
        
        active_cyclists.append({
            'user_id': cyclist.user_id,
            'group_short_name': group_kiosk_label,  # Use kiosk label (short_name if available, otherwise full name)
            'session_km': session_km,
        })
    
    # Time thresholds
    active_threshold = now - timedelta(seconds=30)  # < 30s = active
    recent_threshold = now - timedelta(minutes=10)  # < 10m = recent
    
    # Filter groups based on parent_name parameter
    # If parent_name is provided, show only leaf-groups belonging to this parent (recursively)
    # Otherwise, show all leaf-groups
    if parent_name:
        try:
            # Verify parent group exists and is visible
            parent_group = Group.objects.get(name__iexact=parent_name, is_visible=True)
            
            # Recursively find all descendant group IDs (only visible groups)
            def get_all_descendant_ids_for_tiles(ancestor_id: int, visited: set = None) -> set:
                """Recursively get all descendant group IDs (only visible groups)."""
                if visited is None:
                    visited = set()
                
                # Prevent infinite loops
                if ancestor_id in visited:
                    return set()
                visited.add(ancestor_id)
                
                descendant_ids = set()
                # Start with direct children (only visible ones)
                direct_children = Group.objects.filter(
                    parent_id=ancestor_id,
                    is_visible=True
                ).values_list('id', flat=True)
                
                # Convert to list to ensure we can iterate
                direct_children_list = list(direct_children)
                descendant_ids.update(direct_children_list)
                
                # Recursively get children of children (prevent infinite loops)
                for child_id in direct_children_list:
                    if child_id not in visited:
                        # Recursively get descendants of this child
                        child_descendants = get_all_descendant_ids_for_tiles(child_id, visited)
                        descendant_ids.update(child_descendants)
                
                return descendant_ids
            
            # Get all descendant IDs (only visible groups)
            descendant_ids = get_all_descendant_ids_for_tiles(parent_group.id)
            
            # Helper function to verify that a group is a descendant of ancestor
            def is_descendant_for_tiles(group, ancestor):
                """Check if group is a descendant of ancestor by traversing parent chain."""
                visited = set()
                current = group
                while current and current.parent_id and current.id not in visited:
                    visited.add(current.id)
                    if current.parent_id == ancestor.id:
                        return True
                    try:
                        if not hasattr(current, 'parent') or current.parent is None:
                            current.parent = Group.objects.get(id=current.parent_id) if current.parent_id else None
                        current = current.parent
                    except (Group.DoesNotExist, AttributeError):
                        break
                return False
            
            # Get leaf-groups (with cyclists but no children) that belong to this parent
            # CRITICAL: Only get groups that are in descendant_ids
            if descendant_ids:
                child_groups = Group.objects.filter(
                    id__in=descendant_ids,
                    is_visible=True,
                    children__isnull=True,
                    members__isnull=False
                ).distinct().select_related('parent').prefetch_related('members')
                
                # Additional filtering: verify each group is really a descendant
                verified_groups = []
                for group in child_groups:
                    # CRITICAL: Exclude the parent group itself
                    if group.id == parent_group.id:
                        continue
                    
                    # CRITICAL: Verify that this group actually belongs to the filtered parent
                    if group.id not in descendant_ids:
                        continue
                    
                    # CRITICAL: Double-check that this group is actually a descendant
                    if not is_descendant_for_tiles(group, parent_group):
                        continue
                    
                    # CRITICAL: Only include if all parent groups are visible
                    if not are_all_parents_visible(group):
                        continue
                    
                    verified_groups.append(group)
                
                # Use verified_groups directly - they already have all fields including short_name loaded
                # CRITICAL: Don't reload from database to preserve short_name values
                # Prefetch parent and members to avoid N+1 queries
                if verified_groups:
                    group_ids = [g.id for g in verified_groups]
                    # Prefetch parent relationships for all groups
                    parent_ids = {g.parent_id for g in verified_groups if g.parent_id}
                    if parent_ids:
                        parents = {p.id: p for p in Group.objects.filter(id__in=parent_ids)}
                        for group in verified_groups:
                            if group.parent_id and group.parent_id in parents:
                                group.parent = parents[group.parent_id]
                    # Prefetch members for all groups
                    groups_with_members = Group.objects.filter(id__in=group_ids).prefetch_related('members')
                    member_map = {g.id: list(g.members.all()) for g in groups_with_members}
                    for group in verified_groups:
                        if group.id in member_map:
                            # Store members in a way that's accessible
                            group._prefetched_members = member_map[group.id]
                    all_groups = verified_groups  # Use list directly - preserves short_name
                else:
                    all_groups = []
            else:
                # No descendants found - return empty result
                all_groups = Group.objects.none()
            
            current_filter = parent_name
        except Group.DoesNotExist:
            # Parent group not found or not visible - return empty result
            all_groups = Group.objects.none()
            # CRITICAL: Keep current_filter set even if group not found/visible
            # This ensures that the filtered view is still active and shows nothing
            current_filter = parent_name
    else:
        # No filter - show all leaf-groups
        all_groups = Group.objects.filter(
            is_visible=True,
            members__isnull=False,
            children__isnull=True
        ).distinct().select_related('parent').prefetch_related('members')
        current_filter = None
    
    # Get active groups - synchronize with ticker logic
    # Ticker uses Cyclist.last_active >= 60 seconds, so we use the same logic
    active_cutoff_for_footer = now - timedelta(seconds=60)  # Same as ticker (60 seconds)
    
    # Get active cyclists using the same logic as ticker
    active_cyclists_for_footer = Cyclist.objects.filter(
        is_visible=True,
        last_active__isnull=False,
        last_active__gte=active_cutoff_for_footer
    ).prefetch_related('groups')
    
    # Apply the same filter as ticker if a parent group filter is active
    filtered_descendant_ids = set()  # Initialize empty set
    if current_filter:
        try:
            parent_group = Group.objects.get(name__iexact=current_filter, is_visible=True)
            
            # Recursively find all descendant group IDs (same logic as ticker)
            def get_all_descendant_ids_for_footer(ancestor_id: int, visited: set = None) -> set:
                """Recursively get all descendant group IDs (only visible groups)."""
                if visited is None:
                    visited = set()
                
                descendant_ids = set()
                # Start with direct children (only visible ones)
                direct_children = Group.objects.filter(
                    parent_id=ancestor_id,
                    is_visible=True
                ).values_list('id', flat=True)
                descendant_ids.update(direct_children)
                
                # Recursively get children of children (prevent infinite loops)
                for child_id in direct_children:
                    if child_id not in visited:
                        visited.add(child_id)
                        descendant_ids.update(get_all_descendant_ids_for_footer(child_id, visited))
                
                return descendant_ids
            
            # Get all descendant IDs (only visible groups)
            filtered_descendant_ids = get_all_descendant_ids_for_footer(parent_group.id)
            
            # Filter cyclists to only those in the filtered subgroups (same as ticker)
            if filtered_descendant_ids:
                active_cyclists_for_footer = active_cyclists_for_footer.filter(groups__id__in=filtered_descendant_ids).distinct()
            else:
                # No subgroups found - no active cyclists
                active_cyclists_for_footer = Cyclist.objects.none()
        except Group.DoesNotExist:
            # Parent group not found or not visible - no active cyclists
            active_cyclists_for_footer = Cyclist.objects.none()
    
    # Get leaf-groups that have active cyclists (groups with direct members)
    # This matches what the ticker displays - only leaf-groups with active cyclists
    active_leaf_group_ids = set()
    for cyclist in active_cyclists_for_footer:
        # Get all groups for this cyclist
        cyclist_groups = cyclist.groups.all()
        for group in cyclist_groups:
            # Only count leaf-groups (groups without children, i.e., groups with direct members)
            if group.children.exists():
                continue  # Skip parent groups
            if group.members.exists():
                # If filter is active, only count groups that belong to the filtered parent
                if current_filter and filtered_descendant_ids:
                    # Verify that this group belongs to the filtered parent
                    if group.id not in filtered_descendant_ids:
                        continue
                active_leaf_group_ids.add(group.id)
    
    # Only mark leaf-groups as active if they have active cyclists
    # Do NOT mark parent groups as active based on their children's activity
    # A group is only active if it directly has active cyclists (not through children)
    active_group_ids = set(active_leaf_group_ids)
    
    # Get recent group IDs (activity < 10m)
    recent_mileage = CyclistDeviceCurrentMileage.objects.filter(
        last_activity__gte=recent_threshold
    ).select_related('cyclist')
    recent_cyclist_ids = set(recent_mileage.values_list('cyclist_id', flat=True))
    recent_groups_qs = Group.objects.filter(
        members__id__in=recent_cyclist_ids
    ).distinct()
    recent_group_ids = set(recent_groups_qs.values_list('id', flat=True))
    
    # Calculate all aggregated values from HourlyMetric (unified data source)
    # This ensures all components (Record-Chips, Group-Chips, Banner) use the same data
    # Convert all_groups to list if it's a QuerySet
    try:
        groups_list = list(all_groups) if hasattr(all_groups, '__iter__') and not isinstance(all_groups, list) else all_groups
        if not groups_list:
            groups_list = []
        group_totals = _calculate_group_totals_from_metrics(groups_list, now)
    except Exception as e:
        logger.error(f"Error calculating group totals from metrics: {e}", exc_info=True)
        group_totals = {}
    
    # Extract individual dictionaries for backward compatibility
    daily_km_by_group: Dict[int, float] = {gid: totals['daily'] for gid, totals in group_totals.items()}
    weekly_km_by_group: Dict[int, float] = {gid: totals['weekly'] for gid, totals in group_totals.items()}
    monthly_km_by_group: Dict[int, float] = {gid: totals['monthly'] for gid, totals in group_totals.items()}
    yearly_km_by_group: Dict[int, float] = {gid: totals['yearly'] for gid, totals in group_totals.items()}
    total_km_by_group: Dict[int, float] = {gid: totals['total'] for gid, totals in group_totals.items()}
    
    # Get groups with their distance_total and daily_km
    # Note: We'll sort after collecting all data based on the sort parameter
    groups_data: List[Dict[str, Any]] = []
    for group in all_groups:
        # Only include group if all parent groups are visible
        if not are_all_parents_visible(group):
            continue
        
        # Check if group is active or recent
        # Only leaf-groups with direct active cyclists are marked as active
        # Parent groups are NOT marked as active based on their children's activity
        is_active = group.id in active_group_ids
        is_recent = group.id in recent_group_ids
        
        # Debug: Log if group is marked as active
        if is_active and '4a-SchuleB' in group.name:
            import logging
            logger = logging.getLogger(__name__)
            logger.debug(f"Group {group.name} (ID: {group.id}) marked as active. Has children: {group.children.exists()}, Has members: {group.members.exists()}, In active_group_ids: {group.id in active_group_ids}")
        
        # Determine state
        if is_active:
            state = 'active'
        elif is_recent:
            state = 'idle'
        else:
            state = 'dormant'
        
        # Get top parent group name safely to avoid recursion
        try:
            parent_group_name = group.top_parent_name
        except (RecursionError, AttributeError, RuntimeError):
            # Fallback to group name if recursion occurs
            parent_group_name = group.name
        
        # Get top parent group ID for color mapping (top-most parent group)
        top_parent_id = group.id
        current = group
        visited = set()
        while current and current.parent and current.id not in visited:
            visited.add(current.id)
            current = current.parent
            top_parent_id = current.id if current else top_parent_id
        
        # Get all aggregated values from unified calculation (already includes parent aggregation)
        totals = group_totals.get(group.id, {'total': 0.0, 'daily': 0.0, 'weekly': 0.0, 'monthly': 0.0, 'yearly': 0.0})
        daily_km = float(totals['daily'])
        weekly_km = float(totals['weekly'])
        monthly_km = float(totals['monthly'])
        yearly_km = float(totals['yearly'])
        distance_total_from_metrics = float(totals['total'])
        
        # Get kiosk label (short_name if available, otherwise full name)
        # CRITICAL: Ensure short_name is loaded from database
        # First try to get short_name from the current group object
        # If not available or None, reload from database
        try:
            # Check if short_name is already available on the group object
            if hasattr(group, 'short_name') and group.short_name and group.short_name.strip():
                kiosk_label = group.short_name.strip()
            else:
                # Reload from database to ensure short_name is current
                fresh_group = Group.objects.only('id', 'name', 'short_name').get(id=group.id)
                if fresh_group.short_name and fresh_group.short_name.strip():
                    kiosk_label = fresh_group.short_name.strip()
                else:
                    kiosk_label = fresh_group.name
        except (Group.DoesNotExist, AttributeError):
            # Fallback: try to use group.get_kiosk_label() if available
            try:
                kiosk_label = group.get_kiosk_label()
            except:
                # Final fallback to group name
                kiosk_label = group.name if hasattr(group, 'name') else 'Unknown'
        
        groups_data.append({
            'id': group.id,
            'name': group.name,
            'short_name': group.short_name or '',
            'kiosk_label': kiosk_label,
            'parent_group_name': parent_group_name,
            'top_parent_id': top_parent_id,  # For color mapping
            'distance_total': distance_total_from_metrics,  # Use HourlyMetric total instead of Group.distance_total
            'daily_km': daily_km,
            'weekly_km': weekly_km,
            'monthly_km': monthly_km,
            'yearly_km': yearly_km,
            'state': state,
            'is_active': is_active,
            'is_recent': is_recent,
        })
    
    # Filter out groups with zero total kilometers
    # Show all groups with distance_total > 0, regardless of current activity
    # The 'state' field (active/idle/dormant) will indicate current activity status
    groups_data = [g for g in groups_data if g['distance_total'] > 0]
    
    # Sort groups based on sort parameter
    if sort_by == 'daily':
        # Sort by daily kilometers (descending), then by total as tiebreaker
        groups_data = sorted(groups_data, key=lambda x: (x['daily_km'], x['distance_total']), reverse=True)
    else:
        # Sort by total kilometers (descending), then by daily as tiebreaker
        groups_data = sorted(groups_data, key=lambda x: (x['distance_total'], x['daily_km']), reverse=True)
    
    # Calculate banner data for display
    # If a group filter is active, show subgroups of that parent group
    # Otherwise, show top parent groups sorted by total
    # Only show groups with distance_total > 0
    if current_filter:
        # Filtered view: Show subgroups of the filtered parent group
        # Only show groups that belong to the filtered group (direct or indirect children)
        # CRITICAL: Only show if the filtered parent group itself is visible
        try:
            parent_group = Group.objects.get(name__iexact=current_filter, is_visible=True)
            
            # Use the same recursive function as for tiles to ensure consistency
            def get_all_descendant_ids(ancestor_id: int, visited: set = None) -> set:
                """Recursively get all descendant group IDs (only visible groups)."""
                if visited is None:
                    visited = set()
                
                # Prevent infinite loops - if we've already visited this ancestor, return empty
                if ancestor_id in visited:
                    return set()
                visited.add(ancestor_id)
                
                descendant_ids = set()
                # Start with direct children (only visible ones)
                # CRITICAL: Only get groups where parent_id exactly matches ancestor_id
                direct_children = Group.objects.filter(
                    parent_id=ancestor_id,
                    is_visible=True
                ).values_list('id', flat=True)
                
                # Convert to list to ensure we can iterate
                direct_children_list = list(direct_children)
                descendant_ids.update(direct_children_list)
                
                # Recursively get children of children (prevent infinite loops)
                for child_id in direct_children_list:
                    if child_id not in visited:
                        # Recursively get descendants of this child
                        child_descendants = get_all_descendant_ids(child_id, visited)
                        descendant_ids.update(child_descendants)
                
                return descendant_ids
            
            # Helper function to verify that a group is a descendant of ancestor
            def is_descendant_of(group, ancestor):
                """Check if group is a descendant of ancestor by traversing parent chain."""
                visited = set()
                current = group
                while current and current.parent_id and current.id not in visited:
                    visited.add(current.id)
                    if current.parent_id == ancestor.id:
                        return True
                    try:
                        current = current.parent
                    except (Group.DoesNotExist, AttributeError):
                        break
                return False
            
            # Get all descendant IDs (only visible groups)
            descendant_ids = get_all_descendant_ids(parent_group.id)
            
            # CRITICAL: Only show groups if descendant_ids is not empty
            # If no descendants found, return empty list
            if not descendant_ids:
                top_parent_groups = []
            else:
                # IMPORTANT: Instead of querying all groups and filtering, 
                # we'll iterate through the descendant_ids and verify each one
                # This ensures that ONLY groups in descendant_ids are considered
                top_parent_groups = []
                
                # Get all groups that are in descendant_ids
                # CRITICAL: For banner, only show leaf-groups (groups without children)
                # IMPORTANT: Use select_related to avoid N+1 queries
                # Note: We filter by HourlyMetric totals later, not by Group.distance_total
                subgroups = Group.objects.filter(
                    id__in=descendant_ids,
                    is_visible=True,
                    children__isnull=True  # CRITICAL: Only leaf-groups (no children)
                ).select_related('parent')
                
                top_parent_groups = []
                for subgroup in subgroups:
                    # CRITICAL: Exclude the filtered parent group itself
                    if subgroup.id == parent_group.id:
                        continue
                    
                    # CRITICAL: Verify that this subgroup actually belongs to the filtered parent
                    # by checking if it's in the descendant_ids set (should always be true, but safety check)
                    if subgroup.id not in descendant_ids:
                        continue
                    
                    # CRITICAL: Double-check that this subgroup is actually a descendant
                    # by traversing up the parent chain - this is the most important check
                    # This ensures that "Reiseradler" is not shown if it doesn't belong to "SchuleA"
                    # Reload parent if needed for accurate check
                    if not hasattr(subgroup, 'parent') or subgroup.parent is None:
                        try:
                            subgroup.parent = Group.objects.get(id=subgroup.parent_id) if subgroup.parent_id else None
                        except Group.DoesNotExist:
                            continue
                    
                    if not is_descendant_of(subgroup, parent_group):
                        continue
                    
                    # CRITICAL: Only include if all parent groups are visible
                    # This also ensures that the parent chain is valid
                    if not are_all_parents_visible(subgroup):
                        continue
                    
                    # FINAL VERIFICATION: Ensure the subgroup's parent chain actually leads to parent_group
                    # Traverse the entire parent chain to verify
                    visited_chain = set()
                    current_chain = subgroup
                    found_parent_in_chain = False
                    while current_chain and current_chain.parent_id and current_chain.id not in visited_chain:
                        visited_chain.add(current_chain.id)
                        if current_chain.parent_id == parent_group.id:
                            found_parent_in_chain = True
                            break
                        try:
                            if not hasattr(current_chain, 'parent') or current_chain.parent is None:
                                current_chain.parent = Group.objects.get(id=current_chain.parent_id) if current_chain.parent_id else None
                            current_chain = current_chain.parent
                        except (Group.DoesNotExist, AttributeError):
                            break
                    
                    if not found_parent_in_chain:
                        continue
                    
                    # Use HourlyMetric total instead of Group.distance_total for consistency
                    subgroup_total = total_km_by_group.get(subgroup.id, 0.0)
                    # Only include if total > 0 (filter by HourlyMetric total, not Group.distance_total)
                    if subgroup_total > 0:
                        top_parent_groups.append({
                            'name': subgroup.get_kiosk_label(),  # Use short_name if available, otherwise full name
                            'total_km': subgroup_total,
                        })
                
                # Already sorted by distance_total from query, but ensure descending order
                top_parent_groups = sorted(top_parent_groups, key=lambda x: x['total_km'], reverse=True)[:10]  # Limit to top 10
            
        except Group.DoesNotExist:
            top_parent_groups = []
    else:
        # Global view: Get all top parent groups and sort by total
        # Include parent groups only if:
        # 1. The parent is visible and has distance_total > 0, OR
        # 2. The parent has visible children with distance_total > 0
        # AND all parent groups in the hierarchy are visible
        parent_groups = Group.objects.filter(
            parent__isnull=True
        )
        parent_data: List[Dict[str, Any]] = []
        for parent in parent_groups:
            # First check if all parent groups are visible (for top-level groups, this is just the group itself)
            if not are_all_parents_visible(parent):
                continue
            
            # Use HourlyMetric totals for consistency
            parent_total = total_km_by_group.get(parent.id, 0.0)
            parent_visible_with_km = parent.is_visible and parent_total > 0
            
            # Check if parent has visible children with totals > 0
            # Also ensure all children's parent groups are visible
            visible_children = []
            for child in parent.children.filter(is_visible=True):
                # Only include child if all its parent groups are visible
                if are_all_parents_visible(child):
                    child_total = total_km_by_group.get(child.id, 0.0)
                    if child_total > 0:
                        visible_children.append((child, child_total))
            
            children_total = sum(total for _, total in visible_children)
            has_visible_children = children_total > 0
            
            # Only include parent if it meets one of the conditions
            if parent_visible_with_km or has_visible_children:
                # Use the sum of visible children if available, otherwise use parent's total from HourlyMetric
                if has_visible_children:
                    total_km = children_total
                else:
                    total_km = parent_total
                
                parent_data.append({
                    'name': parent.get_kiosk_label(),  # Use short_name if available, otherwise full name
                    'total_km': total_km,
                })
        
        # Sort parent groups by total_km descending - limit to top 10
        top_parent_groups = sorted(parent_data, key=lambda x: x['total_km'], reverse=True)[:10]
    
    # Daily record holder: Find group with highest value based on sort parameter
    daily_record_holder: Optional[Dict[str, Any]] = None
    daily_record_value: float = 0.0
    
    if groups_data:
        # Find the top group based on sort parameter
        if sort_by == 'daily':
            top_group = max(groups_data, key=lambda x: (x['daily_km'], x['distance_total']))
            if top_group['daily_km'] > 0:
                daily_record_holder = {
                    'name': top_group['kiosk_label'],
                    'parent_group_name': top_group['parent_group_name'],
                }
                daily_record_value = top_group['daily_km']
        else:
            top_group = max(groups_data, key=lambda x: (x['distance_total'], x['daily_km']))
            if top_group['distance_total'] > 0:
                daily_record_holder = {
                    'name': top_group['kiosk_label'],
                    'parent_group_name': top_group['parent_group_name'],
                }
                daily_record_value = top_group['distance_total']
    
    # Weekly record holder: Find group with highest weekly kilometers (Monday to Sunday)
    weekly_record_holder: Optional[Dict[str, Any]] = None
    weekly_record_value: float = 0.0
    
    if groups_data:
        # Find the group with highest weekly_km
        top_weekly_group = max(groups_data, key=lambda x: (x['weekly_km'], x['distance_total']))
        if top_weekly_group['weekly_km'] > 0:
            weekly_record_holder = {
                'name': top_weekly_group['kiosk_label'],
                'parent_group_name': top_weekly_group['parent_group_name'],
            }
            weekly_record_value = top_weekly_group['weekly_km']
    
    # Monthly record holder: Find group with highest monthly kilometers (1st to last day of month)
    monthly_record_holder: Optional[Dict[str, Any]] = None
    monthly_record_value: float = 0.0
    
    if groups_data:
        # Find the group with highest monthly_km
        top_monthly_group = max(groups_data, key=lambda x: (x['monthly_km'], x['distance_total']))
        if top_monthly_group['monthly_km'] > 0:
            monthly_record_holder = {
                'name': top_monthly_group['kiosk_label'],
                'parent_group_name': top_monthly_group['parent_group_name'],
            }
            monthly_record_value = top_monthly_group['monthly_km']
    
    # Yearly record holder: Find group with highest yearly kilometers (January 1st to December 31st)
    yearly_record_holder: Optional[Dict[str, Any]] = None
    yearly_record_value: float = 0.0
    
    if groups_data:
        # Find the group with highest yearly_km
        top_yearly_group = max(groups_data, key=lambda x: (x['yearly_km'], x['distance_total']))
        if top_yearly_group['yearly_km'] > 0:
            yearly_record_holder = {
                'name': top_yearly_group['kiosk_label'],
                'parent_group_name': top_yearly_group['parent_group_name'],
            }
            yearly_record_value = top_yearly_group['yearly_km']
    
    # Count active groups - synchronize with ticker logic
    # Ticker shows cyclists active in last 60 seconds, so we count leaf-groups with active cyclists
    # Use the same logic as ticker: count only leaf-groups (groups with direct members) that have active cyclists
    # This matches what the ticker displays
    active_count = len(active_leaf_group_ids)  # Only count leaf-groups, not parent groups
    
    # Calculate total kilometers across all visible groups (like Admin Report)
    # Use HourlyMetric totals for consistency with other components
    # If a filter is active, only count the filtered parent group's total
    # (which already contains the aggregated sum of all descendants)
    if current_filter:
        # Filtered view: use the parent group's total from HourlyMetric
        # This is the aggregated sum of all its descendants
        try:
            parent_group = Group.objects.get(name=current_filter, is_visible=True)
            total_km = total_km_by_group.get(parent_group.id, 0.0)
        except Group.DoesNotExist:
            # Fallback: use groups_data sum (already from HourlyMetric)
            total_km = sum(g['distance_total'] for g in groups_data)
    else:
        # Unfiltered view: count only top-level groups (no parent) to avoid double-counting
        # Top-level groups need to include aggregated sum of all their descendants
        all_visible_top_groups = Group.objects.filter(is_visible=True, parent__isnull=True)
        
        # Recalculate totals with include_descendants=True to get aggregated values
        # This ensures top-level groups include all their descendants' kilometers
        top_group_totals = _calculate_group_totals_from_metrics(
            list(all_visible_top_groups),
            now,
            use_cache=True,
            include_descendants=True
        )
        total_km = sum(top_group_totals.get(g.id, {}).get('total', 0.0) for g in all_visible_top_groups)
    
    # Generate consistent colors for top parent groups
    # Use a palette of distinct, vibrant colors
    parent_colors = [
        '#3b82f6',  # blue-500
        '#22c55e',  # green-500
        '#a855f7',  # purple-500
        '#ec4899',  # pink-500
        '#06b6d4',  # cyan-500
        '#f97316',  # orange-500
        '#84cc16',  # lime-500
        '#ef4444',  # red-500
        '#6366f1',  # indigo-500
        '#f43f5e',  # rose-500
        '#14b8a6',  # teal-500
        '#eab308',  # yellow-500
        '#8b5cf6',  # violet-500
        '#06b6d4',  # sky-500
        '#10b981',  # emerald-500
    ]
    
    # Create a color map for each unique top_parent_id
    # First, try to get colors from the database (defined in admin)
    parent_color_map = {}
    top_parent_ids = {g['top_parent_id'] for g in groups_data}
    
    # Fetch groups with defined colors
    if top_parent_ids:
        groups_with_colors = Group.objects.filter(
            id__in=top_parent_ids,
            color__isnull=False
        ).exclude(color='').values('id', 'color')
        
        # Map defined colors
        for group_color in groups_with_colors:
            color_value = group_color['color'].strip() if group_color['color'] else None
            if color_value:
                # Ensure color starts with # if not already present
                if not color_value.startswith('#'):
                    color_value = '#' + color_value
                # Validate hex color format (basic: should be # followed by 3 or 6 hex digits)
                if len(color_value) >= 4 and all(c in '0123456789abcdefABCDEF#' for c in color_value[1:]):
                    parent_color_map[group_color['id']] = color_value
    
    # For groups without defined colors, use hash-based automatic assignment
    for group_item in groups_data:
        parent_id = group_item['top_parent_id']
        if parent_id not in parent_color_map:
            # Use hash-based index to assign consistent color
            color_index = hash(str(parent_id)) % len(parent_colors)
            parent_color_map[parent_id] = parent_colors[color_index]
    
    context = {
        'groups': groups_data,
        'top_parent_groups': top_parent_groups,
        'daily_record_holder': daily_record_holder,
        'daily_record_value': daily_record_value,
        'weekly_record_holder': weekly_record_holder,
        'weekly_record_value': weekly_record_value,
        'monthly_record_holder': monthly_record_holder,
        'monthly_record_value': monthly_record_value,
        'yearly_record_holder': yearly_record_holder,
        'yearly_record_value': yearly_record_value,
        'active_count': active_count,
        'total_km': round(total_km, 3),
        'now': now,
        'current_filter': current_filter,  # Pass parent_name for UI display
        'active_cyclists': active_cyclists,  # Pass active cyclists for ticker
        'sort_by': sort_by,  # Pass sort parameter to template
        'parent_color_map': parent_color_map,  # Pass color map to template
        'tracks_json': json.dumps(tracks_data),  # JSON string for JavaScript
        'devices_json': json.dumps(devices_data),  # JSON string for JavaScript
        'milestones_json': json.dumps(milestones_data),  # JSON string for JavaScript
    }
    
    # If HTMX request, check what to return
    if request.headers.get('HX-Request'):
        # Check if this is a ticker-only request
        if request.GET.get('ticker_only') == 'true':
            return render(request, 'leaderboard/partials/ticker.html', context)
        # Check if this is a banner-only request
        if request.GET.get('banner_only') == 'true':
            return render(request, 'leaderboard/partials/banner.html', context)
        # Check if this is a footer-only request
        if request.GET.get('footer_only') == 'true':
            return render(request, 'leaderboard/partials/footer.html', context)
        # Otherwise return leaderboard content
        return render(request, 'leaderboard/partials/content.html', context)
    
    return render(request, 'leaderboard/leaderboard_page.html', context)


def leaderboard_page(request: HttpRequest) -> HttpResponse:
    """
    Main view for leaderboard tiles display.
    
    High-performance leaderboard view.
    Pre-calculates active/recent groups and daily record holder in a single pass.
    Supports ?view=leaderboard URL parameter to start with leaderboard view.
    Supports ?group=parent_name URL parameter to filter by parent group.
    Supports ?sort=daily|total URL parameter to sort by daily or total kilometers.
    
    Args:
        request: HTTP request object.
    
    Returns:
        HTTP response with leaderboard page.
    """
    return _leaderboard_implementation(request)


def leaderboard_ticker(request: HttpRequest) -> HttpResponse:
    """
    Ticker view with session kilometers for active cyclists.
    
    Args:
        request: HTTP request object.
    
    Returns:
        HTTP response with ticker data.
    """
    from urllib.parse import unquote
    from api.models import Group
    
    group_id = request.GET.get('group_id')
    now = timezone.now()
    active_cutoff = now - timedelta(seconds=60)
    
    # Access via OneToOneField 'cyclistdevicecurrentmileage'
    base_cyclists = Cyclist.objects.filter(
        is_visible=True,
        last_active__gte=active_cutoff
    ).select_related('cyclistdevicecurrentmileage').prefetch_related('groups')
    
    target_group = None
    if group_id and group_id.strip() and group_id != 'None':
        # URL decoding for group names with spaces
        group_id = unquote(group_id)
        try:
            # Try first as numeric ID
            target_group = Group.objects.get(id=int(group_id))
            base_cyclists = base_cyclists.filter(groups__id=target_group.id)
        except (ValueError, Group.DoesNotExist):
            # If no valid ID, try as name
            try:
                target_group = Group.objects.get(name=group_id)
                base_cyclists = base_cyclists.filter(groups__id=target_group.id)
            except Group.DoesNotExist:
                pass
    
    ticker_data = []
    for cyclist in base_cyclists:
        s_km = 0.0
        dev_name = "Unknown"
        try:
            # The field is called 'cumulative_mileage'
            # OneToOne relationship may raise DoesNotExist
            mileage_obj = cyclist.cyclistdevicecurrentmileage
            if mileage_obj and mileage_obj.cumulative_mileage is not None:
                s_km = float(mileage_obj.cumulative_mileage)
            else:
                s_km = 0.0
            if mileage_obj and mileage_obj.device:
                dev_name = mileage_obj.device.display_name if mileage_obj.device.display_name else mileage_obj.device.name
            else:
                dev_name = "Unknown"
        except (AttributeError, CyclistDeviceCurrentMileage.DoesNotExist):
            s_km = 0.0
            dev_name = "Unknown"
        
        # Get primary group's short name
        group_short_name = ''
        primary_group = cyclist.groups.first()
        if primary_group:
            group_short_name = primary_group.get_kiosk_label()
        
        # Always include cyclist, even if session_km is 0
        ticker_data.append({
            'id': cyclist.id,
            'user_id': cyclist.user_id,
            'device_display': dev_name,
            'session_km': s_km,
            'total_km': cyclist.distance_total,
            'last_active': cyclist.last_active,
            'group_short_name': group_short_name
        })
    
    ticker_data = sorted(ticker_data, key=lambda x: x['session_km'], reverse=True)[:10]
    
    event_data = None
    if ticker_data:
        # Determine the most recently active cyclist for the overlay
        trigger_cyclist = sorted(ticker_data, key=lambda x: x['last_active'], reverse=True)[0]
        cyclist_key = f"last_session_km_{trigger_cyclist['id']}"
        last_shown_km = request.session.get(cyclist_key, 0)
        current_session_km = int(trigger_cyclist['session_km'])
        
        # World champion logo for each new kilometer in the session
        if current_session_km > last_shown_km:
            event_data = {
                'type': 'km_update',
                'name': trigger_cyclist['user_id'],
                'km': current_session_km,
                'icon': '👑'
            }
            # Trophy for milestones (every 100 total kilometers)
            if int(trigger_cyclist['total_km']) % 100 == 0:
                event_data['type'] = 'milestone'
                event_data['icon'] = '🏆'
            
            request.session[cyclist_key] = current_session_km
            request.session.modified = True
    
    return render(request, 'leaderboard/partials/ticker.html', {
        'active_cyclists': ticker_data,
        'event': event_data,
        'target_group': target_group
    })
