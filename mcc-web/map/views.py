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

Views for map app - handles OSM/Leaflet map visualization only.
Ranking and leaderboard functionality has been moved to separate apps.
"""

import json
from urllib.parse import unquote
from typing import List, Dict, Any, Optional
from datetime import timedelta, datetime
from decimal import Decimal

from django.shortcuts import render, redirect
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils import timezone
from django.db.models import Sum, Q, Max
from django.urls import reverse

from api.models import (
    Group, TravelTrack, Cyclist, GroupTravelStatus, 
    CyclistDeviceCurrentMileage, Milestone, TravelHistory, 
    HourlyMetric, MapPopupSettings,
    LeafGroupTravelContribution
)
from api.helpers import (
    _calculate_cyclist_totals_from_metrics,
    _calculate_group_totals_from_metrics
)
from eventboard.models import Event, GroupEventStatus
from iot.models import Device
from api.views import check_milestone_victory
from mgmt.analytics import _get_descendant_group_ids


def are_all_parents_visible(group: Group) -> bool:
    """
    Check if all parent groups in the hierarchy are visible.
    Returns True if the group and all its parents are visible, False otherwise.
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

def map_page(request: HttpRequest) -> HttpResponse:
    """
    Main view for the OSM/Leaflet map.
    
    This view handles only map visualization. Ranking and leaderboard functionality
    has been moved to separate apps.
    
    Args:
        request: HTTP request object.
    
    Returns:
        HTTP response with map page.
    """
    
    # Check if request is from mobile/tablet device
    user_agent = request.META.get('HTTP_USER_AGENT', '').lower()
    is_mobile = any(mobile_string in user_agent for mobile_string in [
        'mobile', 'android', 'iphone', 'ipad', 'ipod', 'blackberry', 
        'windows phone', 'opera mini', 'iemobile'
    ])
    
    # Logging: Output template selection and User-Agent for debugging
    user_agent_original = request.META.get('HTTP_USER_AGENT', 'Unknown')
    template_mode = "MOBILE" if is_mobile else "KIOSK"
    print(f"[map_page] Serving {template_mode} template | User-Agent: {user_agent_original}")
    
    target_group_id = request.GET.get('group_id')
    target_group_name = request.GET.get('group_name')
    show_cyclists = request.GET.get('show_cyclists', 'true').lower() == 'true'

    try:
        refresh_interval = int(request.GET.get('interval', 20))
    except:
        refresh_interval = 20

    # Group filtering - supports both ID and name, and multiple IDs (comma-separated)
    group_filter = {'is_visible': True}
    target_groups = []
    selected_group_ids = []

    if target_group_id and target_group_id.strip() and target_group_id != 'None':
        # URL decoding for group names with spaces
        target_group_id = unquote(target_group_id)
        # Support comma-separated group IDs
        group_id_list = [gid.strip() for gid in target_group_id.split(',') if gid.strip()]
        
        for gid in group_id_list:
            try:
                # Try first as numeric ID
                group = Group.objects.get(id=int(gid), **group_filter)
                target_groups.append(group)
                selected_group_ids.append(str(group.id))
            except (ValueError, Group.DoesNotExist):
                # If no valid ID, try as name
                try:
                    group = Group.objects.get(name=gid, **group_filter)
                    target_groups.append(group)
                    selected_group_ids.append(str(group.id))
                except Group.DoesNotExist:
                    pass
    elif target_group_name and target_group_name.strip():
        # URL decoding for group names with spaces
        target_group_name = unquote(target_group_name)
        # Search for group name
        try:
            group = Group.objects.get(name=target_group_name, **group_filter)
            target_groups.append(group)
            selected_group_ids.append(str(group.id))
        except Group.DoesNotExist:
            pass

    if target_groups:
        # Filter parent groups to only selected ones
        parent_groups = Group.objects.filter(id__in=[g.id for g in target_groups], **group_filter)
        # Store comma-separated IDs for context
        target_group_id = ','.join(selected_group_ids)
    else:
        parent_groups = Group.objects.filter(parent__isnull=True, **group_filter)
        target_group_id = None
        selected_group_ids = []  # Ensure selected_group_ids is initialized even when no groups selected

    # Calculate group totals from HourlyMetric for all groups at once (like in build_group_hierarchy)
    all_groups_list = list(parent_groups)
    # Also collect all subgroups for calculation
    for p_group in parent_groups:
        all_groups_list.extend(list(p_group.children.filter(is_visible=True)))
    
    group_totals = _calculate_group_totals_from_metrics(all_groups_list, use_cache=True)
    
    hierarchy = []
    for p_group in parent_groups:
        p_filter = {'is_visible': True}

        direct_members = []
        if show_cyclists:
            direct_qs = p_group.members.filter(**p_filter).select_related('cyclistdevicecurrentmileage')
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

        # Filter subgroups
        subgroups_qs = p_group.children.filter(is_visible=True)
        
        subgroups_data = []
        for sub in subgroups_qs:
            sub_member_data = []
            if show_cyclists:
                m_qs = sub.members.filter(**p_filter).select_related('cyclistdevicecurrentmileage')
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
            subgroups_data.append({
                'name': sub.name,
                'km': round(sub_total_km, 3),
                'members': sub_member_data
            })
        
        # Sort subgroups by km (from HourlyMetric) descending - no limit
        subgroups_data = sorted(subgroups_data, key=lambda x: x['km'], reverse=True)

        # Use total from HourlyMetric instead of distance_total from model
        p_group_total_km = group_totals.get(p_group.id, 0.0)
        hierarchy.append({
            'name': p_group.name,
            'km': round(p_group_total_km, 3),
            'direct_members': direct_members,
            'subgroups': subgroups_data
        })
    
    # Sort hierarchy by km (from HourlyMetric) descending - no limit
    hierarchy = sorted(hierarchy, key=lambda x: x['km'], reverse=True)

    # Travel data (Tracks & Avatars)
    # Only show tracks that are currently active (considering start_time and end_time)
    # Get selected track IDs from URL parameter
    selected_track_ids_param = request.GET.get('track_ids')
    selected_track_ids: List[int] = []
    show_all_tracks = True  # Default: show all tracks (only if no track_ids parameter at all)
    
    if selected_track_ids_param and selected_track_ids_param.strip() and selected_track_ids_param.strip().lower() != 'none':
        # Parse comma-separated track IDs
        try:
            track_id_list = [tid.strip() for tid in selected_track_ids_param.split(',') if tid.strip() and tid.strip().lower() != 'none']
            selected_track_ids = [int(tid) for tid in track_id_list]
            show_all_tracks = False
        except (ValueError, TypeError):
            selected_track_ids = []
    elif selected_track_ids_param and selected_track_ids_param.strip().lower() == 'none':
        # Explicitly set to show no tracks
        show_all_tracks = False
        selected_track_ids = []
    
    active_tracks = TravelTrack.objects.filter(is_active=True, is_visible_on_map=True)
    # Filter by time if start_time or end_time is set
    now = timezone.now()
    active_tracks = [t for t in active_tracks if t.is_currently_active()]
    
    # Show all active tracks, including those without assigned groups
    # (Previously filtered to only show tracks with group_statuses, but now showing all)
    
    # Filter tracks by selected track IDs if track_ids parameter is set
    if not show_all_tracks:
        if selected_track_ids:
            # Show only selected tracks
            active_tracks = [t for t in active_tracks if t.id in selected_track_ids]
        else:
            # track_ids='none' - show no tracks
            active_tracks = []
    
    # Filter tracks by selected groups if groups are selected
    if target_groups:
        # Only show tracks that have at least one of the selected groups in their group_statuses
        selected_group_ids = [g.id for g in target_groups]
        active_tracks = [t for t in active_tracks if t.group_statuses.filter(group_id__in=selected_group_ids).exists()]
    
    tracks_data = []
    milestones_data = []
    active_track_ids = []  # Store IDs of active tracks for template
    for track in active_tracks:
        if track.geojson_data:
            tracks_data.append({'id': track.id, 'name': track.name, 'points': json.loads(track.geojson_data)})
            active_track_ids.append(track.id)
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
                'description': m.description or "",
                'external_link': m.external_link or "",
                'is_reached': m.winner_group is not None,
                'winner_group_name': m.winner_group.name if m.winner_group else None,
                'winner_parent_group_name': parent_group_name,  # TOP-Gruppe
                'reached_at': m.reached_at.isoformat() if m.reached_at else None,
                'track_id': track.id,
                'track_name': track.name,  # Track name for overlay display
                'track_total_length_km': float(track.total_length_km)
            })

    group_avatars = []
    # Get all group statuses of active tracks
    track_ids = [t.id for t in active_tracks]
    statuses = GroupTravelStatus.objects.filter(track_id__in=track_ids).select_related('group', 'track')
    
    # Filter statuses by selected groups if groups are selected
    if target_groups:
        selected_group_ids = [g.id for g in target_groups]
        # Get all descendant group IDs for each selected group
        all_group_ids = set()
        for tg in target_groups:
            all_group_ids.add(tg.id)
            # Add all descendant groups recursively
            def get_all_descendant_ids(ancestor_id: int, visited: set = None) -> set:
                if visited is None:
                    visited = set()
                if ancestor_id in visited:
                    return set()
                visited.add(ancestor_id)
                descendant_ids = {ancestor_id}
                direct_children = Group.objects.filter(
                    parent_id=ancestor_id,
                    is_visible=True
                ).values_list('id', flat=True)
                descendant_ids.update(direct_children)
                for child_id in direct_children:
                    if child_id not in visited:
                        descendant_ids.update(get_all_descendant_ids(child_id, visited))
                return descendant_ids
            all_group_ids.update(get_all_descendant_ids(tg.id))
        statuses = statuses.filter(group_id__in=all_group_ids)

    pos_counts = {}

    for s in statuses:
        if s.group.is_visible:
            # For avatar positioning: use only current_travel_distance (not historical)
            # This ensures avatars are at the start (0 km) when trip is restarted
            current_km = float(s.current_travel_distance)
            
            # For active trips: show only current_travel_distance (not historical)
            # Historical kilometers are only relevant for completed trips
            # When trip is restarted, current_travel_distance is 0, so display should also be 0
            display_km = current_km  # Show only current distance for active trips

            # IMPORTANT: Cap at total_length_km if goal is reached
            # This ensures no avatar shows more kilometers than the track length
            if s.track.total_length_km and current_km >= float(s.track.total_length_km):
                current_km = float(s.track.total_length_km)
            
            # Position is based on current_travel_distance only (0 km = start point)
            # We round to 2 decimal places for the offset key
            pos_key = f"{s.track.id}_{round(current_km, 2)}"
            count = pos_counts.get(pos_key, 0)
            pos_counts[pos_key] = count + 1

            # Check if group has reached the goal and find highest contributing leaf group
            top_contributor_leaf_group = None
            travel_duration_seconds = None
            if s.track.total_length_km and current_km >= float(s.track.total_length_km):
                # Group has reached the goal - find leaf group with highest contribution
                try:
                    top_contribution = LeafGroupTravelContribution.objects.filter(
                        track=s.track,
                        leaf_group__parent=s.group
                    ).select_related('leaf_group').order_by('-current_travel_distance').first()
                    
                    if top_contribution:
                        top_contributor_leaf_group = {
                            'name': top_contribution.leaf_group.name,
                            'display_name': top_contribution.leaf_group.get_kiosk_label(),
                            'contribution_km': float(top_contribution.current_travel_distance),
                            'logo': top_contribution.leaf_group.logo.url if top_contribution.leaf_group.logo else '/static/map/images/default_group.png'
                        }
                except Exception as e:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.debug(f"[map_page] Error finding top contributor for {s.group.name}: {e}")
                
                # Calculate travel duration if goal is reached
                # Use goal_reached_at if available, otherwise use current time as fallback
                end_time = s.goal_reached_at if s.goal_reached_at else timezone.now()
                
                # Find the start time from TravelHistory (action_type='assigned')
                # IMPORTANT: Only use the assigned entry that comes AFTER the most recent
                # 'restarted' or 'completed' entry to avoid summing travel times across restarts
                # Only consider entries that occurred BEFORE goal_reached_at
                # If no TravelHistory entry exists, use track.start_time as fallback
                try:
                    from api.models import TravelHistory
                    # First, find the most recent 'restarted' or 'completed' entry
                    # that occurred BEFORE or AT goal_reached_at
                    last_restart_or_complete = TravelHistory.objects.filter(
                        track=s.track,
                        group=s.group,
                        action_type__in=['restarted', 'completed'],
                        end_time__lte=end_time  # Only entries before or at goal_reached_at
                    ).order_by('-end_time').first()
                    
                    # Find the assigned entry that comes after the restart/completion
                    if last_restart_or_complete:
                        # Use assigned entry that starts after the restart/completion end time
                        # and before or at goal_reached_at
                        assigned_entry = TravelHistory.objects.filter(
                            track=s.track,
                            group=s.group,
                            action_type='assigned',
                            start_time__gt=last_restart_or_complete.end_time,
                            start_time__lte=end_time  # Must be before or at goal_reached_at
                        ).order_by('-start_time').first()
                        
                        if assigned_entry:
                            start_time = assigned_entry.start_time
                        else:
                            # No assigned entry after restart - use restart end time as start
                            # This handles the case where trip was restarted but no new assignment entry was created
                            start_time = last_restart_or_complete.end_time
                    else:
                        # No restart/completion found, use the most recent assigned entry
                        # that occurred before or at goal_reached_at
                        assigned_entry = TravelHistory.objects.filter(
                            track=s.track,
                            group=s.group,
                            action_type='assigned',
                            start_time__lte=end_time  # Must be before or at goal_reached_at
                        ).order_by('-start_time').first()
                        
                        if assigned_entry:
                            start_time = assigned_entry.start_time
                        else:
                            # Fallback: use track.start_time if available and before goal_reached_at
                            if s.track.start_time and s.track.start_time <= end_time:
                                start_time = s.track.start_time
                            else:
                                # If track.start_time is after goal_reached_at, use goal_reached_at as start
                                # This should not happen in normal operation, but prevents negative durations
                                start_time = end_time
                    
                    if start_time and start_time <= end_time:
                        travel_duration = end_time - start_time
                        travel_duration_seconds = int(travel_duration.total_seconds())
                        if travel_duration_seconds < 0:
                            travel_duration_seconds = None
                    else:
                        # Invalid time range - set to None
                        travel_duration_seconds = None
                except Exception as e:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(f"[map_page] Error calculating travel duration for {s.group.name}: {e}", exc_info=True)

            # Get parent group name (TOP-Gruppe)
            parent_group_name = None
            if s.group.parent:
                parent_group_name = s.group.parent.name

            group_avatars.append({
                'name': s.group.name,
                'display_name': s.group.get_kiosk_label(),  # Use short_name if available, otherwise name
                'parent_group_name': parent_group_name,  # TOP-Gruppe
                'km': current_km,  # Use current_km for positioning (0 = start point) - capped at total_length_km
                'logo': s.group.logo.url if s.group.logo else '/static/map/images/default_group.png',
                'track_id': s.track.id,
                'track_total_length_km': float(s.track.total_length_km) if s.track.total_length_km else 0,
                'offset_index': count,
                'goal_reached_at': s.goal_reached_at.isoformat() if s.goal_reached_at else None,  # For sorting at finish line
                'travel_duration_seconds': travel_duration_seconds,  # Travel time from start to goal in seconds
                'top_contributor_leaf_group': top_contributor_leaf_group  # Leaf group with highest contribution (if goal reached)
            })

    # Devices with GPS positions
    devices_data = []
    devices = Device.objects.filter(is_visible=True, gps_latitude__isnull=False, gps_longitude__isnull=False)
    for device in devices:
        devices_data.append({
            'name': device.display_name if device.display_name else device.name,
            'lat': float(device.gps_latitude),
            'lon': float(device.gps_longitude),
            'distance_total': float(device.distance_total),
            'last_active': device.last_active.isoformat() if device.last_active else None
        })

    # Event data - Show events that should be displayed (may include ended events to show results)
    active_events = Event.objects.filter(is_active=True, is_visible_on_map=True)
    # Filter by should_be_displayed() instead of is_currently_active()
    # This allows showing events after end_time until hide_after_date
    active_events = [e for e in active_events if e.should_be_displayed()]
    events_data = []
    now = timezone.now()
    for event in active_events:
        # Get all groups participating in this event
        event_groups = []
        for status in event.group_statuses.select_related('group').all():
            event_groups.append({
                'name': status.group.name,
                'km': round(float(status.current_distance_km), 3),
                'group_id': status.group.id
            })
        if event_groups:
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

    # Get only top-level master groups (parent groups) for the group selector dropdown
    # This limits the dropdown to the highest-level parent groups only
    # Note: URL parameter handling remains unchanged to support all groups from other apps
    all_groups = Group.objects.filter(is_visible=True, parent__isnull=True).order_by('name')
    
    # Get all available tracks for the track selector (all tracks with geojson data, not just active ones)
    all_tracks = TravelTrack.objects.filter(
        is_visible_on_map=True,
        geojson_data__isnull=False
    ).exclude(geojson_data='').order_by('name')
    
    # Determine track_ids for context - preserve 'none' if explicitly requested
    context_track_ids = None
    if not show_all_tracks and not selected_track_ids:
        context_track_ids = 'none'  # Preserve 'none' for URL parameter
    elif selected_track_ids:
        context_track_ids = ','.join(str(tid) for tid in selected_track_ids)  # Comma-separated IDs
    
    # Get popup settings
    popup_settings = MapPopupSettings.get_settings()
    
    # Create JSON for all tracks (needed for layer control, even if not all are visible)
    # This ensures the layer control always has access to all tracks, regardless of visibility
    all_tracks_data = []
    for track in all_tracks:
        if track.geojson_data:
            all_tracks_data.append({'id': track.id, 'name': track.name, 'points': json.loads(track.geojson_data)})
    
    context = {
        'hierarchy': hierarchy,
        'group_id': target_group_id,  # Comma-separated IDs or None
        'group_name': target_groups[0].name if target_groups else None,  # First group name for compatibility
        'target_groups': target_groups,  # List of selected groups
        'selected_group_ids': selected_group_ids,  # List of selected group IDs as strings
        'all_groups': all_groups,  # All groups for dropdown selector
        'all_tracks': all_tracks,  # All tracks for track selector
        'active_track_ids': active_track_ids,  # IDs of currently active tracks
        'track_ids': context_track_ids,  # Comma-separated track IDs or 'none' or None
        'selected_track_ids': [str(tid) for tid in selected_track_ids],  # List of selected track IDs as strings
        'refresh_interval': refresh_interval,
        'show_cyclists': show_cyclists,
        'tracks_json': json.dumps(all_tracks_data),  # Use all_tracks_data (all tracks) instead of tracks_data (only visible tracks) for layer control
        'milestones_json': json.dumps(milestones_data),
        'group_avatars_json': json.dumps(group_avatars),
        'devices_json': json.dumps(devices_data),
        'events_data': events_data,
        'weltmeister_popup_duration': popup_settings.weltmeister_popup_duration_seconds * 1000,  # Convert to milliseconds
        'milestone_popup_duration': popup_settings.milestone_popup_duration_seconds * 1000,  # Convert to milliseconds
        'weltmeister_popup_bg_color': popup_settings.weltmeister_popup_background_color,
        'weltmeister_popup_bg_color_end': popup_settings.weltmeister_popup_background_color_end,
        'weltmeister_popup_opacity': float(popup_settings.weltmeister_popup_opacity),
        'milestone_popup_bg_color': popup_settings.milestone_popup_background_color,
        'milestone_popup_opacity': float(popup_settings.milestone_popup_opacity),
    }

    # If HTMX request for table refresh, redirect to ranking app
    if request.headers.get('HX-Request') and request.GET.get('refresh_table'):
        from django.shortcuts import redirect
        return redirect('ranking:ranking_page')

    # Return mobile template for mobile devices, kiosk template for desktop
    template_name = 'map/map_mobile.html' if is_mobile else 'map/dashboard.html'
    return render(request, template_name, context)

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
        # Check ALL active cyclists for new kilometers
        # Show popup for EVERY cyclist who reaches a new kilometer to motivate them
        # If multiple cyclists reach new kilometers simultaneously, prioritize by:
        # 1. Highest session_km (most kilometers in this session)
        # 2. Most recently active (if same session_km)
        cyclists_with_new_km = []
        
        # Show popup for EVERY cyclist who reached a new kilometer
        # Use a queue system to ensure each cyclist gets their popup before any cyclist gets a second one
        # IMPORTANT: Queue logic is independent and evaluates ticker_data directly
        event_data = None
        # Get or initialize the popup queue in session
        popup_queue_key = 'weltmeister_popup_queue'
        popup_queue = request.session.get(popup_queue_key, [])
        
        # Independent queue logic: Check ALL active cyclists in ticker_data for new kilometers
        # This ensures we don't miss any cyclists, regardless of ticker logic
        import logging
        logger = logging.getLogger(__name__)
        
        if ticker_data:
            logger.info(f"[map_ticker] 🔍 Checking {len(ticker_data)} active cyclists for new kilometers")
            logger.info(f"[map_ticker] 📋 Current queue size: {len(popup_queue)} cyclists")
            
            # Build index of existing queue entries
            existing_cyclist_indices = {}  # Map cyclist_id to index in queue
            for idx, item in enumerate(popup_queue):
                existing_cyclist_indices[item['cyclist_id']] = idx
                logger.debug(f"[map_ticker] Queue entry {idx}: cyclist_id={item['cyclist_id']}, user_id={item['user_id']}, session_km={item['session_km']}")
            
            queue_updated = False
            cyclists_added = 0
            cyclists_updated = 0
            
            # Check each active cyclist independently
            for cyclist in ticker_data:
                cyclist_key = f"last_session_km_{cyclist['id']}"
                # Get last shown km, defaulting to 0 if not set
                last_shown_km_raw = request.session.get(cyclist_key)
                if last_shown_km_raw is None:
                    last_shown_km = 0
                else:
                    last_shown_km = int(last_shown_km_raw)
                
                current_session_km = float(cyclist['session_km'])
                current_session_km_int = int(current_session_km)
                
                logger.debug(f"[map_ticker] Queue check: Cyclist {cyclist['user_id']} (ID: {cyclist['id']}): current={current_session_km_int} km, last_shown={last_shown_km} km")
                
                # Check if this cyclist has reached a new whole kilometer
                if current_session_km_int > last_shown_km:
                    logger.info(f"[map_ticker] ✅ New kilometer detected for {cyclist['user_id']}: {last_shown_km} -> {current_session_km_int} km")
                    
                    cyclist_id = cyclist['id']
                    session_km_float = float(current_session_km_int)
                    
                    # Convert datetime to timestamp for JSON serialization
                    last_active_ts = cyclist['last_active'].timestamp() if cyclist['last_active'] else 0.0
                    # Convert Decimal to float for JSON serialization
                    total_km_float = float(cyclist['total_km'])
                    
                    if cyclist_id in existing_cyclist_indices:
                        # Cyclist already in queue
                        existing_idx = existing_cyclist_indices[cyclist_id]
                        existing_entry = popup_queue[existing_idx]
                        
                        if existing_idx == 0:
                            # Cyclist is at position 0 (next to be shown) - update kilometers but keep position
                            # This ensures the popup shows the latest kilometer value
                            popup_queue[existing_idx] = {
                                'cyclist_id': cyclist_id,
                                'session_km': session_km_float,
                                'key': cyclist_key,
                                'last_active_timestamp': last_active_ts,
                                'user_id': cyclist['user_id'],
                                'total_km': total_km_float
                            }
                            queue_updated = True
                            cyclists_updated += 1
                            logger.info(f"[map_ticker] 🔒 Updated position 0 cyclist {cyclist['user_id']} (ID: {cyclist_id}): {existing_entry['session_km']} -> {session_km_float} km (position locked)")
                        else:
                            # Cyclist is not at position 0 - DO NOT update, let them get their popup first
                            # This ensures fair rotation: each cyclist gets their popup before any cyclist gets a second one
                            logger.info(f"[map_ticker] ⏸️ Cyclist {cyclist['user_id']} (ID: {cyclist_id}) already in queue at position {existing_idx} with {existing_entry['session_km']} km - skipping update to ensure fair rotation")
                    else:
                        # New cyclist - add to queue
                        popup_queue.append({
                            'cyclist_id': cyclist_id,
                            'session_km': session_km_float,
                            'key': cyclist_key,
                            'last_active_timestamp': last_active_ts,
                            'user_id': cyclist['user_id'],
                            'total_km': total_km_float
                        })
                        queue_updated = True
                        cyclists_added += 1
                        logger.info(f"[map_ticker] 📝 Added {cyclist['user_id']} (ID: {cyclist_id}) to queue with {session_km_float} km")
                elif current_session_km_int < last_shown_km:
                    # Session reset or cyclist restarted - reset tracking
                    logger.info(f"[map_ticker] ⚠️ Session reset detected for {cyclist['user_id']}: last_shown={last_shown_km} > current={current_session_km_int}, resetting")
                    request.session[cyclist_key] = current_session_km_int
                    request.session.modified = True
            
            # Save queue to session immediately if it was updated
            if queue_updated:
                request.session[popup_queue_key] = popup_queue
                request.session.modified = True
                logger.info(f"[map_ticker] 📝 Queue saved: {len(popup_queue)} cyclists in queue (added: {cyclists_added}, updated: {cyclists_updated})")
                # Log all cyclists in queue BEFORE sorting for debugging
                logger.info(f"[map_ticker] 📋 Queue BEFORE sorting:")
                for idx, item in enumerate(popup_queue):
                    logger.info(f"[map_ticker]   Queue[{idx}]: {item['user_id']} (ID: {item['cyclist_id']}) - {item['session_km']} km")
            
        # Sort queue by session_km descending, then by last_active_timestamp descending
        # IMPORTANT: Position 0 is locked - the cyclist at position 0 cannot be displaced
        # This ensures fair rotation: each cyclist gets their popup before any cyclist gets a second one
        # Process queue even if no new kilometers were detected (to show queued cyclists)
        if popup_queue:
            # Lock position 0 - save the cyclist at position 0
            locked_cyclist = None
            if len(popup_queue) > 0:
                locked_cyclist = popup_queue[0]
                logger.info(f"[map_ticker] 🔒 Locking position 0: {locked_cyclist['user_id']} (ID: {locked_cyclist['cyclist_id']}) with {locked_cyclist['session_km']} km")
            
            # Sort the rest of the queue (positions 1 and onwards)
            if len(popup_queue) > 1:
                rest_of_queue = popup_queue[1:]
                rest_of_queue.sort(key=lambda x: (x['session_km'], x['last_active_timestamp']), reverse=True)
                # Reconstruct queue with locked position 0
                popup_queue = [locked_cyclist] + rest_of_queue if locked_cyclist else rest_of_queue
            elif locked_cyclist:
                # Only one cyclist in queue - keep them at position 0
                popup_queue = [locked_cyclist]
            
            # Log queue AFTER sorting for debugging
            logger.info(f"[map_ticker] 📋 Queue AFTER sorting (position 0 locked):")
            for idx, item in enumerate(popup_queue):
                lock_indicator = "🔒" if idx == 0 else "  "
                logger.info(f"[map_ticker]   {lock_indicator} Queue[{idx}]: {item['user_id']} (ID: {item['cyclist_id']}) - {item['session_km']} km")
            
            # Get the first cyclist from the queue for this update (always position 0, which is locked)
            best_cyclist_data = popup_queue[0]
            trigger_cyclist_id = best_cyclist_data['cyclist_id']
            logger.info(f"[map_ticker] 🎯 Selected cyclist from queue: {best_cyclist_data['user_id']} (ID: {trigger_cyclist_id}) with {best_cyclist_data['session_km']} km")
            
            # Find the full cyclist data from ticker_data
            trigger_cyclist = None
            for cyclist in ticker_data:
                if cyclist['id'] == trigger_cyclist_id:
                    trigger_cyclist = cyclist
                    break
            
            if trigger_cyclist:
                current_session_km = best_cyclist_data['session_km']
                
                # Remove this cyclist from the queue (they will get their popup now)
                popup_queue.pop(0)
                
                # Update session: remove from queue and mark as shown
                request.session[popup_queue_key] = popup_queue
                request.session[best_cyclist_data['key']] = current_session_km
                request.session.modified = True
                
                # Get parent group name for weltmeister popup
                parent_group_name = None
                try:
                    # Find the cyclist's primary group and get its parent
                    # Use prefetch_related for ManyToMany relationship (groups is ManyToMany)
                    cyclist_obj = Cyclist.objects.filter(id=trigger_cyclist['id']).prefetch_related('groups').first()
                    if cyclist_obj:
                        primary_group = cyclist_obj.groups.first()
                        if primary_group and primary_group.parent_id:
                            # Load parent group directly from database
                            try:
                                parent_group = Group.objects.get(id=primary_group.parent_id)
                                parent_group_name = parent_group.name
                            except Group.DoesNotExist:
                                pass
                except Exception as e:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(f"[map_ticker] Error getting parent group for cyclist {trigger_cyclist['id']}: {e}", exc_info=True)
                
                event_data = {
                    'type': 'km_update',
                    'name': trigger_cyclist['user_id'],
                    'km': current_session_km,
                    'icon': '👑',
                    'parent_group_name': parent_group_name  # TOP-Gruppe
                }
                # Trophy for milestones (every 100 total kilometers)
                if int(trigger_cyclist['total_km']) % 100 == 0:
                    event_data['type'] = 'milestone'
                    event_data['icon'] = '🏆'
                
                # Debug logging
                import logging
                logger = logging.getLogger(__name__)
                logger.info(f"[map_ticker] 🎉 Showing weltmeister popup for {trigger_cyclist['user_id']} with {current_session_km} km (type: {event_data['type']}), parent_group: {parent_group_name}")
                logger.info(f"[map_ticker] 📋 Remaining cyclists in queue: {len(popup_queue)} (will be shown in next updates)")
            else:
                # Cyclist not found in ticker_data (maybe inactive now) - remove from queue
                popup_queue.pop(0)
                request.session[popup_queue_key] = popup_queue
                request.session.modified = True

    return render(request, 'map/partials/live_ticker.html', {
        'active_cyclists': ticker_data,
        'event': event_data,
        'target_group': target_group  # Pass target_group to template for conditional display
    })

def get_group_avatars(request):
    """Returns the current avatar positions as JSON for automatic map updates."""
    active_tracks = TravelTrack.objects.filter(is_active=True, is_visible_on_map=True)
    # Filter by time if start_time or end_time is set
    now = timezone.now()
    active_tracks = [t for t in active_tracks if t.is_currently_active()]
    track_ids = [t.id for t in active_tracks]

    group_avatars = []
    pos_counts = {}

    statuses = GroupTravelStatus.objects.filter(track_id__in=track_ids).select_related('group', 'track')

    # Filtering by group_id or group_name, if specified (e.g., in kiosk mode)
    target_group_id = request.GET.get('group_id')
    target_group_name = request.GET.get('group_name')
    target_group = None

    if target_group_id and target_group_id.strip() and target_group_id != 'None':
        # URL decoding for group names with spaces
        target_group_id = unquote(target_group_id)
        try:
            # Try first as numeric ID
            target_group = Group.objects.get(id=int(target_group_id), is_visible=True)
        except (ValueError, Group.DoesNotExist):
            # If no valid ID, try as name
            try:
                target_group = Group.objects.get(name=target_group_id, is_visible=True)
            except Group.DoesNotExist:
                pass
    elif target_group_name and target_group_name.strip():
        # URL decoding for group names with spaces
        target_group_name = unquote(target_group_name)
        # Search for group name
        try:
            target_group = Group.objects.get(name=target_group_name, is_visible=True)
        except Group.DoesNotExist:
            pass

    if target_group:
        # Filter only this group and its subgroups
        group_ids = [target_group.id]
        group_ids.extend(target_group.children.filter(is_visible=True).values_list('id', flat=True))
        statuses = statuses.filter(group_id__in=group_ids)

    # Check milestones for all groups before returning avatar positions
    # This ensures milestones are detected even when avatars are updated on the map
    # IMPORTANT: Only check milestones if the group has actually traveled (current_travel_distance > 0)
    # This prevents unnecessary debug messages when no cyclists are currently riding
    checked_groups = set()
    for s in statuses:
        if s.group.is_visible and s.group.id not in checked_groups:
            # Only check milestones if the group has actually traveled some distance
            # This prevents unnecessary debug messages when no activity is happening
            if s.current_travel_distance and s.current_travel_distance > 0:
                # Check milestones for this group
                # No active_leaf_group available in this context, so pass None
                check_milestone_victory(s.group, active_leaf_group=None)
            checked_groups.add(s.group.id)

    # Import LeafGroupTravelContribution for finding highest contributor
    from api.models import LeafGroupTravelContribution
    
    for s in statuses:
        if s.group.is_visible:
            # For avatar positioning: use only current_travel_distance (not historical)
            # This ensures avatars are at the start (0 km) when trip is restarted
            current_km = float(s.current_travel_distance)
            
            # IMPORTANT: Cap at total_length_km if goal is reached
            # This ensures no avatar shows more kilometers than the track length
            # This prevents display of values greater than the maximum track length
            if s.track.total_length_km and current_km >= float(s.track.total_length_km):
                current_km = float(s.track.total_length_km)
            
            # For active trips: show only current_travel_distance (not historical)
            # Historical kilometers are only relevant for completed trips
            # When trip is restarted, current_travel_distance is 0, so display should also be 0
            display_km = current_km  # Show only current distance for active trips (capped at goal)

            # Position is based on current_travel_distance only (0 km = start point)
            # We round to 2 decimal places for the offset key
            pos_key = f"{s.track.id}_{round(current_km, 2)}"
            count = pos_counts.get(pos_key, 0)
            pos_counts[pos_key] = count + 1

            # Check if group has reached the goal and find highest contributing leaf group
            top_contributor_leaf_group = None
            travel_duration_seconds = None
            if s.track.total_length_km and current_km >= float(s.track.total_length_km):
                # Group has reached the goal - find leaf group with highest contribution
                try:
                    top_contribution = LeafGroupTravelContribution.objects.filter(
                        track=s.track,
                        leaf_group__parent=s.group
                    ).select_related('leaf_group').order_by('-current_travel_distance').first()
                    
                    if top_contribution:
                        top_contributor_leaf_group = {
                            'name': top_contribution.leaf_group.name,
                            'display_name': top_contribution.leaf_group.get_kiosk_label(),
                            'contribution_km': float(top_contribution.current_travel_distance),
                            'logo': top_contribution.leaf_group.logo.url if top_contribution.leaf_group.logo else '/static/map/images/default_group.png'
                        }
                except Exception as e:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.debug(f"[get_group_avatars] Error finding top contributor for {s.group.name}: {e}")
                
                # Calculate travel duration if goal is reached
                # Use goal_reached_at if available, otherwise use current time as fallback
                end_time = s.goal_reached_at if s.goal_reached_at else timezone.now()
                
                # Find the start time from TravelHistory (action_type='assigned')
                # IMPORTANT: Only use the assigned entry that comes AFTER the most recent
                # 'restarted' or 'completed' entry to avoid summing travel times across restarts
                # Only consider entries that occurred BEFORE goal_reached_at
                # If no TravelHistory entry exists, use track.start_time as fallback
                try:
                    from api.models import TravelHistory
                    # First, find the most recent 'restarted' or 'completed' entry
                    # that occurred BEFORE or AT goal_reached_at
                    last_restart_or_complete = TravelHistory.objects.filter(
                        track=s.track,
                        group=s.group,
                        action_type__in=['restarted', 'completed'],
                        end_time__lte=end_time  # Only entries before or at goal_reached_at
                    ).order_by('-end_time').first()
                    
                    # Find the assigned entry that comes after the restart/completion
                    if last_restart_or_complete:
                        # Use assigned entry that starts after the restart/completion end time
                        # and before or at goal_reached_at
                        assigned_entry = TravelHistory.objects.filter(
                            track=s.track,
                            group=s.group,
                            action_type='assigned',
                            start_time__gt=last_restart_or_complete.end_time,
                            start_time__lte=end_time  # Must be before or at goal_reached_at
                        ).order_by('-start_time').first()
                        
                        if assigned_entry:
                            start_time = assigned_entry.start_time
                        else:
                            # No assigned entry after restart - use restart end time as start
                            # This handles the case where trip was restarted but no new assignment entry was created
                            start_time = last_restart_or_complete.end_time
                    else:
                        # No restart/completion found, use the most recent assigned entry
                        # that occurred before or at goal_reached_at
                        assigned_entry = TravelHistory.objects.filter(
                            track=s.track,
                            group=s.group,
                            action_type='assigned',
                            start_time__lte=end_time  # Must be before or at goal_reached_at
                        ).order_by('-start_time').first()
                        
                        if assigned_entry:
                            start_time = assigned_entry.start_time
                        else:
                            # Fallback: use track.start_time if available and before goal_reached_at
                            if s.track.start_time and s.track.start_time <= end_time:
                                start_time = s.track.start_time
                            else:
                                # If track.start_time is after goal_reached_at, use goal_reached_at as start
                                # This should not happen in normal operation, but prevents negative durations
                                start_time = end_time
                    
                    if start_time and start_time <= end_time:
                        travel_duration = end_time - start_time
                        travel_duration_seconds = int(travel_duration.total_seconds())
                        if travel_duration_seconds < 0:
                            travel_duration_seconds = None
                    else:
                        # Invalid time range - set to None
                        travel_duration_seconds = None
                except Exception as e:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(f"[get_group_avatars] Error calculating travel duration for {s.group.name}: {e}", exc_info=True)

            # Get parent group name (TOP-Gruppe)
            parent_group_name = None
            if s.group.parent:
                parent_group_name = s.group.parent.name

            group_avatars.append({
                'name': s.group.name,
                'display_name': s.group.get_kiosk_label(),  # Use short_name if available, otherwise name
                'parent_group_name': parent_group_name,  # TOP-Gruppe
                'km': current_km,  # Use current_km for positioning (0 = start point) - capped at total_length_km
                'logo': s.group.logo.url if s.group.logo else '/static/map/images/default_group.png',
                'track_id': s.track.id,
                'track_total_length_km': float(s.track.total_length_km) if s.track.total_length_km else 0,
                'offset_index': count,
                'goal_reached_at': s.goal_reached_at.isoformat() if s.goal_reached_at else None,  # For sorting at finish line
                'travel_duration_seconds': travel_duration_seconds,  # Travel time from start to goal in seconds
                'top_contributor_leaf_group': top_contributor_leaf_group  # Leaf group with highest contribution (if goal reached)
            })

    return JsonResponse({'avatars': group_avatars})

def get_new_milestones(request):
    """Returns newly reached milestones that have not been displayed yet."""
    group_id = request.GET.get('group_id')
    group_name = request.GET.get('group_name')
    last_check = request.GET.get('last_check')  # Timestamp of last check

    target_group = None
    group_ids = []

    # Find the group
    if group_id and group_id.strip() and group_id != 'None':
        group_id = unquote(group_id)
        try:
            target_group = Group.objects.get(id=int(group_id), is_visible=True)
        except (ValueError, Group.DoesNotExist):
            try:
                target_group = Group.objects.get(name=group_id, is_visible=True)
            except Group.DoesNotExist:
                pass
    elif group_name and group_name.strip():
        group_name = unquote(group_name)
        try:
            target_group = Group.objects.get(name=group_name, is_visible=True)
        except Group.DoesNotExist:
            pass

    # Get active tracks to filter milestones
    active_tracks = TravelTrack.objects.filter(is_active=True, is_visible_on_map=True)
    # Filter by time if start_time or end_time is set
    now = timezone.now()
    active_tracks = [t for t in active_tracks if t.is_currently_active()]
    track_ids = [t.id for t in active_tracks]

    if not track_ids:
        # No active tracks, return empty list
        return JsonResponse({'milestones': []})

    # Simplified logic: Get all reached milestones on active tracks
    # Filter by group if specified, otherwise show all
    if target_group:
        # Find all milestones reached by this group or its subgroups
        group_ids = [target_group.id]
        group_ids.extend(target_group.children.filter(is_visible=True).values_list('id', flat=True))
        query = Milestone.objects.filter(
            winner_group_id__in=group_ids,
            track_id__in=track_ids,  # Only milestones on active tracks
            winner_group__isnull=False,  # Only reached milestones
            reached_at__isnull=False  # Must have a reached_at timestamp
        ).exclude(distance_km=0).select_related('winner_group', 'track')
    else:
        # Show all reached milestones on active tracks
        query = Milestone.objects.filter(
            winner_group__isnull=False,  # Only reached milestones
            track_id__in=track_ids,  # Only milestones on active tracks
            reached_at__isnull=False  # Must have a reached_at timestamp
        ).exclude(distance_km=0).select_related('winner_group', 'track')

    # Filter for newly reached milestones (if last_check specified)
    # Add a buffer to account for timing differences
    if last_check:
        try:
            # Parse ISO format timestamp
            last_check_time = timezone.datetime.fromisoformat(last_check.replace('Z', '+00:00'))
            if timezone.is_naive(last_check_time):
                last_check_time = timezone.make_aware(last_check_time)
            # Subtract 10 seconds to ensure we catch milestones that were just reached
            # This accounts for timing differences between backend and frontend
            last_check_time = last_check_time - timedelta(seconds=10)
            query = query.filter(reached_at__gt=last_check_time)
        except Exception as e:
            # If parsing fails, ignore the filter
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"[get_new_milestones] Failed to parse last_check: {e}")
            pass

    # Sort by reached time (newest first)
    new_milestones = list(query.order_by('-reached_at')[:10])

    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"[get_new_milestones] Found {len(new_milestones)} milestones matching criteria")
    logger.debug(f"[get_new_milestones] Active tracks: {track_ids}")
    if last_check:
        logger.debug(f"[get_new_milestones] Filtering by last_check: {last_check}")
    if target_group:
        logger.debug(f"[get_new_milestones] Filtering by target_group: {target_group.name}")

    milestones_data = []
    for ms in new_milestones:
        # Skip start point milestones (0 km)
        if float(ms.distance_km) < 0.001:
            continue
        if ms.winner_group and ms.reached_at:  # Ensure winner_group and reached_at exist
            # Get parent group name if winner_group has a parent
            parent_group_name = None
            if ms.winner_group.parent:
                parent_group_name = ms.winner_group.parent.name
            
            milestones_data.append({
                'id': ms.id,
                'name': ms.name,
                'reward_text': ms.reward_text or '',
                'description': ms.description or '',
                'external_link': ms.external_link or '',
                'group_name': ms.winner_group.name,
                'parent_group_name': parent_group_name,  # TOP-Gruppe
                'reached_at': ms.reached_at.isoformat(),
                'km': float(ms.distance_km),  # Use 'km' to match frontend expectations
                'distance_km': float(ms.distance_km),  # Keep for backwards compatibility
                'lat': float(ms.gps_latitude) if ms.gps_latitude else None,  # Add coordinates for popup display
                'lon': float(ms.gps_longitude) if ms.gps_longitude else None,
                'track_name': ms.track.name if ms.track else None  # Track name for overlay display
            })
            logger.info(f"[get_new_milestones] ✅ Returning milestone: '{ms.name}' (ID: {ms.id}) reached by '{ms.winner_group.name}' at {ms.reached_at}")

    logger.info(f"[get_new_milestones] Returning {len(milestones_data)} milestones to frontend")
    return JsonResponse({'milestones': milestones_data})

def get_all_milestones_status(request):
    """Returns current status of all milestones for active tracks (for marker updates after reset)."""
    group_id = request.GET.get('group_id')
    group_name = request.GET.get('group_name')

    target_group = None

    # Find the group
    if group_id and group_id.strip() and group_id != 'None':
        group_id = unquote(group_id)
        try:
            target_group = Group.objects.get(id=int(group_id), is_visible=True)
        except (ValueError, Group.DoesNotExist):
            try:
                target_group = Group.objects.get(name=group_id, is_visible=True)
            except Group.DoesNotExist:
                pass
    elif group_name and group_name.strip():
        group_name = unquote(group_name)
        try:
            target_group = Group.objects.get(name=group_name, is_visible=True)
        except Group.DoesNotExist:
            pass

    # Get active tracks to filter milestones
    active_tracks = TravelTrack.objects.filter(is_active=True, is_visible_on_map=True)
    # Filter by time if start_time or end_time is set
    now = timezone.now()
    active_tracks = [t for t in active_tracks if t.is_currently_active()]
    track_ids = [t.id for t in active_tracks]

    if not track_ids:
        # No active tracks, return empty list
        return JsonResponse({'milestones': []})

    # Get all milestones on active tracks, excluding start point (0 km)
    query = Milestone.objects.filter(
        track_id__in=track_ids,
        gps_latitude__isnull=False,
        gps_longitude__isnull=False
    ).exclude(distance_km=0).select_related('winner_group', 'track')

    # Filter by group if specified
    if target_group:
        group_ids = [target_group.id]
        group_ids.extend(target_group.children.filter(is_visible=True).values_list('id', flat=True))
        # Only show milestones that belong to tracks where this group participates
        # or milestones reached by this group
        query = query.filter(
            Q(track__group_statuses__group_id__in=group_ids) |
            Q(winner_group_id__in=group_ids)
        ).distinct()

    milestones_data = []
    for ms in query:
        # Skip start point milestones (0 km)
        if float(ms.distance_km) < 0.001:
            continue
        milestones_data.append({
            'id': ms.id,
            'name': ms.name,
            'reward_text': ms.reward_text or '',
            'description': ms.description or '',
            'external_link': ms.external_link or '',
            'lat': float(ms.gps_latitude) if ms.gps_latitude else None,
            'lon': float(ms.gps_longitude) if ms.gps_longitude else None,
            'is_reached': ms.winner_group is not None,
            'winner_group_name': ms.winner_group.name if ms.winner_group else None,
            'winner_parent_group_name': ms.winner_group.parent.name if (ms.winner_group and ms.winner_group.parent) else None,  # TOP-Gruppe
            'reached_at': ms.reached_at.isoformat() if ms.reached_at else None,
            'km': float(ms.distance_km),
            'text': ms.reward_text or "",
            'track_name': ms.track.name if ms.track else None  # Track name for overlay display
        })

    return JsonResponse({'milestones': milestones_data})


def map_ticker(request: HttpRequest) -> HttpResponse:
    """
    Ticker view with session kilometers for active cyclists.
    
    This is the map app's own ticker implementation, independent of the leaderboard app.
    Shows active cyclists with their session kilometers in a scrolling ticker format.
    
    Args:
        request: HTTP request object.
    
    Returns:
        HTTP response with ticker data.
    """
    from urllib.parse import unquote
    from api.models import Group
    
    group_id = request.GET.get('group_id')
    group_name = request.GET.get('group_name')
    now = timezone.now()
    active_cutoff = now - timedelta(seconds=60)
    
    # Access via OneToOneField 'cyclistdevicecurrentmileage'
    # Filter for visible cyclists with non-null last_active and recent activity
    base_cyclists = Cyclist.objects.filter(
        is_visible=True,
        last_active__isnull=False,
        last_active__gte=active_cutoff
    ).select_related('cyclistdevicecurrentmileage').prefetch_related('groups')
    
    target_group = None
    # Support both group_id and group_name parameters
    group_identifier = group_id or group_name
    if group_identifier and group_identifier.strip() and group_identifier != 'None':
        # URL decoding for group names with spaces
        group_identifier = unquote(group_identifier)
        try:
            # Try first as numeric ID
            target_group = Group.objects.get(id=int(group_identifier))
        except (ValueError, Group.DoesNotExist):
            # If no valid ID, try as name
            try:
                target_group = Group.objects.get(name=group_identifier)
            except Group.DoesNotExist:
                target_group = None
        
        if target_group:
            # Recursively find all descendant group IDs (including the target group itself)
            def get_all_descendant_ids(ancestor_id: int, visited: set = None) -> set:
                """Recursively get all descendant group IDs (only visible groups)."""
                if visited is None:
                    visited = set()
                
                # Prevent infinite loops
                if ancestor_id in visited:
                    return set()
                visited.add(ancestor_id)
                
                descendant_ids = {ancestor_id}  # Include the target group itself
                
                # Start with direct children (only visible ones)
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
            
            # Get all descendant IDs (including the target group itself)
            group_ids = get_all_descendant_ids(target_group.id)
            
            # Filter cyclists to only those in the target group or its subgroups
            if group_ids:
                base_cyclists = base_cyclists.filter(groups__id__in=group_ids).distinct()
            else:
                # No subgroups found - only show cyclists directly in the target group
                base_cyclists = base_cyclists.filter(groups__id=target_group.id)
    
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
        
        # Get top parent group's kiosk label (same logic as leaderboard)
        group_short_name = ''
        primary_group = cyclist.groups.first()
        if primary_group:
            try:
                # Navigate to top parent group
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
                
                # Get kiosk label from top parent
                if top_parent and top_parent.id != primary_group.id:
                    top_parent = Group.objects.get(id=top_parent.id)
                    group_short_name = top_parent.get_kiosk_label()
                else:
                    # No parent found, use primary group
                    group_short_name = primary_group.get_kiosk_label()
            except (RecursionError, AttributeError, RuntimeError, Group.DoesNotExist):
                # Fallback to primary group's kiosk label
                try:
                    group_short_name = primary_group.get_kiosk_label()
                except:
                    group_short_name = primary_group.name
        
        # Always include cyclist, even if session_km is 0
        ticker_data.append({
            'id': cyclist.id,
            'user_id': cyclist.user_id,
            'session_km': s_km,
            'total_km': cyclist.distance_total,
            'last_active': cyclist.last_active,
            'group_short_name': group_short_name
        })
    
    ticker_data = sorted(ticker_data, key=lambda x: x['session_km'], reverse=True)[:10]
    
    event_data = None
    if ticker_data:
        # Check ALL active cyclists for new kilometers
        # Show popup for EVERY cyclist who reaches a new kilometer to motivate them
        # If multiple cyclists reach new kilometers simultaneously, prioritize by:
        # 1. Highest session_km (most kilometers in this session)
        # 2. Most recently active (if same session_km)
        cyclists_with_new_km = []
        
        # Show popup for EVERY cyclist who reached a new kilometer
        # Use a queue system to ensure each cyclist gets their popup before any cyclist gets a second one
        # IMPORTANT: Queue logic is independent and evaluates ticker_data directly
        event_data = None
        # Get or initialize the popup queue in session
        popup_queue_key = 'weltmeister_popup_queue'
        popup_queue = request.session.get(popup_queue_key, [])
        
        # Independent queue logic: Check ALL active cyclists in ticker_data for new kilometers
        # This ensures we don't miss any cyclists, regardless of ticker logic
        import logging
        logger = logging.getLogger(__name__)
        
        if ticker_data:
            logger.info(f"[map_ticker] 🔍 Checking {len(ticker_data)} active cyclists for new kilometers")
            logger.info(f"[map_ticker] 📋 Current queue size: {len(popup_queue)} cyclists")
            
            # Build index of existing queue entries
            existing_cyclist_indices = {}  # Map cyclist_id to index in queue
            for idx, item in enumerate(popup_queue):
                existing_cyclist_indices[item['cyclist_id']] = idx
                logger.debug(f"[map_ticker] Queue entry {idx}: cyclist_id={item['cyclist_id']}, user_id={item['user_id']}, session_km={item['session_km']}")
            
            queue_updated = False
            cyclists_added = 0
            cyclists_updated = 0
            
            # Check each active cyclist independently
            for cyclist in ticker_data:
                cyclist_key = f"last_session_km_{cyclist['id']}"
                # Get last shown km, defaulting to 0 if not set
                last_shown_km_raw = request.session.get(cyclist_key)
                if last_shown_km_raw is None:
                    last_shown_km = 0
                else:
                    last_shown_km = int(last_shown_km_raw)
                
                current_session_km = float(cyclist['session_km'])
                current_session_km_int = int(current_session_km)
                
                logger.debug(f"[map_ticker] Queue check: Cyclist {cyclist['user_id']} (ID: {cyclist['id']}): current={current_session_km_int} km, last_shown={last_shown_km} km")
                
                # Check if this cyclist has reached a new whole kilometer
                if current_session_km_int > last_shown_km:
                    logger.info(f"[map_ticker] ✅ New kilometer detected for {cyclist['user_id']}: {last_shown_km} -> {current_session_km_int} km")
                    
                    cyclist_id = cyclist['id']
                    session_km_float = float(current_session_km_int)
                    
                    # Convert datetime to timestamp for JSON serialization
                    last_active_ts = cyclist['last_active'].timestamp() if cyclist['last_active'] else 0.0
                    # Convert Decimal to float for JSON serialization
                    total_km_float = float(cyclist['total_km'])
                    
                    if cyclist_id in existing_cyclist_indices:
                        # Cyclist already in queue
                        existing_idx = existing_cyclist_indices[cyclist_id]
                        existing_entry = popup_queue[existing_idx]
                        
                        if existing_idx == 0:
                            # Cyclist is at position 0 (next to be shown) - update kilometers but keep position
                            # This ensures the popup shows the latest kilometer value
                            popup_queue[existing_idx] = {
                                'cyclist_id': cyclist_id,
                                'session_km': session_km_float,
                                'key': cyclist_key,
                                'last_active_timestamp': last_active_ts,
                                'user_id': cyclist['user_id'],
                                'total_km': total_km_float
                            }
                            queue_updated = True
                            cyclists_updated += 1
                            logger.info(f"[map_ticker] 🔒 Updated position 0 cyclist {cyclist['user_id']} (ID: {cyclist_id}): {existing_entry['session_km']} -> {session_km_float} km (position locked)")
                        else:
                            # Cyclist is not at position 0 - DO NOT update, let them get their popup first
                            # This ensures fair rotation: each cyclist gets their popup before any cyclist gets a second one
                            logger.info(f"[map_ticker] ⏸️ Cyclist {cyclist['user_id']} (ID: {cyclist_id}) already in queue at position {existing_idx} with {existing_entry['session_km']} km - skipping update to ensure fair rotation")
                    else:
                        # New cyclist - add to queue
                        popup_queue.append({
                            'cyclist_id': cyclist_id,
                            'session_km': session_km_float,
                            'key': cyclist_key,
                            'last_active_timestamp': last_active_ts,
                            'user_id': cyclist['user_id'],
                            'total_km': total_km_float
                        })
                        queue_updated = True
                        cyclists_added += 1
                        logger.info(f"[map_ticker] 📝 Added {cyclist['user_id']} (ID: {cyclist_id}) to queue with {session_km_float} km")
                elif current_session_km_int < last_shown_km:
                    # Session reset or cyclist restarted - reset tracking
                    logger.info(f"[map_ticker] ⚠️ Session reset detected for {cyclist['user_id']}: last_shown={last_shown_km} > current={current_session_km_int}, resetting")
                    request.session[cyclist_key] = current_session_km_int
                    request.session.modified = True
            
            # Save queue to session immediately if it was updated
            if queue_updated:
                request.session[popup_queue_key] = popup_queue
                request.session.modified = True
                logger.info(f"[map_ticker] 📝 Queue saved: {len(popup_queue)} cyclists in queue (added: {cyclists_added}, updated: {cyclists_updated})")
                # Log all cyclists in queue BEFORE sorting for debugging
                logger.info(f"[map_ticker] 📋 Queue BEFORE sorting:")
                for idx, item in enumerate(popup_queue):
                    logger.info(f"[map_ticker]   Queue[{idx}]: {item['user_id']} (ID: {item['cyclist_id']}) - {item['session_km']} km")
            
        # Sort queue by session_km descending, then by last_active_timestamp descending
        # IMPORTANT: Position 0 is locked - the cyclist at position 0 cannot be displaced
        # This ensures fair rotation: each cyclist gets their popup before any cyclist gets a second one
        # Process queue even if no new kilometers were detected (to show queued cyclists)
        if popup_queue:
            # Lock position 0 - save the cyclist at position 0
            locked_cyclist = None
            if len(popup_queue) > 0:
                locked_cyclist = popup_queue[0]
                logger.info(f"[map_ticker] 🔒 Locking position 0: {locked_cyclist['user_id']} (ID: {locked_cyclist['cyclist_id']}) with {locked_cyclist['session_km']} km")
            
            # Sort the rest of the queue (positions 1 and onwards)
            if len(popup_queue) > 1:
                rest_of_queue = popup_queue[1:]
                rest_of_queue.sort(key=lambda x: (x['session_km'], x['last_active_timestamp']), reverse=True)
                # Reconstruct queue with locked position 0
                popup_queue = [locked_cyclist] + rest_of_queue if locked_cyclist else rest_of_queue
            elif locked_cyclist:
                # Only one cyclist in queue - keep them at position 0
                popup_queue = [locked_cyclist]
            
            # Log queue AFTER sorting for debugging
            logger.info(f"[map_ticker] 📋 Queue AFTER sorting (position 0 locked):")
            for idx, item in enumerate(popup_queue):
                lock_indicator = "🔒" if idx == 0 else "  "
                logger.info(f"[map_ticker]   {lock_indicator} Queue[{idx}]: {item['user_id']} (ID: {item['cyclist_id']}) - {item['session_km']} km")
            
            # Get the first cyclist from the queue for this update (always position 0, which is locked)
            best_cyclist_data = popup_queue[0]
            trigger_cyclist_id = best_cyclist_data['cyclist_id']
            logger.info(f"[map_ticker] 🎯 Selected cyclist from queue: {best_cyclist_data['user_id']} (ID: {trigger_cyclist_id}) with {best_cyclist_data['session_km']} km")
            
            # Find the full cyclist data from ticker_data
            trigger_cyclist = None
            for cyclist in ticker_data:
                if cyclist['id'] == trigger_cyclist_id:
                    trigger_cyclist = cyclist
                    break
            
            if trigger_cyclist:
                current_session_km = best_cyclist_data['session_km']
                
                # Remove this cyclist from the queue (they will get their popup now)
                popup_queue.pop(0)
                
                # Update session: remove from queue and mark as shown
                request.session[popup_queue_key] = popup_queue
                request.session[best_cyclist_data['key']] = current_session_km
                request.session.modified = True
                
                # Get parent group name for weltmeister popup
                parent_group_name = None
                try:
                    # Find the cyclist's primary group and get its parent
                    # Use prefetch_related for ManyToMany relationship (groups is ManyToMany)
                    cyclist_obj = Cyclist.objects.filter(id=trigger_cyclist['id']).prefetch_related('groups').first()
                    if cyclist_obj:
                        primary_group = cyclist_obj.groups.first()
                        if primary_group and primary_group.parent_id:
                            # Load parent group directly from database
                            try:
                                parent_group = Group.objects.get(id=primary_group.parent_id)
                                parent_group_name = parent_group.name
                            except Group.DoesNotExist:
                                pass
                except Exception as e:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(f"[map_ticker] Error getting parent group for cyclist {trigger_cyclist['id']}: {e}", exc_info=True)
                
                event_data = {
                    'type': 'km_update',
                    'name': trigger_cyclist['user_id'],
                    'km': current_session_km,
                    'icon': '👑',
                    'parent_group_name': parent_group_name  # TOP-Gruppe
                }
                # Trophy for milestones (every 100 total kilometers)
                if int(trigger_cyclist['total_km']) % 100 == 0:
                    event_data['type'] = 'milestone'
                    event_data['icon'] = '🏆'
                
                # Debug logging
                import logging
                logger = logging.getLogger(__name__)
                logger.info(f"[map_ticker] 🎉 Showing weltmeister popup for {trigger_cyclist['user_id']} with {current_session_km} km (type: {event_data['type']}), parent_group: {parent_group_name}")
                logger.info(f"[map_ticker] 📋 Remaining cyclists in queue: {len(popup_queue)} (will be shown in next updates)")
            else:
                # Cyclist not found in ticker_data (maybe inactive now) - remove from queue
                popup_queue.pop(0)
                request.session[popup_queue_key] = popup_queue
                request.session.modified = True
    
    # Get popup settings
    popup_settings = MapPopupSettings.get_settings()
    
    return render(request, 'map/partials/live_ticker.html', {
        'active_cyclists': ticker_data,
        'event': event_data,
        'target_group': target_group,
        'weltmeister_popup_duration': popup_settings.weltmeister_popup_duration_seconds * 1000,  # Convert to milliseconds
        'weltmeister_popup_opacity': float(popup_settings.weltmeister_popup_opacity),
    })


def _leaderboard_implementation(request: HttpRequest) -> HttpResponse:
    """
    DEPRECATED: This function has been moved to leaderboard.views.
    
    This function is kept here temporarily for backward compatibility.
    It now redirects to the leaderboard app implementation.
    
    Args:
        request: HTTP request object.
    
    Returns:
        HTTP response with leaderboard page.
    """
    # Import from leaderboard app
    from leaderboard.views import _leaderboard_implementation as leaderboard_impl
    return leaderboard_impl(request)
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
    
    # Daily record holder: Best performance since 00:00 today
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Calculate daily kilometers for each group
    # Use only HourlyMetric data (updated every 60 seconds by cronjob)
    
    # Get HourlyMetric entries for today
    daily_metrics = HourlyMetric.objects.filter(
        timestamp__gte=today_start,
        group_at_time__isnull=False
    ).values('group_at_time').annotate(
        daily_total=Sum('distance_km')
    )
    
    # Create a dictionary to store daily kilometers per group
    daily_km_by_group: Dict[int, float] = {}
    
    # Add HourlyMetric data
    for metric in daily_metrics:
        group_id = metric['group_at_time']
        if group_id:
            daily_km_by_group[group_id] = float(metric['daily_total'] or 0.0)
    
    # For parent groups that don't have direct members, calculate daily_km from their children
    # This ensures parent groups like "Testtour" have correct daily_km values
    for group_id in list(daily_km_by_group.keys()):
        try:
            group = Group.objects.get(id=group_id)
            # If this group has a parent and the parent is in all_groups, add to parent's daily_km
            if group.parent:
                parent_id = group.parent.id
                if parent_id not in daily_km_by_group:
                    daily_km_by_group[parent_id] = 0.0
                daily_km_by_group[parent_id] += daily_km_by_group[group_id]
        except Group.DoesNotExist:
            pass
    
    # Weekly record holder: Best performance from Monday to Sunday of current week
    # Calculate Monday of current week (Monday = 0, Sunday = 6)
    days_since_monday = now.weekday()  # 0 = Monday, 6 = Sunday
    week_start = (now - timedelta(days=days_since_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
    week_end = (week_start + timedelta(days=6)).replace(hour=23, minute=59, second=59, microsecond=999999)
    
    # Calculate weekly kilometers for each group
    # Use only HourlyMetric data (updated every 60 seconds by cronjob)
    
    # Get HourlyMetric entries for this week (Monday to Sunday)
    weekly_metrics = HourlyMetric.objects.filter(
        timestamp__gte=week_start,
        timestamp__lte=week_end,
        group_at_time__isnull=False
    ).values('group_at_time').annotate(
        weekly_total=Sum('distance_km')
    )
    
    # Create a dictionary to store weekly kilometers per group
    weekly_km_by_group: Dict[int, float] = {}
    
    # Add HourlyMetric data
    for metric in weekly_metrics:
        group_id = metric['group_at_time']
        if group_id:
            weekly_km_by_group[group_id] = float(metric['weekly_total'] or 0.0)
    
    # For parent groups that don't have direct members, calculate weekly_km from their children
    # This ensures parent groups like "Testtour" have correct weekly_km values
    for group_id in list(weekly_km_by_group.keys()):
        try:
            group = Group.objects.get(id=group_id)
            # If this group has a parent and the parent is in all_groups, add to parent's weekly_km
            if group.parent:
                parent_id = group.parent.id
                if parent_id not in weekly_km_by_group:
                    weekly_km_by_group[parent_id] = 0.0
                weekly_km_by_group[parent_id] += weekly_km_by_group[group_id]
        except Group.DoesNotExist:
            pass
    
    # Monthly record holder: Best performance from 1st to last day of current month
    # Calculate first day of current month
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    # Calculate last day of current month
    if now.month == 12:
        month_end = now.replace(year=now.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        month_end = now.replace(month=now.month + 1, day=1) - timedelta(days=1)
    month_end = month_end.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    # Calculate monthly kilometers for each group
    # Use only HourlyMetric data (updated every 60 seconds by cronjob)
    
    # Get HourlyMetric entries for this month
    monthly_metrics = HourlyMetric.objects.filter(
        timestamp__gte=month_start,
        timestamp__lte=month_end,
        group_at_time__isnull=False
    ).values('group_at_time').annotate(
        monthly_total=Sum('distance_km')
    )
    
    # Create a dictionary to store monthly kilometers per group
    monthly_km_by_group: Dict[int, float] = {}
    
    # Add HourlyMetric data
    for metric in monthly_metrics:
        group_id = metric['group_at_time']
        if group_id:
            monthly_km_by_group[group_id] = float(metric['monthly_total'] or 0.0)
    
    # For parent groups that don't have direct members, calculate monthly_km from their children
    for group_id in list(monthly_km_by_group.keys()):
        try:
            group = Group.objects.get(id=group_id)
            if group.parent:
                parent_id = group.parent.id
                if parent_id not in monthly_km_by_group:
                    monthly_km_by_group[parent_id] = 0.0
                monthly_km_by_group[parent_id] += monthly_km_by_group[group_id]
        except Group.DoesNotExist:
            pass
    
    # Yearly record holder: Best performance from January 1st to December 31st of current year
    # Calculate first day of current year
    year_start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    # Calculate last day of current year
    year_end = now.replace(month=12, day=31, hour=23, minute=59, second=59, microsecond=999999)
    
    # Calculate yearly kilometers for each group
    # Use only HourlyMetric data (updated every 60 seconds by cronjob)
    
    # Get HourlyMetric entries for this year
    yearly_metrics = HourlyMetric.objects.filter(
        timestamp__gte=year_start,
        timestamp__lte=year_end,
        group_at_time__isnull=False
    ).values('group_at_time').annotate(
        yearly_total=Sum('distance_km')
    )
    
    # Create a dictionary to store yearly kilometers per group
    yearly_km_by_group: Dict[int, float] = {}
    
    # Add HourlyMetric data
    for metric in yearly_metrics:
        group_id = metric['group_at_time']
        if group_id:
            yearly_km_by_group[group_id] = float(metric['yearly_total'] or 0.0)
    
    # For parent groups that don't have direct members, calculate yearly_km from their children
    for group_id in list(yearly_km_by_group.keys()):
        try:
            group = Group.objects.get(id=group_id)
            if group.parent:
                parent_id = group.parent.id
                if parent_id not in yearly_km_by_group:
                    yearly_km_by_group[parent_id] = 0.0
                yearly_km_by_group[parent_id] += yearly_km_by_group[group_id]
        except Group.DoesNotExist:
            pass
    
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
        
        # Get daily kilometers for this group
        daily_km = daily_km_by_group.get(group.id, 0.0)
        # For parent groups without direct members, calculate from children if not already set
        if daily_km == 0.0 and group.children.exists() and not group.members.exists():
            # Sum up daily_km from all child groups
            child_daily_km = sum(
                daily_km_by_group.get(child.id, 0.0)
                for child in group.children.all()
            )
            daily_km = child_daily_km
        
        # Ensure daily_km is always a float, never None
        if daily_km is None:
            daily_km = 0.0
        daily_km = float(daily_km)
        
        # Get weekly kilometers for this group
        weekly_km = weekly_km_by_group.get(group.id, 0.0)
        # For parent groups without direct members, calculate from children if not already set
        if weekly_km == 0.0 and group.children.exists() and not group.members.exists():
            # Sum up weekly_km from all child groups
            child_weekly_km = sum(
                weekly_km_by_group.get(child.id, 0.0)
                for child in group.children.all()
            )
            weekly_km = child_weekly_km
        
        # Ensure weekly_km is always a float, never None
        if weekly_km is None:
            weekly_km = 0.0
        weekly_km = float(weekly_km)
        
        # Get monthly kilometers for this group
        monthly_km = monthly_km_by_group.get(group.id, 0.0)
        # For parent groups without direct members, calculate from children if not already set
        if monthly_km == 0.0 and group.children.exists() and not group.members.exists():
            # Sum up monthly_km from all child groups
            child_monthly_km = sum(
                monthly_km_by_group.get(child.id, 0.0)
                for child in group.children.all()
            )
            monthly_km = child_monthly_km
        
        # Ensure monthly_km is always a float, never None
        if monthly_km is None:
            monthly_km = 0.0
        monthly_km = float(monthly_km)
        
        # Get yearly kilometers for this group
        yearly_km = yearly_km_by_group.get(group.id, 0.0)
        # For parent groups without direct members, calculate from children if not already set
        if yearly_km == 0.0 and group.children.exists() and not group.members.exists():
            # Sum up yearly_km from all child groups
            child_yearly_km = sum(
                yearly_km_by_group.get(child.id, 0.0)
                for child in group.children.all()
            )
            yearly_km = child_yearly_km
        
        # Ensure yearly_km is always a float, never None
        if yearly_km is None:
            yearly_km = 0.0
        yearly_km = float(yearly_km)
        
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
            'distance_total': float(group.distance_total),
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
                # Only include visible groups with distance_total > 0
                # IMPORTANT: Use select_related to avoid N+1 queries
                subgroups = Group.objects.filter(
                    id__in=descendant_ids,
                    is_visible=True,
                    distance_total__gt=0,
                    children__isnull=True  # CRITICAL: Only leaf-groups (no children)
                ).select_related('parent').order_by('-distance_total')
                
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
                    
                    top_parent_groups.append({
                        'name': subgroup.get_kiosk_label(),  # Use short_name if available, otherwise full name
                        'total_km': float(subgroup.distance_total),
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
            
            # Check if parent is visible and has distance_total > 0
            parent_visible_with_km = parent.is_visible and float(parent.distance_total) > 0
            
            # Check if parent has visible children with distance_total > 0
            # Also ensure all children's parent groups are visible
            visible_children = []
            for child in parent.children.filter(is_visible=True, distance_total__gt=0):
                # Only include child if all its parent groups are visible
                if are_all_parents_visible(child):
                    visible_children.append(child)
            
            children_total = sum(
                float(child.distance_total) for child in visible_children
            )
            has_visible_children = children_total > 0
            
            # Only include parent if it meets one of the conditions
            if parent_visible_with_km or has_visible_children:
                # Use the sum of visible children if available, otherwise use parent's distance_total
                if has_visible_children:
                    total_km = children_total
                else:
                    total_km = float(parent.distance_total)
                
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
    # This should match the Admin Report's total_distance calculation
    # If a filter is active, only count the filtered parent group's distance_total
    # (which already contains the aggregated sum of all descendants)
    if current_filter:
        # Filtered view: use the parent group's distance_total
        # This is the aggregated sum of all its descendants
        try:
            parent_group = Group.objects.get(name=current_filter, is_visible=True)
            total_km = float(parent_group.distance_total)
        except Group.DoesNotExist:
            # Fallback: use groups_data sum
            total_km = sum(g['distance_total'] for g in groups_data)
    else:
        # Unfiltered view: count only top-level groups (no parent) to avoid double-counting
        # Top-level groups already contain the aggregated sum of all their descendants
        all_visible_groups = Group.objects.filter(is_visible=True, parent__isnull=True)
        total_km = sum(float(g.distance_total) for g in all_visible_groups)
    
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