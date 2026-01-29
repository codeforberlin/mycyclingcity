# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    debug_operator_milestones.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

"""
Debug script to check why an operator can see milestones from other TOP groups.

Usage:
    python manage.py debug_operator_milestones --username mccoperator
"""

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from api.models import Group, GroupMilestoneAchievement
from mgmt.admin import get_operator_managed_group_ids

User = get_user_model()


class Command(BaseCommand):
    help = 'Debug why operator can see milestones from other TOP groups'

    def add_arguments(self, parser):
        parser.add_argument(
            '--username',
            type=str,
            default='mccoperator',
            help='Username of the operator to check',
        )

    def handle(self, *args, **options):
        username = options['username']
        
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'User "{username}" not found'))
            return
        
        self.stdout.write(self.style.SUCCESS(f'\n=== Debugging Operator: {username} ===\n'))
        
        # 1. Prüfe TOP-Gruppen des Operators
        managed_top_groups = user.managed_groups.all()
        self.stdout.write(f'TOP-Gruppen des Operators:')
        top_group_ids = []
        for group in managed_top_groups:
            self.stdout.write(f'  - {group.name} (ID: {group.id})')
            top_group_ids.append(group.id)
        
        if not top_group_ids:
            self.stdout.write(self.style.WARNING('  Keine TOP-Gruppen zugewiesen!'))
            return
        
        # 2. Prüfe managed_group_ids
        managed_group_ids = get_operator_managed_group_ids(user)
        self.stdout.write(f'\nVerwaltete Gruppen-IDs (inkl. Untergruppen): {len(managed_group_ids)} Gruppen')
        self.stdout.write(f'  IDs: {sorted(managed_group_ids)[:20]}...' if len(managed_group_ids) > 20 else f'  IDs: {sorted(managed_group_ids)}')
        
        # 3. Hole alle Meilensteine
        all_milestones = GroupMilestoneAchievement.objects.select_related('group', 'milestone', 'track').all()
        self.stdout.write(f'\nAlle Meilensteine in der Datenbank: {all_milestones.count()}')
        
        # 4. Prüfe Meilensteine nach Gruppen
        self.stdout.write(f'\nMeilensteine nach Gruppen:')
        milestones_by_group = {}
        for milestone in all_milestones:
            group_id = milestone.group_id
            if group_id not in milestones_by_group:
                milestones_by_group[group_id] = []
            milestones_by_group[group_id].append(milestone)
        
        # 5. Prüfe für jede Gruppe, ob sie zu einer TOP-Gruppe gehört
        self.stdout.write(f'\nPrüfung der Gruppen-Hierarchie:')
        invalid_milestones = []
        valid_milestones = []
        
        for group_id, milestones in milestones_by_group.items():
            try:
                group = Group.objects.get(id=group_id)
                top_parent = self._get_top_parent(group)
                
                belongs_to_top = top_parent.id in top_group_ids
                
                status = '✓' if belongs_to_top else '✗'
                self.stdout.write(f'  {status} Gruppe "{group.name}" (ID: {group_id}) -> TOP: "{top_parent.name}" (ID: {top_parent.id})')
                
                if belongs_to_top:
                    valid_milestones.extend(milestones)
                else:
                    invalid_milestones.extend(milestones)
                    self.stdout.write(self.style.WARNING(f'    -> {len(milestones)} Meilensteine sollten NICHT angezeigt werden!'))
                    
            except Group.DoesNotExist:
                self.stdout.write(self.style.ERROR(f'  ✗ Gruppe ID {group_id} nicht gefunden!'))
        
        # 6. Zeige problematische Meilensteine
        if invalid_milestones:
            self.stdout.write(self.style.ERROR(f'\n=== PROBLEM: {len(invalid_milestones)} Meilensteine von anderen TOP-Gruppen ==='))
            for milestone in invalid_milestones[:10]:  # Zeige nur die ersten 10
                top_parent = self._get_top_parent(milestone.group)
                self.stdout.write(f'  - Gruppe: "{milestone.group.name}" -> TOP: "{top_parent.name}" | Meilenstein: "{milestone.milestone.name}" | Track: "{milestone.track.name}"')
            if len(invalid_milestones) > 10:
                self.stdout.write(f'  ... und {len(invalid_milestones) - 10} weitere')
        
        # 7. Prüfe, ob die Gruppen in managed_group_ids sind
        self.stdout.write(f'\nPrüfung: Sind die problematischen Gruppen in managed_group_ids?')
        for milestone in invalid_milestones[:5]:
            group_id = milestone.group_id
            in_managed = group_id in managed_group_ids
            status = 'JA' if in_managed else 'NEIN'
            self.stdout.write(f'  Gruppe "{milestone.group.name}" (ID: {group_id}): {status}')
            if in_managed:
                self.stdout.write(self.style.ERROR(f'    -> PROBLEM: Gruppe ist in managed_group_ids, obwohl sie nicht zur TOP-Gruppe gehört!'))
        
        # 8. Zusammenfassung
        self.stdout.write(f'\n=== Zusammenfassung ===')
        self.stdout.write(f'  TOP-Gruppen: {len(top_group_ids)}')
        self.stdout.write(f'  Verwaltete Gruppen: {len(managed_group_ids)}')
        self.stdout.write(f'  Gültige Meilensteine: {len(valid_milestones)}')
        self.stdout.write(f'  Ungültige Meilensteine: {len(invalid_milestones)}')
        
        if invalid_milestones:
            self.stdout.write(self.style.ERROR(f'\nFEHLER: {len(invalid_milestones)} Meilensteine sollten nicht angezeigt werden!'))
    
    def _get_top_parent(self, group):
        """Finde die TOP-Gruppe (Parent ohne Parent)."""
        visited = set()
        current = group
        
        while current and current.parent and current.id not in visited:
            visited.add(current.id)
            current = current.parent
        
        return current
