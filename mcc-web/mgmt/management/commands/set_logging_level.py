# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    set_logging_level.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
"""
Management command to set the default logging level for database storage.

This command sets the minimum log level that will be stored in the database
and displayed in the Admin GUI. Can be used during deployment or setup.

Usage:
    python manage.py set_logging_level WARNING
    python manage.py set_logging_level DEBUG
    python manage.py set_logging_level --from-env
"""

from django.core.management.base import BaseCommand
from django.core.exceptions import ValidationError
from mgmt.models import LoggingConfig


class Command(BaseCommand):
    help = 'Set the default logging level for database storage'

    def add_arguments(self, parser):
        parser.add_argument(
            'level',
            nargs='?',
            type=str,
            choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
            help='Minimum log level to store (DEBUG, INFO, WARNING, ERROR, CRITICAL)',
        )
        parser.add_argument(
            '--from-env',
            action='store_true',
            help='Read level from LOG_DB_DEBUG environment variable (True=DEBUG, False=WARNING)',
        )
        parser.add_argument(
            '--default',
            action='store_true',
            help='Set to default value (WARNING)',
        )

    def handle(self, *args, **options):
        level = options.get('level')
        from_env = options.get('from_env', False)
        default = options.get('default', False)
        
        # Get or create config
        config = LoggingConfig.get_config()
        
        # Determine the level to set
        if default:
            level_to_set = 'WARNING'
        elif from_env:
            from django.conf import settings
            log_db_debug = getattr(settings, 'LOG_DB_DEBUG', False)
            level_to_set = 'DEBUG' if log_db_debug else 'WARNING'
        elif level:
            level_to_set = level
        else:
            self.stdout.write(
                self.style.ERROR(
                    'Please provide a level, use --from-env, or use --default'
                )
            )
            return
        
        # Update the configuration
        old_level = config.min_log_level
        config.min_log_level = level_to_set
        config.save()
        
        self.stdout.write(
            self.style.SUCCESS(
                f'✓ Logging level updated: {old_level} → {level_to_set}'
            )
        )
        self.stdout.write(
            f'  Logs with level {level_to_set} or higher will now be stored in the database.'
        )
        self.stdout.write(
            self.style.NOTICE(
                '  You can change this setting in the Admin GUI at: /admin/mgmt/loggingconfig/'
            )
        )
