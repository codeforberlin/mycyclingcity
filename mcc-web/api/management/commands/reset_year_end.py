# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    reset_year_end.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
"""
Management command to perform year-end reset for a TOP group (school or institution).

This command will:
1. Create a YearEndSnapshot with all current kilometer and coin totals
2. Save detailed snapshot data for all subgroups, cyclists, and devices
3. Reset distance_total and coins_total to 0 for all affected entities
4. Support undo functionality to restore previous state

Usage:
    python manage.py reset_year_end --group-id 1 --snapshot-date "2024-07-31 23:59:59" --period-type school_year
    python manage.py reset_year_end --group-name "Schule A" --snapshot-date "2024-07-31 23:59:59" --period-type school_year
    python manage.py reset_year_end --undo --snapshot-id 5
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.contrib.auth.models import User
from decimal import Decimal
from datetime import datetime
from api.models import (
    Group, Cyclist, YearEndSnapshot, YearEndSnapshotDetail
)
from iot.models import Device
from eventboard.utils import get_all_subgroup_ids
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Perform year-end reset for a TOP group: create snapshot and reset totals to 0'

    def add_arguments(self, parser):
        parser.add_argument(
            '--group-id',
            type=int,
            help='ID of the TOP group to reset',
        )
        parser.add_argument(
            '--group-name',
            type=str,
            help='Name of the TOP group to reset',
        )
        parser.add_argument(
            '--snapshot-date',
            type=str,
            required=True,
            help='Date/time for the snapshot (format: YYYY-MM-DD HH:MM:SS or YYYY-MM-DD)',
        )
        parser.add_argument(
            '--period-start-date',
            type=str,
            help='Start date of the period (format: YYYY-MM-DD HH:MM:SS or YYYY-MM-DD). Defaults to snapshot-date if not provided.',
        )
        parser.add_argument(
            '--period-end-date',
            type=str,
            help='End date of the period (format: YYYY-MM-DD HH:MM:SS or YYYY-MM-DD). Defaults to snapshot-date if not provided.',
        )
        parser.add_argument(
            '--period-type',
            type=str,
            choices=['school_year', 'calendar_year'],
            required=True,
            help='Type of period: school_year or calendar_year',
        )
        parser.add_argument(
            '--user-id',
            type=int,
            help='User ID who performs the reset (for audit trail)',
        )
        parser.add_argument(
            '--undo',
            action='store_true',
            help='Undo a previous snapshot (restore totals)',
        )
        parser.add_argument(
            '--snapshot-id',
            type=int,
            help='ID of the snapshot to undo (required for --undo)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be reset without actually doing it',
        )
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Skip confirmation prompt (use with caution!)',
        )

    def handle(self, *args, **options):
        undo = options['undo']
        snapshot_id = options.get('snapshot_id')
        dry_run = options['dry_run']
        confirm = options['confirm']

        if undo:
            return self.handle_undo(snapshot_id, dry_run, confirm, options)
        else:
            return self.handle_reset(options)

    def handle_reset(self, options):
        """Handle the reset operation."""
        group_id = options.get('group_id')
        group_name = options.get('group_name')
        snapshot_date_str = options['snapshot_date']
        period_start_date_str = options.get('period_start_date')
        period_end_date_str = options.get('period_end_date')
        period_type = options['period_type']
        user_id = options.get('user_id')
        dry_run = options['dry_run']
        confirm = options['confirm']

        # Parse dates
        try:
            snapshot_date = self.parse_date(snapshot_date_str)
            period_start_date = self.parse_date(period_start_date_str) if period_start_date_str else snapshot_date
            period_end_date = self.parse_date(period_end_date_str) if period_end_date_str else snapshot_date
        except ValueError as e:
            raise CommandError(f"Invalid date format: {e}")

        # Get TOP group
        if group_id:
            try:
                top_group = Group.objects.get(id=group_id)
            except Group.DoesNotExist:
                raise CommandError(f"Group with ID {group_id} not found")
        elif group_name:
            try:
                top_group = Group.objects.get(name=group_name)
            except Group.DoesNotExist:
                raise CommandError(f"Group with name '{group_name}' not found")
            except Group.MultipleObjectsReturned:
                raise CommandError(f"Multiple groups found with name '{group_name}'. Please use --group-id instead.")
        else:
            raise CommandError("Either --group-id or --group-name must be provided")

        # Verify it's a TOP group (no parent)
        if top_group.parent is not None:
            raise CommandError(f"Group '{top_group.name}' is not a TOP group (it has a parent: '{top_group.parent.name}')")

        # Get user
        user = None
        if user_id:
            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                raise CommandError(f"User with ID {user_id} not found")

        # Get all subgroups (recursively)
        all_subgroup_ids = get_all_subgroup_ids(top_group)
        all_subgroup_ids.append(top_group.id)  # Include TOP group itself
        all_groups = Group.objects.filter(id__in=all_subgroup_ids)

        # Get all cyclists in these groups
        all_cyclists = Cyclist.objects.filter(groups__id__in=all_subgroup_ids).distinct()

        # Get all devices assigned to these groups
        all_devices = Device.objects.filter(group__id__in=all_subgroup_ids)

        # Count what will be affected
        group_count = all_groups.count()
        cyclist_count = all_cyclists.count()
        device_count = all_devices.count()

        # Show summary
        self.stdout.write(self.style.WARNING("=" * 60))
        self.stdout.write(self.style.WARNING("YEAR-END RESET"))
        self.stdout.write(self.style.WARNING("=" * 60))
        self.stdout.write("")
        self.stdout.write(f"TOP Group: {top_group.name} (ID: {top_group.id})")
        self.stdout.write(f"Period Type: {dict(YearEndSnapshot.PERIOD_TYPE_CHOICES).get(period_type, period_type)}")
        self.stdout.write(f"Snapshot Date: {snapshot_date}")
        self.stdout.write(f"Period: {period_start_date} to {period_end_date}")
        self.stdout.write("")
        self.stdout.write("This will:")
        self.stdout.write(f"  1. Create a snapshot with current totals")
        self.stdout.write(f"  2. Reset {group_count} Groups (distance_total, coins_total → 0)")
        self.stdout.write(f"  3. Reset {cyclist_count} Cyclists (distance_total, coins_total → 0)")
        self.stdout.write(f"  4. Reset {device_count} Devices (distance_total → 0)")
        self.stdout.write("")
        self.stdout.write(self.style.NOTICE("Note: HourlyMetric entries are NOT deleted. They remain as historical data."))
        self.stdout.write(self.style.NOTICE("Note: Active sessions (CyclistDeviceCurrentMileage) are NOT affected."))
        self.stdout.write("")

        if not confirm and not dry_run:
            self.stdout.write(self.style.ERROR("WARNING: This operation can be undone using --undo, but please verify the data!"))
            response = input("Type 'RESET' to confirm: ")
            if response != 'RESET':
                self.stdout.write(self.style.ERROR("Reset cancelled."))
                return

        if dry_run:
            self.stdout.write(self.style.SUCCESS("DRY RUN: Would perform reset as shown above"))
            return

        # Perform reset
        self.stdout.write(self.style.NOTICE("Starting reset..."))

        try:
            with transaction.atomic():
                # 1. Create snapshot
                self.stdout.write("Creating snapshot...")
                snapshot = YearEndSnapshot.objects.create(
                    group=top_group,
                    snapshot_date=snapshot_date,
                    period_start_date=period_start_date,
                    period_end_date=period_end_date,
                    period_type=period_type,
                    group_total_km=top_group.distance_total,
                    group_total_coins=top_group.coins_total,
                    created_by=user
                )
                self.stdout.write(self.style.SUCCESS(f"  ✓ Created snapshot ID: {snapshot.id}"))

                # 2. Save group details
                self.stdout.write("Saving group details...")
                group_details_count = 0
                for group in all_groups:
                    YearEndSnapshotDetail.objects.create(
                        snapshot=snapshot,
                        group=group,
                        distance_total=group.distance_total,
                        coins_total=group.coins_total
                    )
                    group_details_count += 1
                self.stdout.write(self.style.SUCCESS(f"  ✓ Saved {group_details_count} group details"))

                # 3. Save cyclist details
                self.stdout.write("Saving cyclist details...")
                cyclist_details_count = 0
                for cyclist in all_cyclists:
                    YearEndSnapshotDetail.objects.create(
                        snapshot=snapshot,
                        cyclist=cyclist,
                        distance_total=cyclist.distance_total,
                        coins_total=cyclist.coins_total
                    )
                    cyclist_details_count += 1
                self.stdout.write(self.style.SUCCESS(f"  ✓ Saved {cyclist_details_count} cyclist details"))

                # 4. Save device details
                self.stdout.write("Saving device details...")
                device_details_count = 0
                for device in all_devices:
                    YearEndSnapshotDetail.objects.create(
                        snapshot=snapshot,
                        device=device,
                        distance_total=device.distance_total,
                        coins_total=0  # Devices don't have coins
                    )
                    device_details_count += 1
                self.stdout.write(self.style.SUCCESS(f"  ✓ Saved {device_details_count} device details"))

                # 5. Reset group totals
                self.stdout.write("Resetting group totals...")
                all_groups.update(
                    distance_total=Decimal('0.00000'),
                    coins_total=0
                )
                self.stdout.write(self.style.SUCCESS(f"  ✓ Reset {group_count} groups"))

                # 6. Reset cyclist totals
                self.stdout.write("Resetting cyclist totals...")
                all_cyclists.update(
                    distance_total=Decimal('0.00000'),
                    coins_total=0,
                    coins_spendable=0
                )
                self.stdout.write(self.style.SUCCESS(f"  ✓ Reset {cyclist_count} cyclists"))

                # 7. Reset device totals
                self.stdout.write("Resetting device totals...")
                all_devices.update(
                    distance_total=Decimal('0.00000')
                )
                self.stdout.write(self.style.SUCCESS(f"  ✓ Reset {device_count} devices"))

                # 8. Invalidate cache for affected groups
                self.stdout.write("Invalidating cache...")
                from api.helpers import invalidate_cache_for_top_group
                invalidate_cache_for_top_group(top_group)
                self.stdout.write(self.style.SUCCESS(f"  ✓ Cache invalidated"))

            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS("=" * 60))
            self.stdout.write(self.style.SUCCESS("RESET COMPLETED SUCCESSFULLY"))
            self.stdout.write(self.style.SUCCESS("=" * 60))
            self.stdout.write("")
            self.stdout.write(f"Snapshot ID: {snapshot.id}")
            self.stdout.write(f"To undo this reset, run:")
            self.stdout.write(f"  python manage.py reset_year_end --undo --snapshot-id {snapshot.id}")
            self.stdout.write("")

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"ERROR during reset: {e}"))
            logger.error(f"Error during year-end reset: {e}", exc_info=True)
            raise

    def handle_undo(self, snapshot_id, dry_run, confirm, options):
        """Handle the undo operation."""
        if not snapshot_id:
            raise CommandError("--snapshot-id is required when using --undo")

        try:
            snapshot = YearEndSnapshot.objects.get(id=snapshot_id)
        except YearEndSnapshot.DoesNotExist:
            raise CommandError(f"Snapshot with ID {snapshot_id} not found")

        if snapshot.is_undone:
            raise CommandError(f"Snapshot {snapshot_id} has already been undone")

        # Get user
        user = None
        user_id = options.get('user_id')
        if user_id:
            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                raise CommandError(f"User with ID {user_id} not found")

        # Get all details
        group_details = snapshot.details.filter(group__isnull=False)
        cyclist_details = snapshot.details.filter(cyclist__isnull=False)
        device_details = snapshot.details.filter(device__isnull=False)

        # Show summary
        self.stdout.write(self.style.WARNING("=" * 60))
        self.stdout.write(self.style.WARNING("UNDO YEAR-END RESET"))
        self.stdout.write(self.style.WARNING("=" * 60))
        self.stdout.write("")
        self.stdout.write(f"Snapshot ID: {snapshot.id}")
        self.stdout.write(f"Group: {snapshot.group.name}")
        self.stdout.write(f"Snapshot Date: {snapshot.snapshot_date}")
        self.stdout.write(f"Period Type: {dict(YearEndSnapshot.PERIOD_TYPE_CHOICES).get(snapshot.period_type, snapshot.period_type)}")
        self.stdout.write("")
        self.stdout.write("This will restore:")
        self.stdout.write(f"  - {group_details.count()} Groups")
        self.stdout.write(f"  - {cyclist_details.count()} Cyclists")
        self.stdout.write(f"  - {device_details.count()} Devices")
        self.stdout.write("")
        self.stdout.write(self.style.WARNING("WARNING: This will overwrite current totals with snapshot values!"))
        self.stdout.write("")

        if not confirm and not dry_run:
            response = input("Type 'UNDO' to confirm: ")
            if response != 'UNDO':
                self.stdout.write(self.style.ERROR("Undo cancelled."))
                return

        if dry_run:
            self.stdout.write(self.style.SUCCESS("DRY RUN: Would restore snapshot as shown above"))
            return

        # Perform undo
        self.stdout.write(self.style.NOTICE("Starting undo..."))

        try:
            with transaction.atomic():
                # 1. Restore group totals
                self.stdout.write("Restoring group totals...")
                group_count = 0
                for detail in group_details.select_related('group'):
                    detail.group.distance_total = detail.distance_total
                    detail.group.coins_total = detail.coins_total
                    detail.group.save(update_fields=['distance_total', 'coins_total'])
                    group_count += 1
                self.stdout.write(self.style.SUCCESS(f"  ✓ Restored {group_count} groups"))

                # 2. Restore cyclist totals
                self.stdout.write("Restoring cyclist totals...")
                cyclist_count = 0
                for detail in cyclist_details.select_related('cyclist'):
                    detail.cyclist.distance_total = detail.distance_total
                    detail.cyclist.coins_total = detail.coins_total
                    # Note: coins_spendable is not restored (it's calculated)
                    detail.cyclist.save(update_fields=['distance_total', 'coins_total'])
                    cyclist_count += 1
                self.stdout.write(self.style.SUCCESS(f"  ✓ Restored {cyclist_count} cyclists"))

                # 3. Restore device totals
                self.stdout.write("Restoring device totals...")
                device_count = 0
                for detail in device_details.select_related('device'):
                    detail.device.distance_total = detail.distance_total
                    detail.device.save(update_fields=['distance_total'])
                    device_count += 1
                self.stdout.write(self.style.SUCCESS(f"  ✓ Restored {device_count} devices"))

                # 4. Mark snapshot as undone
                snapshot.is_undone = True
                snapshot.undone_at = timezone.now()
                snapshot.undone_by = user
                snapshot.save(update_fields=['is_undone', 'undone_at', 'undone_by'])

                # 5. Invalidate cache for affected groups
                self.stdout.write("Invalidating cache...")
                from api.helpers import invalidate_cache_for_top_group
                invalidate_cache_for_top_group(snapshot.group)
                self.stdout.write(self.style.SUCCESS(f"  ✓ Cache invalidated"))

            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS("=" * 60))
            self.stdout.write(self.style.SUCCESS("UNDO COMPLETED SUCCESSFULLY"))
            self.stdout.write(self.style.SUCCESS("=" * 60))
            self.stdout.write("")

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"ERROR during undo: {e}"))
            logger.error(f"Error during year-end undo: {e}", exc_info=True)
            raise

    def parse_date(self, date_str):
        """Parse date string in various formats."""
        if not date_str:
            return None

        # Try different formats
        formats = [
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d %H:%M',
            '%Y-%m-%d',
            '%d.%m.%Y %H:%M:%S',
            '%d.%m.%Y %H:%M',
            '%d.%m.%Y',
        ]

        for fmt in formats:
            try:
                return timezone.make_aware(datetime.strptime(date_str, fmt))
            except ValueError:
                continue

        raise ValueError(f"Unable to parse date: {date_str}")
