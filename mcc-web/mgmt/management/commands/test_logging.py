# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    test_logging.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
"""
Management command to test the logging system and generate test log entries.

This command helps verify that the DatabaseLogHandler is working correctly
and that logs are being stored in the database.

Usage:
    python manage.py test_logging
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
import logging
import time

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Test the application logging system and generate test log entries'

    def handle(self, *args, **options):
        self.stdout.write("=" * 80)
        self.stdout.write(self.style.SUCCESS("Testing Application Logging System"))
        self.stdout.write("=" * 80)
        
        # Check if ApplicationLog model exists
        try:
            from mgmt.models import ApplicationLog
            count_before = ApplicationLog.objects.count()
            self.stdout.write(
                self.style.SUCCESS(
                    f"✓ ApplicationLog model exists. Current entries: {count_before}"
                )
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"✗ Error accessing ApplicationLog model: {e}")
            )
            self.stdout.write(
                self.style.WARNING(
                    "Make sure you have run: python manage.py migrate mgmt"
                )
            )
            return
        
        # Get different loggers
        logger_api = logging.getLogger('api')
        logger_mgmt = logging.getLogger('mgmt')
        logger_iot = logging.getLogger('iot')
        logger_test = logging.getLogger('test')
        
        self.stdout.write("\nGenerating test log entries...")
        
        # Test WARNING log (should be stored)
        logger_test.warning("Test WARNING message - should appear in Admin")
        self.stdout.write("  ✓ Generated WARNING log")
        
        # Test ERROR log (should be stored)
        logger_test.error("Test ERROR message - should appear in Admin")
        self.stdout.write("  ✓ Generated ERROR log")
        
        # Test CRITICAL log (should be stored)
        logger_test.critical("Test CRITICAL message - should appear in Admin")
        self.stdout.write("  ✓ Generated CRITICAL log")
        
        # Test INFO log (should NOT be stored by default)
        logger_test.info("Test INFO message - will NOT appear in Admin (unless LOG_DB_DEBUG=True)")
        self.stdout.write("  ✓ Generated INFO log (will not be stored by default)")
        
        # Test from different loggers
        logger_api.warning("Test WARNING from api logger")
        logger_mgmt.error("Test ERROR from mgmt logger")
        logger_iot.warning("Test WARNING from iot logger")
        self.stdout.write("  ✓ Generated logs from different loggers")
        
        # Wait for batch processing (handler flushes every 5 seconds or after 10 entries)
        self.stdout.write("\nWaiting 6 seconds for batch processing...")
        time.sleep(6)
        
        # Check if logs were created
        try:
            count_after = ApplicationLog.objects.count()
            new_logs = count_after - count_before
            
            if new_logs > 0:
                self.stdout.write(
                    self.style.SUCCESS(f"\n✓ Success! {new_logs} new log entries created")
                )
                self.stdout.write(f"  Total entries in database: {count_after}")
                
                self.stdout.write("\nRecent log entries:")
                recent_logs = ApplicationLog.objects.order_by('-timestamp')[:5]
                for log in recent_logs:
                    level_color = {
                        'WARNING': self.style.WARNING,
                        'ERROR': self.style.ERROR,
                        'CRITICAL': self.style.ERROR,
                    }.get(log.level, self.style.SUCCESS)
                    
                    self.stdout.write(
                        level_color(
                            f"  - [{log.level}] {log.logger_name}: {log.message[:60]}"
                        )
                    )
            else:
                self.stdout.write(
                    self.style.WARNING("\n⚠ No new logs were created.")
                )
                self.stdout.write("\nPossible reasons:")
                self.stdout.write("  1. Handler batch not flushed yet (wait a bit longer)")
                self.stdout.write("  2. Handler not properly configured in settings.py")
                self.stdout.write("  3. Logs are being filtered out by level")
                self.stdout.write("  4. Database connection issue")
                
                # Check handler configuration
                self.stdout.write("\nChecking handler configuration...")
                from django.conf import settings
                if 'database' in settings.LOGGING.get('handlers', {}):
                    self.stdout.write("  ✓ Database handler is configured")
                else:
                    self.stdout.write(
                        self.style.ERROR("  ✗ Database handler is NOT configured")
                    )
                    
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"\n✗ Error checking logs: {e}")
            )
        
        self.stdout.write("\n" + "=" * 80)
        self.stdout.write(
            self.style.SUCCESS(
                "Test completed. Check Admin GUI at: /admin/mgmt/applicationlog/"
            )
        )
        self.stdout.write("=" * 80)
