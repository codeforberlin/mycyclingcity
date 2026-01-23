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
            workers = config.get_workers_count()
            threads = config.threads
            worker_class = config.worker_class
            bind_address = config.bind_address
            
            if output_format == 'env':
                # Output as environment variable format
                self.stdout.write(f'GUNICORN_LOG_LEVEL={log_level}')
                self.stdout.write(f'GUNICORN_WORKERS={workers}')
                self.stdout.write(f'GUNICORN_THREADS={threads}')
                self.stdout.write(f'GUNICORN_WORKER_CLASS={worker_class}')
                self.stdout.write(f'GUNICORN_BIND={bind_address}')
                # Also output to stderr for shell scripts to capture
                sys.stderr.write(f'GUNICORN_LOG_LEVEL={log_level}\n')
                sys.stderr.write(f'GUNICORN_WORKERS={workers}\n')
                sys.stderr.write(f'GUNICORN_THREADS={threads}\n')
                sys.stderr.write(f'GUNICORN_WORKER_CLASS={worker_class}\n')
                sys.stderr.write(f'GUNICORN_BIND={bind_address}\n')
            elif output_format == 'json':
                import json
                self.stdout.write(json.dumps({
                    'log_level': log_level,
                    'workers': workers,
                    'threads': threads,
                    'worker_class': worker_class,
                    'bind_address': bind_address,
                }))
            
            return 0
        except Exception as e:
            # If database is not available or model doesn't exist, use default
            if output_format == 'env':
                self.stdout.write('GUNICORN_LOG_LEVEL=info')
                self.stdout.write('GUNICORN_WORKERS=0')
                self.stdout.write('GUNICORN_THREADS=2')
                self.stdout.write('GUNICORN_WORKER_CLASS=gthread')
                self.stdout.write('GUNICORN_BIND=127.0.0.1:8001')
                sys.stderr.write('GUNICORN_LOG_LEVEL=info\n')
                sys.stderr.write('GUNICORN_WORKERS=0\n')
                sys.stderr.write('GUNICORN_THREADS=2\n')
                sys.stderr.write('GUNICORN_WORKER_CLASS=gthread\n')
                sys.stderr.write('GUNICORN_BIND=127.0.0.1:8001\n')
            else:
                import json
                self.stdout.write(json.dumps({
                    'log_level': 'info',
                    'workers': 0,
                    'threads': 2,
                    'worker_class': 'gthread',
                    'bind_address': '127.0.0.1:8001',
                }))
            return 0
