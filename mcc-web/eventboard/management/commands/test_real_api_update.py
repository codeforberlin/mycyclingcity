# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    test_real_api_update.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

from django.core.management.base import BaseCommand
from api.models import Cyclist, Group, Event, GroupEventStatus
from api.models import update_group_hierarchy_progress
from decimal import Decimal
import logging

# Setze Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('api.models')
logger.setLevel(logging.DEBUG)


class Command(BaseCommand):
    help = 'Test if update_group_hierarchy_progress is called correctly for cyclist groups'

    def add_arguments(self, parser):
        parser.add_argument('cyclist_id', type=int, help='Cyclist ID to test')
        parser.add_argument('event_id', type=int, help='Event ID to test')
        parser.add_argument('--delta', type=float, default=0.1, help='Kilometer delta to add')

    def handle(self, *args, **options):
        cyclist_id = options['cyclist_id']
        event_id = options['event_id']
        delta_km = Decimal(str(options['delta']))
        
        self.stdout.write(f"=== Testing Real API Update Logic ===")
        self.stdout.write(f"Cyclist ID: {cyclist_id}")
        self.stdout.write(f"Event ID: {event_id}")
        self.stdout.write(f"Delta KM: {delta_km}")
        self.stdout.write("")
        
        try:
            c = Cyclist.objects.get(id=cyclist_id)
            self.stdout.write(f"Cyclist: {c.user_id} (ID: {c.id})")
            self.stdout.write(f"Groups: {[g.id for g in c.groups.all()]}")
        except Cyclist.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Cyclist {cyclist_id} not found!"))
            return
        
        try:
            e = Event.objects.get(id=event_id)
            self.stdout.write(f"Event: {e.name} (ID: {e.id})")
            self.stdout.write(f"  - is_active: {e.is_active}")
            self.stdout.write(f"  - is_currently_active(): {e.is_currently_active()}")
        except Event.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Event {event_id} not found!"))
            return
        
        # Prüfe Event-Statuses vor Update
        self.stdout.write(f"\n=== Event Statuses BEFORE Update ===")
        event_statuses_before = {}
        for g in c.groups.all():
            ges = GroupEventStatus.objects.filter(group=g, event=e).first()
            if ges:
                event_statuses_before[g.id] = ges.current_distance_km
                self.stdout.write(f"Group {g.id} ({g.name}): {ges.current_distance_km} km")
            else:
                self.stdout.write(f"Group {g.id} ({g.name}): NO EVENT STATUS")
        
        # Simuliere die API-Logik: update_group_hierarchy_progress für alle Gruppen
        self.stdout.write(f"\n=== Simulating API Update Logic ===")
        self.stdout.write(f"Calling update_group_hierarchy_progress for each group...")
        
        for group in c.groups.all():
            self.stdout.write(f"\nProcessing Group {group.id} ({group.name}):")
            self.stdout.write(f"  - is_leaf_group(): {group.is_leaf_group()}")
            
            # Prüfe, ob Event-Status existiert
            ges = GroupEventStatus.objects.filter(group=group, event=e).first()
            if ges:
                self.stdout.write(f"  - Event Status exists: {ges.current_distance_km} km")
            else:
                self.stdout.write(f"  - Event Status: NOT FOUND - will skip event update")
            
            # Führe Update durch (wie in _process_update_with_retry)
            old_group_distance = group.distance_total
            update_group_hierarchy_progress(group, delta_km)
            group.refresh_from_db()
            self.stdout.write(f"  - Group distance_total: {old_group_distance} → {group.distance_total}")
        
        # Prüfe Event-Statuses nach Update
        self.stdout.write(f"\n=== Event Statuses AFTER Update ===")
        for g in c.groups.all():
            ges = GroupEventStatus.objects.filter(group=g, event=e).first()
            if ges:
                before = event_statuses_before.get(g.id, Decimal('0'))
                after = ges.current_distance_km
                diff = after - before
                self.stdout.write(f"Group {g.id} ({g.name}): {after} km (was {before} km, diff: {diff} km)")
                if diff == 0:
                    self.stdout.write(self.style.WARNING(f"  ⚠️ NO CHANGE! Kilometers were NOT added!"))
                else:
                    self.stdout.write(self.style.SUCCESS(f"  ✅ SUCCESS! Kilometers were added!"))
            else:
                self.stdout.write(f"Group {g.id} ({g.name}): NO EVENT STATUS")
