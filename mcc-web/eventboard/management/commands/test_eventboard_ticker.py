# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    test_eventboard_ticker.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

"""
Management command to test eventboard_ticker query directly.
Usage: python manage.py test_eventboard_ticker [event_id] [group_filter_id]
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from api.models import Cyclist, Group, CyclistDeviceCurrentMileage
from eventboard.models import Event, GroupEventStatus


class Command(BaseCommand):
    help = 'Test eventboard_ticker query to debug why no cyclists are found'

    def add_arguments(self, parser):
        parser.add_argument('event_id', nargs='?', type=int, help='Event ID to filter by')
        parser.add_argument('group_filter_id', nargs='?', type=int, help='Group filter ID (TOP-group)')

    def handle(self, *args, **options):
        event_id = options.get('event_id')
        group_filter_id = options.get('group_filter_id')
        
        now = timezone.now()
        active_cutoff = now - timedelta(seconds=60)
        
        self.stdout.write(f"=== Eventboard Ticker Debug ===")
        self.stdout.write(f"Current time: {now}")
        self.stdout.write(f"Active cutoff: {active_cutoff} (60 seconds ago)")
        self.stdout.write(f"Event ID: {event_id}")
        self.stdout.write(f"Group Filter ID: {group_filter_id}")
        self.stdout.write("")
        
        # Basis-Query
        base_cyclists = Cyclist.objects.filter(
            is_visible=True,
            last_active__isnull=False,
            last_active__gte=active_cutoff
        ).select_related('cyclistdevicecurrentmileage').prefetch_related('groups')
        
        base_count = base_cyclists.count()
        self.stdout.write(f"1. Base query (visible, last_active >= {active_cutoff}): {base_count} cyclists")
        
        if base_count == 0:
            # Debug why no cyclists found
            all_visible = Cyclist.objects.filter(is_visible=True).count()
            with_last_active = Cyclist.objects.filter(is_visible=True, last_active__isnull=False).count()
            recent_active = Cyclist.objects.filter(
                is_visible=True,
                last_active__isnull=False,
                last_active__gte=active_cutoff
            ).count()
            self.stdout.write(f"   - Total visible cyclists: {all_visible}")
            self.stdout.write(f"   - With last_active: {with_last_active}")
            self.stdout.write(f"   - Recent active (>= {active_cutoff}): {recent_active}")
            
            # Show some examples
            if with_last_active > 0:
                self.stdout.write(f"   - Sample cyclists with last_active:")
                samples = Cyclist.objects.filter(
                    is_visible=True,
                    last_active__isnull=False
                ).order_by('-last_active')[:5]
                for c in samples:
                    self.stdout.write(f"     * {c.user_id}: last_active={c.last_active}, "
                                    f"age={(now - c.last_active).total_seconds():.0f}s ago")
        else:
            # Show first 3 cyclists
            self.stdout.write(f"   - First 3 cyclists:")
            for cyclist in base_cyclists[:3]:
                groups = list(cyclist.groups.values_list('id', flat=True))
                try:
                    session = cyclist.cyclistdevicecurrentmileage
                    session_km = float(session.cumulative_mileage) if session.cumulative_mileage else 0.0
                except CyclistDeviceCurrentMileage.DoesNotExist:
                    session_km = 0.0
                self.stdout.write(f"     * {cyclist.user_id}: last_active={cyclist.last_active}, "
                                f"groups={groups}, session_km={session_km}")
        
        # Event-Filterung
        if event_id:
            self.stdout.write("")
            try:
                event = Event.objects.get(id=event_id)
                self.stdout.write(f"2. Event {event_id} exists: {event.name}")
                
                event_groups = GroupEventStatus.objects.filter(event_id=event_id).values_list('group_id', flat=True)
                event_group_list = list(event_groups)
                self.stdout.write(f"   - Groups in event: {event_group_list} ({len(event_group_list)} groups)")
                
                if event_group_list:
                    before_count = base_count
                    base_cyclists = base_cyclists.filter(groups__id__in=event_group_list).distinct()
                    after_count = base_cyclists.count()
                    self.stdout.write(f"   - After event filter: {before_count} -> {after_count} cyclists")
                    
                    if before_count > 0 and after_count == 0:
                        self.stdout.write(f"   - WARNING: Event filter excluded all cyclists!")
                        # Show sample cyclists and their groups
                        samples = Cyclist.objects.filter(
                            is_visible=True,
                            last_active__isnull=False,
                            last_active__gte=active_cutoff
                        )[:3]
                        self.stdout.write(f"   - Sample cyclists (not in event groups):")
                        for c in samples:
                            c_groups = list(c.groups.values_list('id', flat=True))
                            self.stdout.write(f"     * {c.user_id}: groups={c_groups}")
                else:
                    self.stdout.write(f"   - No groups in event, showing all active cyclists")
            except Event.DoesNotExist:
                self.stdout.write(f"2. Event {event_id} does NOT exist!")
        
        # Group-Filterung
        if group_filter_id:
            self.stdout.write("")
            try:
                top_group = Group.objects.get(id=group_filter_id, parent__isnull=True)
                self.stdout.write(f"3. TOP-Group {group_filter_id} exists: {top_group.name}")
                
                from eventboard.utils import get_all_subgroup_ids
                all_group_ids = get_all_subgroup_ids(top_group)
                all_group_ids.append(top_group.id)
                self.stdout.write(f"   - All group IDs (including subgroups): {all_group_ids}")
                
                before_count = base_cyclists.count()
                base_cyclists = base_cyclists.filter(groups__id__in=all_group_ids).distinct()
                after_count = base_cyclists.count()
                self.stdout.write(f"   - After group filter: {before_count} -> {after_count} cyclists")
            except Group.DoesNotExist:
                self.stdout.write(f"3. TOP-Group {group_filter_id} does NOT exist!")
        
        # Final result
        self.stdout.write("")
        final_count = base_cyclists.count()
        self.stdout.write(f"=== Final Result: {final_count} active cyclists ===")
        
        if final_count > 0:
            self.stdout.write("First 5 cyclists:")
            for cyclist in base_cyclists[:5]:
                try:
                    session = cyclist.cyclistdevicecurrentmileage
                    session_km = float(session.cumulative_mileage) if session.cumulative_mileage else 0.0
                except CyclistDeviceCurrentMileage.DoesNotExist:
                    session_km = 0.0
                groups = list(cyclist.groups.values_list('id', flat=True))
                self.stdout.write(f"  - {cyclist.user_id}: session_km={session_km}, groups={groups}")
