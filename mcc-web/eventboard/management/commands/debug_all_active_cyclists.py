# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    debug_all_active_cyclists.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from api.models import Cyclist
from eventboard.models import Event, GroupEventStatus


class Command(BaseCommand):
    help = 'Debug all active cyclists - find why some are not counted'

    def add_arguments(self, parser):
        parser.add_argument('event_id', type=int, help='Event ID to test')

    def handle(self, *args, **options):
        event_id = options['event_id']
        
        now = timezone.now()
        active_cutoff = now - timedelta(seconds=60)
        
        self.stdout.write(f"=== All Active Cyclists Debug ===")
        self.stdout.write(f"Current time: {now}")
        self.stdout.write(f"Active cutoff: {active_cutoff} (60 seconds ago)")
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
        event_groups = GroupEventStatus.objects.filter(
            event_id=event_id
        ).values_list('group_id', flat=True)
        
        self.stdout.write(f"Event groups: {list(event_groups)}")
        self.stdout.write("")
        
        # Zeige ALLE aktiven Radler (ohne Gruppen-Filter)
        self.stdout.write(f"=== ALL Active Cyclists (no group filter) ===")
        all_active = Cyclist.objects.filter(
            is_visible=True,
            last_active__isnull=False,
            last_active__gte=active_cutoff
        ).prefetch_related('groups')
        
        self.stdout.write(f"Total active cyclists: {all_active.count()}")
        self.stdout.write("")
        
        for cyclist in all_active:
            cyclist_groups = list(cyclist.groups.values_list('id', flat=True))
            belongs_to_event = bool(set(cyclist_groups) & set(event_groups))
            
            self.stdout.write(f"Cyclist {cyclist.id} ({cyclist.user_id}):")
            self.stdout.write(f"  - last_active: {cyclist.last_active}")
            self.stdout.write(f"  - groups: {cyclist_groups}")
            self.stdout.write(f"  - belongs to event groups: {belongs_to_event}")
            if belongs_to_event:
                common = set(cyclist_groups) & set(event_groups)
                self.stdout.write(f"  - common groups: {list(common)}")
            self.stdout.write("")
        
        # Zeige Radler, die zu Event-Gruppen gehören
        self.stdout.write(f"=== Cyclists in Event Groups (with filter) ===")
        in_event_groups = Cyclist.objects.filter(
            is_visible=True,
            last_active__isnull=False,
            last_active__gte=active_cutoff,
            groups__id__in=event_groups
        ).prefetch_related('groups').distinct()
        
        self.stdout.write(f"Count: {in_event_groups.count()}")
        for cyclist in in_event_groups:
            cyclist_groups = list(cyclist.groups.values_list('id', flat=True))
            self.stdout.write(f"  - {cyclist.id} ({cyclist.user_id}): groups={cyclist_groups}")
