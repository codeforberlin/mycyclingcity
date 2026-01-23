# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    get_gunicorn_config.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
"""
Management command to get Gunicorn configuration from database.

This command is used by the startup script to read the Gunicorn log level
from the database and export it as an environment variable.

Usage:
    python manage.py get_gunicorn_config
    python manage.py get_gunicorn_config --format=env
"""

from django.core.management.base import BaseCommand
from django.core.management import call_command
from mgmt.models import GunicornConfig
import sys


class Command(BaseCommand):
    help = 'Get Gunicorn configuration from database and output as environment variable'

    def add_arguments(self, parser):
        parser.add_argument(
            '--format',
            type=str,
            choices=['env', 'json'],
            default='env',
            help='Output format (default: env)',
        )

    def handle(self, *args, **options):
        output_format = options['format']
        
        try:
            config = GunicornConfig.get_config()
            log_level = config.log_level
            
            if output_format == 'env':
                # Output as environment variable format
                self.stdout.write(f'GUNICORN_LOG_LEVEL={log_level}')
                # Also output to stderr for shell scripts to capture
                sys.stderr.write(f'GUNICORN_LOG_LEVEL={log_level}\n')
            elif output_format == 'json':
                import json
                self.stdout.write(json.dumps({
                    'log_level': log_level,
                }))
            
            return 0
        except Exception as e:
            # If database is not available or model doesn't exist, use default
            if output_format == 'env':
                self.stdout.write('GUNICORN_LOG_LEVEL=info')
                sys.stderr.write('GUNICORN_LOG_LEVEL=info\n')
            else:
                import json
                self.stdout.write(json.dumps({
                    'log_level': 'info',
                }))
            return 0
