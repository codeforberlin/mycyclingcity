# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    set_gunicorn_sync.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

"""
Management command to set Gunicorn worker class to 'sync' to avoid signal handler issues.

This command sets the Gunicorn configuration to use 'sync' worker class instead of 'gthread',
which prevents "signal only works in main thread" errors when using mcrcon in worker threads.

Usage:
    python manage.py set_gunicorn_sync
    python manage.py set_gunicorn_sync --threads=1
"""

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from mgmt.models import GunicornConfig


User = get_user_model()


class Command(BaseCommand):
    help = 'Set Gunicorn worker class to sync to avoid signal handler issues'

    def add_arguments(self, parser):
        parser.add_argument(
            '--threads',
            type=int,
            default=1,
            help='Number of threads (default: 1, not used with sync worker class)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be changed without actually changing it',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        threads = options['threads']
        
        try:
            config = GunicornConfig.get_config()
            
            old_worker_class = config.worker_class
            old_threads = config.threads
            
            if dry_run:
                self.stdout.write(self.style.WARNING('DRY RUN - No changes will be made'))
                self.stdout.write('')
                self.stdout.write(f'Current configuration:')
                self.stdout.write(f'  Worker Class: {old_worker_class}')
                self.stdout.write(f'  Threads: {old_threads}')
                self.stdout.write('')
                self.stdout.write(f'Would change to:')
                self.stdout.write(f'  Worker Class: sync')
                self.stdout.write(f'  Threads: {threads}')
                self.stdout.write('')
                self.stdout.write(self.style.WARNING('Run without --dry-run to apply changes'))
                return
            
            # Set worker class to sync
            config.worker_class = 'sync'
            config.threads = threads
            
            # Try to get current user (if available)
            try:
                # This might not work in all contexts, so we catch the exception
                from django.contrib.auth.models import AnonymousUser
                user = getattr(self, 'user', None)
                if user and not isinstance(user, AnonymousUser):
                    config.updated_by = user
            except Exception:
                pass  # Ignore if user is not available
            
            config.save()
            
            self.stdout.write(self.style.SUCCESS('✓ Gunicorn configuration updated'))
            self.stdout.write('')
            self.stdout.write(f'Changed:')
            self.stdout.write(f'  Worker Class: {old_worker_class} → sync')
            self.stdout.write(f'  Threads: {old_threads} → {threads}')
            self.stdout.write('')
            self.stdout.write(self.style.WARNING('⚠ IMPORTANT: Restart the server for changes to take effect:'))
            self.stdout.write('  /data/appl/mcc/mcc-web/scripts/mcc-web.sh restart')
            self.stdout.write('')
            self.stdout.write('This change prevents "signal only works in main thread" errors')
            self.stdout.write('when using mcrcon (Minecraft RCON) in worker threads.')
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'✗ Failed to update configuration: {e}'))
            raise
