# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    debug_eventboard_selection.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from api.models import Event, GroupEventStatus, Group, Cyclist
from eventboard.utils import get_all_subgroup_ids


class Command(BaseCommand):
    help = 'Debug eventboard selection API logic - test active cyclists counting'

    def add_arguments(self, parser):
        parser.add_argument('event_id', type=int, help='Event ID to test')
        parser.add_argument('--group-filter-id', type=int, help='Group filter ID (TOP-group)')

    def handle(self, *args, **options):
        event_id = options['event_id']
        group_filter_id = options.get('group_filter_id')
        
        now = timezone.now()
        active_cutoff = now - timedelta(seconds=60)
        
        self.stdout.write(f"=== Eventboard Selection API Debug ===")
        self.stdout.write(f"Current time: {now}")
        self.stdout.write(f"Active cutoff: {active_cutoff} (60 seconds ago)")
        self.stdout.write(f"Event ID: {event_id}")
        self.stdout.write(f"Group Filter ID: {group_filter_id}")
        self.stdout.write("")
        
        # Lade Event
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
        
        # Hole alle Gruppen, die am Event teilnehmen (mit Untergruppen)
        event_group_statuses = GroupEventStatus.objects.filter(
            event_id=event_id
        ).select_related('group')
        
        self.stdout.write(f"=== Event Groups (direct) ===")
        direct_groups = []
        for status in event_group_statuses:
            group = status.group
            direct_groups.append(group.id)
            self.stdout.write(f"  - Group {group.id} ({group.name}): parent={group.parent_id}, is_TOP={group.parent is None}")
        
        # Erweitere um Untergruppen von TOP-Gruppen
        all_group_ids = set(direct_groups)
        for status in event_group_statuses:
            group = status.group
            if group.parent is None:  # TOP-Gruppe
                subgroups = get_all_subgroup_ids(group)
                subgroups.append(group.id)
                self.stdout.write(f"  - TOP-Group {group.id}: adding all subgroups {subgroups}")
                all_group_ids.update(subgroups)
            else:
                # Prüfe, ob TOP-Gruppe auch im Event ist
                top_group = group
                while top_group.parent:
                    top_group = top_group.parent
                
                top_group_in_event = GroupEventStatus.objects.filter(
                    event_id=event_id,
                    group=top_group
                ).exists()
                
                if top_group_in_event:
                    subgroups = get_all_subgroup_ids(top_group)
                    subgroups.append(top_group.id)
                    self.stdout.write(f"  - Group {group.id} is subgroup of TOP-Group {top_group.id} (in event): adding all subgroups {subgroups}")
                    all_group_ids.update(subgroups)
        
        all_group_ids = list(all_group_ids)
        self.stdout.write(f"Final event groups (with subgroups): {sorted(all_group_ids)}")
        self.stdout.write("")
        
        # Hole alle aktiven Radler, die zu Event-Gruppen gehören
        if not all_group_ids:
            self.stdout.write(self.style.WARNING("No groups found for this event!"))
            return
        
        self.stdout.write(f"=== Querying active cyclists ===")
        self.stdout.write(f"Groups to check: {all_group_ids}")
        self.stdout.write(f"Active cutoff: {active_cutoff}")
        self.stdout.write("")
        
        # Basis-Query
        base_cyclists = Cyclist.objects.filter(
            is_visible=True,
            last_active__isnull=False,
            last_active__gte=active_cutoff,
            groups__id__in=all_group_ids
        ).prefetch_related('groups').distinct()
        
        base_count = base_cyclists.count()
        self.stdout.write(f"Base query result: {base_count} cyclists")
        self.stdout.write("")
        
        if base_count == 0:
            # Debug: Prüfe, warum keine Radler gefunden wurden
            all_visible = Cyclist.objects.filter(is_visible=True).count()
            with_last_active = Cyclist.objects.filter(is_visible=True, last_active__isnull=False).count()
            recent_active = Cyclist.objects.filter(
                is_visible=True,
                last_active__isnull=False,
                last_active__gte=active_cutoff
            ).count()
            in_groups = Cyclist.objects.filter(
                is_visible=True,
                last_active__isnull=False,
                last_active__gte=active_cutoff,
                groups__id__in=all_group_ids
            ).count()
            
            self.stdout.write(self.style.WARNING("NO ACTIVE CYCLISTS FOUND!"))
            self.stdout.write(f"  - Total visible cyclists: {all_visible}")
            self.stdout.write(f"  - With last_active: {with_last_active}")
            self.stdout.write(f"  - Recent active (last 60s): {recent_active}")
            self.stdout.write(f"  - In event groups: {in_groups}")
            return
        
        # Zeige Details aller gefundenen Radler
        self.stdout.write(f"=== Active Cyclists Details ===")
        active_cyclists_by_event = {}
        
        for cyclist in base_cyclists:
            cyclist_group_ids = set(cyclist.groups.values_list('id', flat=True))
            event_group_ids = set(all_group_ids)
            
            # Prüfe, ob Radler zu mindestens einer Gruppe des Events gehört
            common_groups = cyclist_group_ids & event_group_ids
            
            self.stdout.write(f"Cyclist {cyclist.id} ({cyclist.user_id}):")
            self.stdout.write(f"  - last_active: {cyclist.last_active}")
            self.stdout.write(f"  - cyclist groups: {list(cyclist_group_ids)}")
            self.stdout.write(f"  - event groups: {list(event_group_ids)}")
            self.stdout.write(f"  - common groups: {list(common_groups)}")
            self.stdout.write(f"  - belongs to event: {len(common_groups) > 0}")
            
            if len(common_groups) > 0:
                if event_id not in active_cyclists_by_event:
                    active_cyclists_by_event[event_id] = {}
                active_cyclists_by_event[event_id][cyclist.id] = {
                    'id': cyclist.id,
                    'user_id': cyclist.user_id,
                }
            self.stdout.write("")
        
        # Zeige Ergebnis
        active_cyclists_list = active_cyclists_by_event.get(event_id, {})
        active_cyclists_count = len(active_cyclists_list)
        
        self.stdout.write(f"=== Result ===")
        self.stdout.write(f"Active cyclists count: {active_cyclists_count}")
        self.stdout.write(f"Active cyclists list: {list(active_cyclists_list.values())}")
        self.stdout.write(f"Event is_currently_active: {event.is_currently_active()}")
        self.stdout.write(f"has_active_cyclists: {event.is_currently_active() and active_cyclists_count > 0}")
