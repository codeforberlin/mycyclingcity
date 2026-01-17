# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    cleanup_ended_rooms.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

"""
Management command to clean up old ended game rooms.

Usage:
    python manage.py cleanup_ended_rooms [--days=7] [--dry-run]
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from game.models import GameRoom


class Command(BaseCommand):
    help = 'Deletes old ended game rooms (inactive rooms older than specified days)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=7,
            help='Number of days after which ended rooms should be deleted (default: 7)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting',
        )

    def handle(self, *args, **options):
        days = options['days']
        dry_run = options['dry_run']
        
        cutoff_date = timezone.now() - timedelta(days=days)
        
        # Find all inactive (ended) rooms older than cutoff_date
        old_ended_rooms = GameRoom.objects.filter(
            is_active=False,
            last_activity__lt=cutoff_date
        )
        
        count = old_ended_rooms.count()
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f'DRY RUN: Would delete {count} ended room(s) older than {days} days (before {cutoff_date.strftime("%Y-%m-%d %H:%M:%S")})'
                )
            )
            for room in old_ended_rooms[:10]:  # Show first 10
                self.stdout.write(f'  - Room {room.room_code} (ended: {room.last_activity})')
            if count > 10:
                self.stdout.write(f'  ... and {count - 10} more')
        else:
            deleted_count = old_ended_rooms.delete()[0]
            self.stdout.write(
                self.style.SUCCESS(
                    f'Successfully deleted {deleted_count} ended room(s) older than {days} days'
                )
            )
