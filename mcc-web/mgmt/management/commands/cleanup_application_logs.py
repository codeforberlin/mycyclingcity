# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    cleanup_application_logs.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
"""
Management command to clean up old application logs from the database.

This command removes log entries older than a specified number of days to prevent
the database from growing too large. It can be run manually or via cron job.

Usage:
    python manage.py cleanup_application_logs
    python manage.py cleanup_application_logs --days 30
    python manage.py cleanup_application_logs --days 7 --level DEBUG
    python manage.py cleanup_application_logs --dry-run
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from django.db.models import Count
from datetime import timedelta
from mgmt.models import ApplicationLog
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Clean up old application logs from the database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=30,
            help='Delete logs older than this many days (default: 30)',
        )
        parser.add_argument(
            '--level',
            type=str,
            choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
            default=None,
            help='Only delete logs of this level or lower (default: all levels)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting',
        )

    def handle(self, *args, **options):
        days = options['days']
        level = options['level']
        dry_run = options['dry_run']
        
        # Calculate cutoff date
        cutoff_date = timezone.now() - timedelta(days=days)
        
        # Build query
        queryset = ApplicationLog.objects.filter(timestamp__lt=cutoff_date)
        
        # Filter by level if specified
        if level:
            level_order = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
            level_index = level_order.index(level)
            levels_to_delete = level_order[:level_index + 1]
            queryset = queryset.filter(level__in=levels_to_delete)
        
        # Count entries to be deleted
        count = queryset.count()
        
        if count == 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f'No log entries found older than {days} days'
                    + (f' with level {level} or lower' if level else '')
                )
            )
            return
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f'DRY RUN: Would delete {count} log entries older than {days} days'
                    + (f' with level {level} or lower' if level else '')
                )
            )
            
            # Show breakdown by level
            if not level:
                breakdown = queryset.values('level').annotate(
                    count=Count('id')
                ).order_by('level')
                self.stdout.write('\nBreakdown by level:')
                for item in breakdown:
                    self.stdout.write(f"  {item['level']}: {item['count']}")
            
            # Show date range
            oldest = queryset.order_by('timestamp').first()
            newest = queryset.order_by('-timestamp').first()
            if oldest and newest:
                self.stdout.write(f'\nDate range: {oldest.timestamp} to {newest.timestamp}')
            
            return
        
        # Confirm deletion
        self.stdout.write(
            self.style.WARNING(
                f'About to delete {count} log entries older than {days} days'
                + (f' with level {level} or lower' if level else '')
            )
        )
        
        # Perform deletion
        try:
            with transaction.atomic():
                deleted_count = queryset.delete()[0]
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'Successfully deleted {deleted_count} log entries'
                )
            )
            logger.info(f"Cleaned up {deleted_count} application log entries older than {days} days")
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error deleting log entries: {str(e)}')
            )
            logger.error(f"Error cleaning up application logs: {str(e)}", exc_info=True)
            raise
