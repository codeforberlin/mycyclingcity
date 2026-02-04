# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    debug_event_kilometers.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

from django.core.management.base import BaseCommand
from api.models import Group, Cyclist
from eventboard.models import Event, GroupEventStatus


class Command(BaseCommand):
    help = 'Debug event kilometers - check why kilometers are not being added'

    def add_arguments(self, parser):
        parser.add_argument('event_id', type=int, help='Event ID to test')

    def handle(self, *args, **options):
        event_id = options['event_id']
        
        self.stdout.write(f"=== Event Kilometers Debug ===")
        self.stdout.write(f"Event ID: {event_id}")
        self.stdout.write("")
        
        try:
            event = Event.objects.get(id=event_id)
            self.stdout.write(f"Event: {event.name}")
            self.stdout.write(f"  - is_active: {event.is_active}")
            self.stdout.write(f"  - is_currently_active(): {event.is_currently_active()}")
            self.stdout.write(f"  - start_time: {event.start_time}")
            self.stdout.write(f"  - end_time: {event.end_time}")
            self.stdout.write("")
        except Event.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Event {event_id} not found!"))
            return
        
        # Zeige alle Gruppen, die am Event teilnehmen
        self.stdout.write(f"=== Groups in Event ===")
        event_statuses = GroupEventStatus.objects.filter(event=event).select_related('group')
        self.stdout.write(f"Total groups: {event_statuses.count()}")
        self.stdout.write("")
        
        for status in event_statuses:
            group = status.group
            self.stdout.write(f"Group {group.id} ({group.name}):")
            self.stdout.write(f"  - current_distance_km: {status.current_distance_km}")
            self.stdout.write(f"  - parent: {group.parent_id}")
            self.stdout.write(f"  - is TOP-group: {group.parent is None}")
            
            # Prüfe, ob Radler in dieser Gruppe sind
            cyclists_in_group = Cyclist.objects.filter(groups=group, is_visible=True).count()
            self.stdout.write(f"  - cyclists in group: {cyclists_in_group}")
            
            # Prüfe, ob diese Gruppe Event-Statuses hat
            group_event_statuses = group.event_statuses.filter(event=event)
            self.stdout.write(f"  - event_statuses for this group: {group_event_statuses.count()}")
            self.stdout.write("")
        
        # Prüfe, ob Radler in Untergruppen sind, die nicht direkt am Event teilnehmen
        self.stdout.write(f"=== Checking Subgroups ===")
        for status in event_statuses:
            group = status.group
            if group.parent is None:  # TOP-Gruppe
                # Hole alle Untergruppen
                from eventboard.utils import get_all_subgroup_ids
                all_subgroup_ids = get_all_subgroup_ids(group)
                all_subgroup_ids.append(group.id)
                
                # Prüfe, welche Untergruppen am Event teilnehmen
                subgroups_in_event = GroupEventStatus.objects.filter(
                    event=event,
                    group_id__in=all_subgroup_ids
                ).values_list('group_id', flat=True)
                
                subgroups_not_in_event = set(all_subgroup_ids) - set(subgroups_in_event)
                
                if subgroups_not_in_event:
                    self.stdout.write(f"TOP-Group {group.id} ({group.name}) has subgroups NOT in event:")
                    for subgroup_id in subgroups_not_in_event:
                        try:
                            subgroup = Group.objects.get(id=subgroup_id)
                            cyclists_count = Cyclist.objects.filter(groups=subgroup, is_visible=True).count()
                            self.stdout.write(f"  - Subgroup {subgroup_id} ({subgroup.name}): {cyclists_count} cyclists")
                        except Group.DoesNotExist:
                            pass
                    self.stdout.write("")
