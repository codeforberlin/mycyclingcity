# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    load_test_data.py
# @author  Roland Rutz

#
"""
Management command to load controlled test data into the database.

This command loads test data from a JSON configuration file to ensure
consistent, reproducible test scenarios for regression testing.

Usage:
    python manage.py load_test_data
    python manage.py load_test_data --file api/tests/test_data.json
    python manage.py load_test_data --reset  # Reset database first
"""

import json
import os
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from api.models import (
    Group, Cyclist, CyclistDeviceCurrentMileage, HourlyMetric, GroupType
)
from iot.models import Device, DeviceConfiguration
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Load controlled test data from JSON configuration file'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            type=str,
            default='api/tests/test_data.json',
            help='Path to test data JSON file (default: api/tests/test_data.json)',
        )
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Reset database before loading test data',
        )

    def handle(self, *args, **options):
        file_path = options['file']
        reset = options['reset']

        # Get absolute path
        if not os.path.isabs(file_path):
            from django.conf import settings
            file_path = os.path.join(settings.BASE_DIR, file_path)

        if not os.path.exists(file_path):
            self.stdout.write(self.style.ERROR(f"Test data file not found: {file_path}"))
            return

        # Load test data
        self.stdout.write(self.style.NOTICE(f"Loading test data from: {file_path}"))
        with open(file_path, 'r', encoding='utf-8') as f:
            test_data = json.load(f)

        if reset:
            self.stdout.write(self.style.WARNING("Resetting database..."))
            from api.management.commands.reset_mileage_data import Command as ResetCommand
            reset_cmd = ResetCommand()
            # Call with proper options
            reset_cmd.handle(confirm=True, include_history=False, dry_run=False)

        try:
            with transaction.atomic():
                # 0. Delete existing test data groups/players/devices if they exist
                self.stdout.write("Cleaning up existing test data...")
                test_group_ids = [g['id'] for g in test_data['groups']]
                test_group_names = [(g.get('group_type', 'Schule'), g['name']) for g in test_data['groups']]
                cyclists_data = test_data.get('cyclists', test_data.get('players', []))
                test_cyclist_ids = [p['id'] for p in cyclists_data]
                test_device_ids = [d['id'] for d in test_data['devices']]
                
                # Delete groups by ID and by name (to catch duplicates)
                Group.objects.filter(id__in=test_group_ids).delete()
                for group_type_name, name in test_group_names:
                    try:
                        group_type_obj = GroupType.objects.get(name=group_type_name, is_active=True)
                        Group.objects.filter(group_type=group_type_obj, name=name).delete()
                    except GroupType.DoesNotExist:
                        pass
                
                Cyclist.objects.filter(id__in=test_cyclist_ids).delete()
                Device.objects.filter(id__in=test_device_ids).delete()
                self.stdout.write("  ✓ Cleaned up existing test data")
                
                # 1. Create Groups
                self.stdout.write("Creating groups...")
                groups_map = {}
                for group_data in test_data['groups']:
                    parent = None
                    if group_data.get('parent'):
                        parent = groups_map.get(group_data['parent'])
                    
                    # Get or create GroupType
                    group_type_name = group_data.get('group_type', 'Schule')
                    group_type, _ = GroupType.objects.get_or_create(
                        name=group_type_name,
                        defaults={'is_active': True, 'description': f'Group type: {group_type_name}'}
                    )
                    
                    group = Group(
                        id=group_data['id'],
                        group_type=group_type,
                        name=group_data['name'],
                        short_name=group_data.get('short_name', ''),
                        is_visible=group_data.get('is_visible', True),
                        parent=parent,
                        distance_total=Decimal(str(group_data.get('distance_total', 0))),
                        coins_total=group_data.get('coins_total', 0),
                    )
                    group.save()
                    
                    groups_map[group_data['id']] = group
                    self.stdout.write(f"  ✓ Created Group: {group.name}")

                # 2. Create Cyclists
                self.stdout.write("Creating cyclists...")
                cyclists_map = {}
                cyclists_data = test_data.get('cyclists', test_data.get('players', []))
                for cyclist_data in cyclists_data:
                    cyclist, created = Cyclist.objects.get_or_create(
                        id=cyclist_data['id'],
                        defaults={
                            'user_id': cyclist_data['user_id'],
                            'id_tag': cyclist_data['id_tag'],
                            'is_visible': cyclist_data.get('is_visible', True),
                            'distance_total': Decimal(str(cyclist_data.get('distance_total', 0))),
                            'coins_total': cyclist_data.get('coins_total', 0),
                        }
                    )
                    if not created:
                        cyclist.user_id = cyclist_data['user_id']
                        cyclist.id_tag = cyclist_data['id_tag']
                        cyclist.is_visible = cyclist_data.get('is_visible', True)
                        cyclist.distance_total = Decimal(str(cyclist_data.get('distance_total', 0)))
                        cyclist.coins_total = cyclist_data.get('coins_total', 0)
                        cyclist.save()
                    
                    # Assign to groups
                    cyclist.groups.clear()
                    for group_id in cyclist_data.get('group_ids', []):
                        if group_id in groups_map:
                            cyclist.groups.add(groups_map[group_id])
                    
                    cyclists_map[cyclist_data['id']] = cyclist
                    self.stdout.write(f"  ✓ Cyclist: {cyclist.user_id}")

                # 3. Create Devices
                self.stdout.write("Creating devices...")
                devices_map = {}
                for device_data in test_data['devices']:
                    group = groups_map.get(device_data.get('group_id'))
                    device, created = Device.objects.get_or_create(
                        id=device_data['id'],
                        defaults={
                            'name': device_data['name'],
                            'display_name': device_data.get('display_name', device_data['name']),
                            'is_visible': device_data.get('is_visible', True),
                            'group': group,
                            'distance_total': Decimal(str(device_data.get('distance_total', 0))),
                        }
                    )
                    if not created:
                        device.name = device_data['name']
                        device.display_name = device_data.get('display_name', device_data['name'])
                        device.is_visible = device_data.get('is_visible', True)
                        device.group = group
                        device.distance_total = Decimal(str(device_data.get('distance_total', 0)))
                        device.save()
                    
                    # Create DeviceConfiguration with auto-generated API key
                    config, config_created = DeviceConfiguration.objects.get_or_create(
                        device=device,
                        defaults={
                            'device_name': device.name,
                            'default_id_tag': '',
                            'send_interval_seconds': 60,
                            'debug_mode': False,
                            'test_mode': False,
                            'deep_sleep_seconds': 0,
                            'wheel_size': 26,
                        }
                    )
                    # Generate API key if not already set
                    if not config.device_specific_api_key:
                        config.generate_api_key()
                        self.stdout.write(f"  ✓ Device: {device.name} (API-Key generiert)")
                    else:
                        self.stdout.write(f"  ✓ Device: {device.name}")
                    
                    devices_map[device_data['id']] = device

                # 4. Create mileage updates
                # IMPORTANT: Cyclist.distance_total is the MASTER data source.
                # HourlyMetrics should ONLY be created from sessions when they end,
                # not directly. For test data, we simulate sessions and then save them.
                self.stdout.write("Creating mileage updates...")
                now = timezone.now()
                
                for update in test_data.get('mileage_updates', []):
                    cyclist = cyclists_map.get(update['player_id'])
                    device = devices_map.get(update['device_id'])
                    if not cyclist or not device:
                        continue
                    
                    # Calculate timestamp
                    timestamp = now + timedelta(hours=update.get('timestamp_offset_hours', 0))
                    delta_km = Decimal(str(update['distance_delta']))
                    
                    # Update cyclist, device, and group totals (MASTER DATA)
                    cyclist.distance_total += delta_km
                    cyclist.save()
                    
                    device.distance_total += delta_km
                    device.save()
                    
                    primary_group = cyclist.groups.first()
                    if primary_group:
                        primary_group.add_to_totals(delta_km, 0)
                    
                    # Create a simulated session and immediately save it to HourlyMetric
                    # This simulates the real-world flow: session -> HourlyMetric
                    # Round timestamp to the hour to aggregate metrics within the same hour
                    hour_timestamp = timestamp.replace(minute=0, second=0, microsecond=0)
                    
                    # Create/update HourlyMetric (as if session was saved)
                    metric, created = HourlyMetric.objects.get_or_create(
                        cyclist=cyclist,
                        device=device,
                        timestamp=hour_timestamp,
                        defaults={
                            'distance_km': delta_km,
                            'group_at_time': primary_group,
                        }
                    )
                    if not created:
                        # Update existing metric by adding the session kilometers
                        metric.distance_km += delta_km
                        # Update group if it changed
                        if metric.group_at_time != primary_group:
                            metric.group_at_time = primary_group
                        metric.save()
                    
                    self.stdout.write(f"  ✓ Update: {cyclist.user_id} +{update['distance_delta']} km")

            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS("=" * 60))
            self.stdout.write(self.style.SUCCESS("TEST DATA LOADED SUCCESSFULLY"))
            self.stdout.write(self.style.SUCCESS("=" * 60))
            self.stdout.write("")

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"ERROR loading test data: {e}"))
            logger.error(f"Error loading test data: {e}", exc_info=True)
            raise

