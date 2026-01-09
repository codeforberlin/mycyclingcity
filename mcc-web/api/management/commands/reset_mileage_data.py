# mcc/api/management/commands/reset_mileage_data.py

"""
Management command to reset all mileage data in the database.

This command will:
1. Reset all distance_total and coins_total to 0 for Groups, Cyclists, and Devices
2. Delete all HourlyMetric entries (historical data)
3. Delete all CyclistDeviceCurrentMileage entries (current sessions)
4. Optionally delete EventHistory and TravelHistory entries

Usage:
    python manage.py reset_mileage_data
    python manage.py reset_mileage_data --confirm
    python manage.py reset_mileage_data --include-history
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from decimal import Decimal
from api.models import (
    Group, Cyclist,
    HourlyMetric, CyclistDeviceCurrentMileage,
    EventHistory, TravelHistory,
    GroupTravelStatus, GroupEventStatus
)
from iot.models import Device
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Reset all mileage data: set distance_total/coins_total to 0 and delete historical data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Skip confirmation prompt (use with caution!)',
        )
        parser.add_argument(
            '--include-history',
            action='store_true',
            help='Also delete EventHistory and TravelHistory entries',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be reset without actually doing it',
        )

    def handle(self, *args, **options):
        confirm = options['confirm']
        include_history = options['include_history']
        dry_run = options['dry_run']

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN MODE - No changes will be made"))
            self.stdout.write("")

        # Count what will be affected
        group_count = Group.objects.count()
        player_count = Cyclist.objects.count()
        device_count = Device.objects.count()
        hourly_metric_count = HourlyMetric.objects.count()
        session_count = CyclistDeviceCurrentMileage.objects.count()
        travel_status_count = GroupTravelStatus.objects.count()
        event_status_count = GroupEventStatus.objects.count()
        event_history_count = EventHistory.objects.count() if include_history else 0
        travel_history_count = TravelHistory.objects.count() if include_history else 0

        # Show summary
        self.stdout.write(self.style.WARNING("=" * 60))
        self.stdout.write(self.style.WARNING("MILEAGE DATA RESET"))
        self.stdout.write(self.style.WARNING("=" * 60))
        self.stdout.write("")
        self.stdout.write("This will reset:")
        self.stdout.write(f"  - {group_count} Groups (distance_total, coins_total → 0)")
        self.stdout.write(f"  - {player_count} Cyclists (distance_total, coins_total → 0)")
        self.stdout.write(f"  - {device_count} Devices (distance_total → 0)")
        self.stdout.write(f"  - {hourly_metric_count} HourlyMetric entries (DELETE)")
        self.stdout.write(f"  - {session_count} CyclistDeviceCurrentMileage entries (DELETE)")
        self.stdout.write(f"  - {travel_status_count} GroupTravelStatus entries (current_travel_distance → 0)")
        self.stdout.write(f"  - {event_status_count} GroupEventStatus entries (current_distance_km → 0)")
        if include_history:
            self.stdout.write(f"  - {event_history_count} EventHistory entries (DELETE)")
            self.stdout.write(f"  - {travel_history_count} TravelHistory entries (DELETE)")
        self.stdout.write("")

        if not confirm and not dry_run:
            self.stdout.write(self.style.ERROR("WARNING: This operation cannot be undone!"))
            response = input("Type 'RESET' to confirm: ")
            if response != 'RESET':
                self.stdout.write(self.style.ERROR("Reset cancelled."))
                return

        if dry_run:
            self.stdout.write(self.style.SUCCESS("DRY RUN: Would reset all data as shown above"))
            return

        # Perform reset
        self.stdout.write(self.style.NOTICE("Starting reset..."))
        
        try:
            with transaction.atomic():
                # 1. Reset Group totals
                self.stdout.write("Resetting Group totals...")
                Group.objects.all().update(
                    distance_total=Decimal('0.00000'),
                    coins_total=0
                )
                self.stdout.write(self.style.SUCCESS(f"  ✓ Reset {group_count} groups"))

                # 2. Reset Cyclist totals
                self.stdout.write("Resetting Cyclist totals...")
                Cyclist.objects.all().update(
                    distance_total=Decimal('0.00000'),
                    coins_total=0,
                    coins_spendable=0
                )
                self.stdout.write(self.style.SUCCESS(f"  ✓ Reset {player_count} players"))

                # 3. Reset Device totals
                self.stdout.write("Resetting Device totals...")
                Device.objects.all().update(
                    distance_total=Decimal('0.00000')
                )
                self.stdout.write(self.style.SUCCESS(f"  ✓ Reset {device_count} devices"))

                # 4. Delete HourlyMetric entries
                self.stdout.write("Deleting HourlyMetric entries...")
                deleted_metrics, _ = HourlyMetric.objects.all().delete()
                self.stdout.write(self.style.SUCCESS(f"  ✓ Deleted {deleted_metrics} HourlyMetric entries"))

                # 5. Delete CyclistDeviceCurrentMileage entries
                self.stdout.write("Deleting CyclistDeviceCurrentMileage entries...")
                deleted_sessions, _ = CyclistDeviceCurrentMileage.objects.all().delete()
                self.stdout.write(self.style.SUCCESS(f"  ✓ Deleted {deleted_sessions} session entries"))

                # 6. Reset GroupTravelStatus
                self.stdout.write("Resetting GroupTravelStatus entries...")
                GroupTravelStatus.objects.all().update(
                    current_travel_distance=Decimal('0.00000'),
                    start_km_offset=Decimal('0.00000')
                )
                self.stdout.write(self.style.SUCCESS(f"  ✓ Reset {travel_status_count} travel status entries"))

                # 7. Reset GroupEventStatus
                self.stdout.write("Resetting GroupEventStatus entries...")
                GroupEventStatus.objects.all().update(
                    current_distance_km=Decimal('0.00000'),
                    start_km_offset=Decimal('0.00000')
                )
                self.stdout.write(self.style.SUCCESS(f"  ✓ Reset {event_status_count} event status entries"))

                # 8. Optionally delete history entries
                if include_history:
                    self.stdout.write("Deleting EventHistory entries...")
                    deleted_events, _ = EventHistory.objects.all().delete()
                    self.stdout.write(self.style.SUCCESS(f"  ✓ Deleted {deleted_events} EventHistory entries"))

                    self.stdout.write("Deleting TravelHistory entries...")
                    deleted_travels, _ = TravelHistory.objects.all().delete()
                    self.stdout.write(self.style.SUCCESS(f"  ✓ Deleted {deleted_travels} TravelHistory entries"))

            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS("=" * 60))
            self.stdout.write(self.style.SUCCESS("RESET COMPLETED SUCCESSFULLY"))
            self.stdout.write(self.style.SUCCESS("=" * 60))
            self.stdout.write("")
            self.stdout.write("All mileage data has been reset. The system is now ready for a fresh start.")
            self.stdout.write("")

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"ERROR during reset: {e}"))
            logger.error(f"Error during mileage data reset: {e}", exc_info=True)
            raise

