# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    views.py
# @author  Roland Rutz

#
"""
Project: MyCyclingCity
Generation: AI-based

Views for ranking app - handles ranking tables and statistical lists.
"""

from urllib.parse import unquote
from typing import Any, Optional
from django.shortcuts import render
from django.http import HttpRequest, HttpResponse
from api.models import Group
from api.helpers import build_group_hierarchy, build_events_data


def ranking_page(request: HttpRequest, kiosk: bool = False) -> HttpResponse:
    """
    Main view for ranking tables and statistical lists.
    
    Args:
        request: HTTP request object.
        kiosk: Whether in kiosk mode.
    
    Returns:
        HTTP response with ranking table data.
    """
    target_group_id = request.GET.get('group_id')
    target_group_name = request.GET.get('group_name')
    show_cyclists = request.GET.get('show_cyclists', 'false' if kiosk else 'true').lower() == 'true'
    
    # Store original target_group_id for final check
    original_target_group_id = target_group_id
    
    try:
        # Default: 60s for kiosk, 20s for browser
        default_int = 60 if kiosk else 20
        refresh_interval = int(request.GET.get('interval', default_int))
    except (ValueError, TypeError):
        refresh_interval = 20
    
    # Group filtering - supports both ID and name, and multiple IDs (comma-separated)
    group_filter = {'is_visible': True}
    target_groups = []
    selected_group_ids = []
    show_all_groups = True  # Default: show all groups (only if no group_id parameter at all)
    is_none_requested = False  # Track if group_id='none' was explicitly requested
    
    if target_group_id and target_group_id.strip() and target_group_id != 'None':
        # URL decoding for group names with spaces
        target_group_id = unquote(target_group_id)
        # Check if explicitly set to 'none' to show no groups
        if target_group_id.strip().lower() == 'none':
            show_all_groups = False
            is_none_requested = True
            # Explicitly set to show no groups - don't process further
            # Ensure target_groups stays empty
            target_groups = []
            selected_group_ids = []
        else:
            # Support comma-separated group IDs
            group_id_list = [gid.strip() for gid in target_group_id.split(',') if gid.strip() and gid.strip().lower() != 'none']
            
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
            show_all_groups = False  # Groups selected, don't show all
    elif target_group_name and target_group_name.strip():
        # URL decoding for group names with spaces
        target_group_name = unquote(target_group_name)
        # Search for group name
        try:
            group = Group.objects.get(name=target_group_name, **group_filter)
            target_groups.append(group)
            selected_group_ids.append(str(group.id))
            show_all_groups = False  # Group selected, don't show all
        except Group.DoesNotExist:
            pass
    
    # Initialize target_group to None (will be set below if needed)
    target_group = None
    
    # Initialize hierarchy variable
    hierarchy = []
    
    # If group_id='none' was explicitly requested, return empty hierarchy immediately
    if is_none_requested:
        # Don't process further - return empty hierarchy
        hierarchy = []
    # If show_all_groups is False and no groups selected, return empty hierarchy
    elif not show_all_groups and len(target_groups) == 0:
        # Don't process further - return empty hierarchy
        hierarchy = []
    elif len(target_groups) > 0:
        # Groups are selected - load and filter
        # If multiple groups selected, load all top groups (target_group = None) and filter
        # If single group selected, load only that group (target_group = target_groups[0])
        target_group = None if len(target_groups) != 1 else target_groups[0]
        
        # Build hierarchy using shared helper
        hierarchy = build_group_hierarchy(
            target_group=target_group,
            kiosk=kiosk,
            show_cyclists=show_cyclists
        )
        
        # Filter hierarchy to only show selected groups and their descendants
        if len(target_groups) > 1:
            # Multiple groups selected - filter
            from mgmt.analytics import _get_descendant_group_ids
            all_group_ids = set()
            for tg in target_groups:
                all_group_ids.add(tg.id)
                all_group_ids.update(_get_descendant_group_ids(tg))  # Pass Group object, not ID
            
            # Filter hierarchy to only include selected groups and their descendants
            filtered_hierarchy = []
            for group_data in hierarchy:
                if group_data.get('id') in all_group_ids:
                    # Filter subgroups within this group
                    if 'subgroups' in group_data:
                        group_data['subgroups'] = [
                            sg for sg in group_data['subgroups']
                            if sg.get('id') in all_group_ids
                        ]
                    filtered_hierarchy.append(group_data)
            hierarchy = filtered_hierarchy
        # else: single group selected - hierarchy already filtered by build_group_hierarchy
    elif show_all_groups:
        # No groups selected and show_all_groups is True - show all groups
        # Only execute this if is_none_requested is False
        target_group = None
        hierarchy = build_group_hierarchy(
            target_group=target_group,
            kiosk=kiosk,
            show_cyclists=show_cyclists
        )
    
    # Build events data - but don't show events if group_id='none' is requested
    if is_none_requested:
        events_data = []  # Don't show events when no groups are selected
    else:
        events_data = build_events_data(kiosk=kiosk)
    
    # Final safety check: if group_id='none' was explicitly requested, hierarchy must be empty
    # This ensures hierarchy stays empty even if something went wrong above
    if is_none_requested:
        hierarchy = []
    
    # Get only top-level master groups (parent groups) for the group selector dropdown
    # This limits the dropdown to the highest-level parent groups only (TOP-Gruppen)
    all_groups = Group.objects.filter(is_visible=True, parent__isnull=True).order_by('name')
    
    # Determine group_id for context - preserve 'none' if explicitly requested
    context_group_id = None
    if is_none_requested:
        context_group_id = 'none'  # Preserve 'none' for HTMX requests
    elif selected_group_ids:
        context_group_id = ','.join(selected_group_ids)  # Comma-separated IDs
    
    context = {
        'hierarchy': hierarchy,
        'is_kiosk': kiosk,
        'group_id': context_group_id,
        'group_name': target_groups[0].name if target_groups else None,  # First group name for compatibility
        'target_group': target_group,  # First group for backward compatibility
        'target_groups': target_groups,  # List of selected groups
        'selected_group_ids': selected_group_ids,  # List of selected group IDs as strings
        'all_groups': all_groups,  # All TOP-Gruppen for filter dropdown
        'refresh_interval': refresh_interval,
        'show_cyclists': show_cyclists,
        'events_data': events_data,
    }
    
    # If HTMX request for table refresh, return only table fragment
    if request.headers.get('HX-Request') and request.GET.get('refresh_table'):
        return render(request, 'ranking/table_data.html', context)
    
    return render(request, 'ranking/ranking_page.html', context)
