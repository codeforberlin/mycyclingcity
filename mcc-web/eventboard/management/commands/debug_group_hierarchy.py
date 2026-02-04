# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    debug_group_hierarchy.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

from django.core.management.base import BaseCommand
from api.models import Event, GroupEventStatus, Group, Cyclist
from eventboard.utils import get_all_subgroup_ids


class Command(BaseCommand):
    help = 'Debug group hierarchy for event - check if subgroups should be included'

    def add_arguments(self, parser):
        parser.add_argument('event_id', type=int, help='Event ID to test')

    def handle(self, *args, **options):
        event_id = options['event_id']
        
        self.stdout.write(f"=== Group Hierarchy Debug ===")
        self.stdout.write(f"Event ID: {event_id}")
        self.stdout.write("")
        
        # Lade Event
        try:
            event = Event.objects.get(id=event_id)
            self.stdout.write(f"Event: {event.name}")
        except Event.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Event {event_id} not found!"))
            return
        
        # Hole alle Gruppen, die am Event teilnehmen
        event_group_statuses = GroupEventStatus.objects.filter(
            event_id=event_id
        ).select_related('group')
        
        self.stdout.write(f"=== Event Groups (direct) ===")
        direct_groups = []
        for status in event_group_statuses:
            group = status.group
            direct_groups.append(group.id)
            self.stdout.write(f"Group {group.id} ({group.name}):")
            self.stdout.write(f"  - parent: {group.parent_id}")
            self.stdout.write(f"  - is TOP-group: {group.parent is None}")
            self.stdout.write("")
        
        # Prüfe, ob es Untergruppen gibt, die auch berücksichtigt werden sollten
        self.stdout.write(f"=== All Subgroups (including direct groups) ===")
        all_group_ids = set(direct_groups)
        
        for status in event_group_statuses:
            group = status.group
            if group.parent is None:  # TOP-Gruppe
                subgroups = get_all_subgroup_ids(group)
                self.stdout.write(f"TOP-Group {group.id} ({group.name}):")
                self.stdout.write(f"  - All subgroup IDs (including self): {subgroups}")
                all_group_ids.update(subgroups)
            else:
                # Prüfe, ob die Gruppe eine Untergruppe einer TOP-Gruppe ist
                top_group = group
                while top_group.parent:
                    top_group = top_group.parent
                
                if top_group.id in direct_groups:
                    subgroups = get_all_subgroup_ids(top_group)
                    self.stdout.write(f"Group {group.id} is subgroup of TOP-Group {top_group.id}:")
                    self.stdout.write(f"  - All subgroup IDs: {subgroups}")
                    all_group_ids.update(subgroups)
        
        self.stdout.write("")
        self.stdout.write(f"=== Final Group List (with all subgroups) ===")
        self.stdout.write(f"All group IDs: {sorted(all_group_ids)}")
        self.stdout.write("")
        
        # Prüfe aktive Radler mit erweiterten Gruppen
        from django.utils import timezone
        from datetime import timedelta
        now = timezone.now()
        active_cutoff = now - timedelta(seconds=60)
        
        active_cyclists = Cyclist.objects.filter(
            is_visible=True,
            last_active__isnull=False,
            last_active__gte=active_cutoff,
            groups__id__in=all_group_ids
        ).prefetch_related('groups').distinct()
        
        self.stdout.write(f"=== Active Cyclists (with all subgroups) ===")
        self.stdout.write(f"Count: {active_cyclists.count()}")
        for cyclist in active_cyclists:
            cyclist_groups = list(cyclist.groups.values_list('id', flat=True))
            self.stdout.write(f"  - {cyclist.id} ({cyclist.user_id}): groups={cyclist_groups}")
