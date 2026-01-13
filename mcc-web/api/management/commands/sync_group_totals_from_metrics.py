# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    sync_group_totals_from_metrics.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
"""
Management command to synchronize group.distance_total with HourlyMetrics.

This command recalculates group.distance_total based on all HourlyMetrics
to ensure consistency between Admin GUI and Reports.

Usage:
    python manage.py sync_group_totals_from_metrics
    python manage.py sync_group_totals_from_metrics --group-id=41
"""

from django.core.management.base import BaseCommand
from django.db.models import Sum
from decimal import Decimal
from api.models import Group, HourlyMetric


class Command(BaseCommand):
    help = 'Synchronize group.distance_total with HourlyMetrics data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--group-id',
            type=int,
            help='Sync only a specific group by ID',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be changed without actually updating',
        )

    def handle(self, *args, **options):
        group_id = options.get('group_id')
        dry_run = options.get('dry_run', False)
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))
            self.stdout.write('')
        
        # Get groups to process
        if group_id:
            groups = Group.objects.filter(id=group_id)
            if not groups.exists():
                self.stdout.write(self.style.ERROR(f'Group with ID {group_id} not found'))
                return
        else:
            groups = Group.objects.filter(is_visible=True)
        
        self.stdout.write(f'Processing {groups.count()} group(s)...')
        self.stdout.write('')
        
        updated_count = 0
        unchanged_count = 0
        
        for group in groups:
            # Calculate total from HourlyMetrics
            metrics_total = HourlyMetric.objects.filter(
                group_at_time=group
            ).aggregate(
                total=Sum('distance_km')
            )['total'] or Decimal('0.00000')
            
            current_total = group.distance_total or Decimal('0.00000')
            difference = float(metrics_total) - float(current_total)
            
            if abs(difference) > 0.0001:  # Only update if difference is significant
                self.stdout.write(
                    f'Group: {group.name} (ID: {group.id})'
                )
                self.stdout.write(
                    f'  Current distance_total: {current_total} km'
                )
                self.stdout.write(
                    f'  HourlyMetrics sum: {metrics_total} km'
                )
                self.stdout.write(
                    f'  Difference: {difference:+.3f} km'
                )
                
                if not dry_run:
                    group.distance_total = metrics_total
                    group.save(update_fields=['distance_total'])
                    self.stdout.write(
                        self.style.SUCCESS(f'  ✓ Updated to {metrics_total} km')
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(f'  [DRY RUN] Would update to {metrics_total} km')
                    )
                self.stdout.write('')
                updated_count += 1
            else:
                unchanged_count += 1
        
        self.stdout.write('')
        self.stdout.write(f'Summary:')
        self.stdout.write(f'  Updated: {updated_count}')
        self.stdout.write(f'  Unchanged: {unchanged_count}')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('\nDRY RUN - No changes were made'))
        else:
            self.stdout.write(self.style.SUCCESS(f'\nSuccessfully synchronized {updated_count} group(s)'))

