"""
Project: MyCyclingCity
Generation: AI-based

Shared helper functions for building group hierarchies and data structures.
Used by map, ranking, and leaderboard apps.
"""

from typing import List, Dict, Any, Optional
from django.db.models import QuerySet
from api.models import Group, Cyclist, CyclistDeviceCurrentMileage, Event, GroupEventStatus
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
    
    hierarchy = []
    for p_group in parent_groups:
        p_filter = {'is_visible': True}
        if kiosk:
            p_filter['distance_total__gt'] = 0
        
        direct_members = []
        if show_cyclists:
            direct_qs = p_group.members.filter(**p_filter).select_related(
                'cyclistdevicecurrentmileage'
            ).order_by('-distance_total')
            direct_members = []
            for m in direct_qs:
                session_km = 0
                try:
                    if hasattr(m, 'cyclistdevicecurrentmileage') and m.cyclistdevicecurrentmileage:
                        session_km = float(m.cyclistdevicecurrentmileage.cumulative_mileage)
                except (AttributeError, ValueError, TypeError):
                    pass
                direct_members.append({
                    'name': m.user_id,
                    'km': round(m.distance_total, 3),
                    'session_km': round(session_km, 3)
                })
        
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
                ).order_by('-distance_total')
                sub_member_data = []
                for m in m_qs:
                    session_km = 0
                    try:
                        if hasattr(m, 'cyclistdevicecurrentmileage') and m.cyclistdevicecurrentmileage:
                            session_km = float(m.cyclistdevicecurrentmileage.cumulative_mileage)
                    except (AttributeError, ValueError, TypeError):
                        pass
                    sub_member_data.append({
                        'name': m.user_id,
                        'km': round(m.distance_total, 3),
                        'session_km': round(session_km, 3)
                    })
            # In kiosk mode, only add subgroup if it has distance_total > 0 or has members with distance_total > 0
            if not kiosk or (sub.distance_total > 0 or len(sub_member_data) > 0):
                subgroups_data.append({
                    'id': sub.id,  # Add subgroup ID for filtering
                    'name': sub.name,
                    'km': round(sub.distance_total, 3),
                    'members': sub_member_data
                })
        
        # Limit subgroups to top 10 by distance_total (sorted descending)
        subgroups_data = sorted(subgroups_data, key=lambda x: x['km'], reverse=True)[:10]
        
        if not kiosk or (p_group.distance_total > 0 or subgroups_data or direct_members):
            hierarchy.append({
                'id': p_group.id,  # Add group ID for filtering
                'name': p_group.name,
                'km': round(p_group.distance_total, 3),
                'direct_members': direct_members,
                'subgroups': subgroups_data
            })
    
    # Sort hierarchy by name to match the group menu sorting
    hierarchy = sorted(hierarchy, key=lambda x: x['name'])
    
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
    from api.models import Event
    
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


