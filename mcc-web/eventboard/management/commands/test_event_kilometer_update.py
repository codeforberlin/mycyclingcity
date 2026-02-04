# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    test_event_kilometer_update.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

from django.core.management.base import BaseCommand
from api.models import Group
from eventboard.models import Event, GroupEventStatus
from api.models import update_group_hierarchy_progress
from decimal import Decimal


class Command(BaseCommand):
    help = 'Test if event kilometer update logic works correctly'

    def add_arguments(self, parser):
        parser.add_argument('group_id', type=int, help='Group ID to test')
        parser.add_argument('event_id', type=int, help='Event ID to test')
        parser.add_argument('--delta', type=float, default=1.0, help='Kilometer delta to add')

    def handle(self, *args, **options):
        group_id = options['group_id']
        event_id = options['event_id']
        delta_km = Decimal(str(options['delta']))
        
        self.stdout.write(f"=== Test Event Kilometer Update ===")
        self.stdout.write(f"Group ID: {group_id}")
        self.stdout.write(f"Event ID: {event_id}")
        self.stdout.write(f"Delta KM: {delta_km}")
        self.stdout.write("")
        
        try:
            group = Group.objects.get(id=group_id)
            self.stdout.write(f"Group: {group.name}")
        except Group.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Group {group_id} not found!"))
            return
        
        try:
            event = Event.objects.get(id=event_id)
            self.stdout.write(f"Event: {event.name}")
            self.stdout.write(f"  - is_active: {event.is_active}")
            self.stdout.write(f"  - is_currently_active(): {event.is_currently_active()}")
        except Event.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Event {event_id} not found!"))
            return
        
        # Prüfe Event-Status vor Update
        try:
            event_status_before = GroupEventStatus.objects.get(group=group, event=event)
            self.stdout.write(f"")
            self.stdout.write(f"BEFORE Update:")
            self.stdout.write(f"  - current_distance_km: {event_status_before.current_distance_km}")
        except GroupEventStatus.DoesNotExist:
            self.stdout.write(self.style.WARNING(f"Group {group_id} is not in event {event_id}!"))
            return
        
        # Führe Update durch
        self.stdout.write(f"")
        self.stdout.write(f"Calling update_group_hierarchy_progress(group={group_id}, delta_km={delta_km})...")
        update_group_hierarchy_progress(group, delta_km)
        
        # Prüfe Event-Status nach Update
        event_status_after = GroupEventStatus.objects.get(group=group, event=event)
        self.stdout.write(f"")
        self.stdout.write(f"AFTER Update:")
        self.stdout.write(f"  - current_distance_km: {event_status_after.current_distance_km}")
        self.stdout.write(f"  - Difference: {event_status_after.current_distance_km - event_status_before.current_distance_km}")
        
        if event_status_after.current_distance_km == event_status_before.current_distance_km:
            self.stdout.write(self.style.ERROR("❌ NO CHANGE! Kilometers were NOT added!"))
        else:
            self.stdout.write(self.style.SUCCESS("✅ SUCCESS! Kilometers were added!"))
