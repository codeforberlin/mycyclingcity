# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    cleanup_game_rooms.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from game.models import GameRoom
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Clean up old and inactive game rooms'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=7,
            help='Delete rooms older than X days (default: 7)'
        )
        parser.add_argument(
            '--inactive-hours',
            type=int,
            default=24,
            help='Delete inactive rooms (no activity for X hours, default: 24)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting'
        )
        parser.add_argument(
            '--only-inactive',
            action='store_true',
            help='Only clean up inactive rooms, not old rooms'
        )
        parser.add_argument(
            '--only-old',
            action='store_true',
            help='Only clean up old rooms, not inactive rooms'
        )

    def handle(self, *args, **options):
        days = options['days']
        inactive_hours = options['inactive_hours']
        dry_run = options['dry_run']
        only_inactive = options['only_inactive']
        only_old = options['only_old']

        self.stdout.write(self.style.NOTICE(
            f"--- Game Room Cleanup: {timezone.now()} ---"
        ))

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN MODE - Keine Änderungen werden durchgeführt"))

        total_deleted = 0

        # Clean up old rooms
        if not only_inactive:
            deleted_old = self.cleanup_old_rooms(days, dry_run)
            total_deleted += deleted_old

        # Clean up inactive rooms
        if not only_old:
            deleted_inactive = self.cleanup_inactive_rooms(inactive_hours, dry_run)
            total_deleted += deleted_inactive

        if dry_run:
            self.stdout.write(self.style.SUCCESS(
                f"DRY RUN: {total_deleted} Raum/Räume würden gelöscht werden"
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"✓ {total_deleted} Raum/Räume wurden gelöscht"
            ))

        self.stdout.write(self.style.NOTICE("--- Cleanup beendet ---"))

    def cleanup_old_rooms(self, days, dry_run):
        """Delete rooms older than specified days."""
        cutoff_date = timezone.now() - timedelta(days=days)
        old_rooms = GameRoom.objects.filter(created_at__lt=cutoff_date)

        count = old_rooms.count()

        if count == 0:
            self.stdout.write(f"  Keine Räume älter als {days} Tag(e) gefunden")
            return 0

        self.stdout.write(f"  Gefunden: {count} Raum/Räume älter als {days} Tag(e)")

        if not dry_run:
            # Log room codes before deletion
            room_codes = list(old_rooms.values_list('room_code', flat=True))
            old_rooms.delete()
            logger.info(f"Deleted {count} old game rooms (older than {days} days): {room_codes}")
            self.stdout.write(self.style.SUCCESS(f"  ✓ {count} Raum/Räume gelöscht"))
        else:
            room_codes = list(old_rooms.values_list('room_code', flat=True))
            self.stdout.write(self.style.WARNING(f"  Würde löschen: {', '.join(room_codes)}"))

        return count

    def cleanup_inactive_rooms(self, hours, dry_run):
        """Delete rooms inactive for more than specified hours."""
        cutoff_time = timezone.now() - timedelta(hours=hours)
        inactive_rooms = GameRoom.objects.filter(
            last_activity__lt=cutoff_time,
            is_active=False
        )

        count = inactive_rooms.count()

        if count == 0:
            self.stdout.write(f"  Keine inaktiven Räume (keine Aktivität seit {hours}h) gefunden")
            return 0

        self.stdout.write(f"  Gefunden: {count} inaktive Raum/Räume (keine Aktivität seit {hours}h)")

        if not dry_run:
            # Log room codes before deletion
            room_codes = list(inactive_rooms.values_list('room_code', flat=True))
            inactive_rooms.delete()
            logger.info(f"Deleted {count} inactive game rooms (no activity for {hours} hours): {room_codes}")
            self.stdout.write(self.style.SUCCESS(f"  ✓ {count} Raum/Räume gelöscht"))
        else:
            room_codes = list(inactive_rooms.values_list('room_code', flat=True))
            self.stdout.write(self.style.WARNING(f"  Würde löschen: {', '.join(room_codes)}"))

        return count
