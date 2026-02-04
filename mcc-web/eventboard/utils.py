# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    utils.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

from django.utils import timezone
from datetime import timedelta
from eventboard.models import GroupEventStatus
from api.models import Cyclist, Group, CyclistDeviceCurrentMileage


def get_all_subgroup_ids(top_group):
    """
    Rekursiv alle Untergruppen-IDs einer TOP-Gruppe holen.
    
    Args:
        top_group: Group-Objekt (TOP-Gruppe)
    
    Returns:
        Liste von Gruppen-IDs (inkl. TOP-Gruppe selbst)
    """
    def get_descendant_ids(ancestor_id, visited=None):
        """Rekursiv alle Nachfolger-IDs holen."""
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
                descendant_ids.update(get_descendant_ids(child_id, visited))
        
        return descendant_ids
    
    return list(get_descendant_ids(top_group.id))


def get_active_cyclists_for_eventboard(event_id=None, group_filter_id=None):
    """
    Hole aktive Radler für Eventboard mit Event- und Gruppen-Filterung.
    
    Args:
        event_id: Optional - Filtere nur Radler aus Gruppen, die am Event teilnehmen
        group_filter_id: Optional - Filtere nur Radler aus dieser TOP-Gruppe
    
    Returns:
        QuerySet von aktiven Cyclist-Objekten
    """
    now = timezone.now()
    active_cutoff = now - timedelta(seconds=60)
    
    # Basis-Query: Sichtbare Radler mit aktiver Session
    base_cyclists = Cyclist.objects.filter(
        is_visible=True,
        last_active__isnull=False,
        last_active__gte=active_cutoff
    ).select_related('cyclistdevicecurrentmileage').prefetch_related('groups')
    
    # Event-Filterung
    if event_id:
        # Hole alle Gruppen, die am Event teilnehmen
        event_groups = GroupEventStatus.objects.filter(
            event_id=event_id
        ).values_list('group_id', flat=True)
        
        # Filtere Radler, die zu diesen Gruppen gehören
        base_cyclists = base_cyclists.filter(groups__id__in=event_groups)
    
    # TOP-Gruppen-Filterung
    if group_filter_id:
        try:
            top_group = Group.objects.get(id=group_filter_id, parent__isnull=True)
            # Hole alle Untergruppen rekursiv
            all_group_ids = get_all_subgroup_ids(top_group)
            # WICHTIG: Füge die TOP-Gruppe selbst hinzu
            all_group_ids.append(group_filter_id)
            
            # Filtere Radler, die zu diesen Gruppen gehören
            base_cyclists = base_cyclists.filter(groups__id__in=all_group_ids)
        except Group.DoesNotExist:
            pass
    
    return base_cyclists.distinct()
