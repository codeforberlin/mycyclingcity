# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    run_extended_cronjob_test.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
"""
Management command to run an extended 30-minute test of the cronjob functionality.

This command simulates 30 minutes of activity with multiple players and devices,
running the cronjob every 5 minutes. Data is kept in the database for manual inspection.

Usage:
    python manage.py run_extended_cronjob_test
    python manage.py run_extended_cronjob_test --duration 30 --update-interval 30
"""

import json
import random
from django.core.management.base import BaseCommand
from django.test import Client
from django.utils import timezone
from django.urls import reverse
from django.conf import settings
from datetime import timedelta
from decimal import Decimal
from api.models import (
    Group, Player, Device, HourlyMetric, PlayerDeviceCurrentMileage
)
from api.management.commands.mcc_worker import Command as MccWorkerCommand
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Run extended 30-minute test of cronjob functionality with multiple players and devices'

    def add_arguments(self, parser):
        parser.add_argument(
            '--duration',
            type=int,
            default=30,
            help='Test duration in minutes (default: 30)',
        )
        parser.add_argument(
            '--update-interval',
            type=int,
            default=30,
            help='Update interval in seconds (default: 30)',
        )
        parser.add_argument(
            '--players',
            type=int,
            default=5,
            help='Number of players to create (default: 5)',
        )
        parser.add_argument(
            '--devices',
            type=int,
            default=3,
            help='Number of devices to create (default: 3)',
        )
        parser.add_argument(
            '--cleanup',
            action='store_true',
            help='Clean up test data after completion (default: keep data)',
        )

    def handle(self, *args, **options):
        duration_minutes = options['duration']
        update_interval_seconds = options['update_interval']
        num_players = options['players']
        num_devices = options['devices']
        cleanup = options['cleanup']
        
        self.stdout.write(self.style.NOTICE(f"\n{'='*80}"))
        self.stdout.write(self.style.NOTICE(f"Starting extended {duration_minutes}-minute cronjob test"))
        self.stdout.write(self.style.NOTICE(f"{'='*80}"))
        
        # Clean up existing test data first (sessions and metrics)
        self.stdout.write("Cleaning up existing test sessions and metrics...")
        existing_players = Player.objects.filter(user_id__startswith='extended-test')
        existing_devices = Device.objects.filter(name__startswith='extended-test')
        if existing_players.exists() or existing_devices.exists():
            HourlyMetric.objects.filter(player__in=existing_players).delete()
            HourlyMetric.objects.filter(device__in=existing_devices).delete()
            PlayerDeviceCurrentMileage.objects.filter(player__in=existing_players).delete()
            self.stdout.write("  Cleaned up existing sessions and metrics")
        
        # Create test data
        self.stdout.write("Creating test data...")
        groups = self._create_groups()
        players = self._create_players(num_players, groups)
        devices = self._create_devices(num_devices)
        
        self.stdout.write(self.style.SUCCESS(f"Created {len(players)} players, {len(devices)} devices, {len(groups)} groups"))
        
        # Initialize statistics
        stats = {
            'total_updates': 0,
            'cronjob_runs': 0,
            'sessions_cleaned': 0,
            'start_time': timezone.now()
        }
        
        # Get API key
        api_key = getattr(settings, 'MCC_APP_API_KEY', 'MCC-APP-API-KEY-SECRET')
        client = Client()
        worker_cmd = MccWorkerCommand()
        
        # Calculate iterations
        total_iterations = (duration_minutes * 60) // update_interval_seconds
        cronjob_interval_iterations = (5 * 60) // update_interval_seconds  # Every 5 minutes
        
        self.stdout.write(f"\nConfiguration:")
        self.stdout.write(f"  Duration: {duration_minutes} minutes")
        self.stdout.write(f"  Update interval: {update_interval_seconds} seconds")
        self.stdout.write(f"  Total iterations: {total_iterations}")
        self.stdout.write(f"  Cronjob runs: {duration_minutes // 5}")
        self.stdout.write(f"\nStarting test run...\n")
        
        start_time = timezone.now()
        
        # Run test iterations
        for iteration in range(total_iterations):
            # Select random player and device
            player = random.choice(players)
            device = random.choice(devices)
            
            # Generate random distance (0.05 to 0.25 km per update)
            distance = Decimal(str(round(random.uniform(0.05, 0.25), 2)))
            
            # Send update data
            success = self._send_update_data(client, api_key, player, device, distance)
            
            if success:
                stats['total_updates'] += 1
            
            # Run cronjob every 5 minutes
            if (iteration + 1) % cronjob_interval_iterations == 0:
                elapsed_minutes = ((iteration + 1) * update_interval_seconds) // 60
                
                # Save active sessions to history
                worker_cmd.save_active_sessions_to_history()
                
                # Cleanup expired sessions
                expired_before = PlayerDeviceCurrentMileage.objects.count()
                worker_cmd.cleanup_expired_sessions()
                expired_after = PlayerDeviceCurrentMileage.objects.count()
                stats['sessions_cleaned'] += (expired_before - expired_after)
                
                stats['cronjob_runs'] += 1
                
                self.stdout.write(
                    f"[{elapsed_minutes:2d} min] Cronjob run #{stats['cronjob_runs']}: "
                    f"Active sessions: {PlayerDeviceCurrentMileage.objects.count()}, "
                    f"Hourly metrics: {HourlyMetric.objects.count()}, "
                    f"Updates: {stats['total_updates']}"
                )
                self.stdout.flush()  # Ensure output is written immediately
            
            # Wait for the update interval (except after the last iteration)
            if iteration < total_iterations - 1:
                import time
                time.sleep(update_interval_seconds)
        
        # Final cronjob run - save all active sessions and clean them up
        self.stdout.write("\nRunning final cronjob...")
        worker_cmd.save_active_sessions_to_history()
        
        # Force cleanup of ALL remaining sessions (not just expired ones)
        # This ensures no sessions remain after test completion
        all_sessions_before = PlayerDeviceCurrentMileage.objects.count()
        
        # First try normal cleanup
        worker_cmd.cleanup_expired_sessions()
        
        # If there are still active sessions, force save and delete them
        # This handles the case where sessions are still active (not expired) at test end
        remaining_sessions = PlayerDeviceCurrentMileage.objects.filter(
            player__in=players  # Only cleanup test sessions
        )
        if remaining_sessions.exists():
            self.stdout.write(f"  Saving and cleaning up {remaining_sessions.count()} remaining active session(s)...")
            for sess in remaining_sessions:
                # Save session to HourlyMetric before deleting
                if sess.cumulative_mileage and sess.cumulative_mileage > 0:
                    primary_group = sess.player.groups.first()
                    hour_timestamp = sess.last_activity.replace(minute=0, second=0, microsecond=0)
                    
                    metric, created = HourlyMetric.objects.get_or_create(
                        player=sess.player,
                        device=sess.device,
                        timestamp=hour_timestamp,
                        defaults={
                            'distance_km': sess.cumulative_mileage,
                            'group_at_time': primary_group
                        }
                    )
                    
                    if not created:
                        metric.distance_km += sess.cumulative_mileage
                        if metric.group_at_time != primary_group:
                            metric.group_at_time = primary_group
                        metric.save()
                        self.stdout.write(f"  → Updated HourlyMetric for {sess.player.user_id} on {sess.device.name}: {sess.cumulative_mileage} km")
                    else:
                        self.stdout.write(f"  → Created HourlyMetric for {sess.player.user_id} on {sess.device.name}: {sess.cumulative_mileage} km")
            
            # Delete all remaining sessions
            remaining_sessions.delete()
            self.stdout.write(f"  → Deleted {all_sessions_before} remaining session(s)")
        
        expired_after = PlayerDeviceCurrentMileage.objects.count()
        stats['sessions_cleaned'] += (all_sessions_before - expired_after)
        
        # Calculate final statistics
        end_time = timezone.now()
        duration = end_time - start_time
        
        active_sessions = PlayerDeviceCurrentMileage.objects.count()
        hourly_metrics = HourlyMetric.objects.count()
        total_player_distance = sum(float(p.distance_total) for p in players)
        total_device_distance = sum(float(d.distance_total) for d in devices)
        total_group_distance = sum(float(g.distance_total) for g in groups)
        
        # Print final report
        self.stdout.write(f"\n{'='*80}")
        self.stdout.write(self.style.SUCCESS("Test completed successfully!"))
        self.stdout.write(f"{'='*80}")
        self.stdout.write(f"Duration: {duration}")
        self.stdout.write(f"Total API updates: {stats['total_updates']}")
        self.stdout.write(f"Cronjob runs: {stats['cronjob_runs']}")
        self.stdout.write(f"Sessions cleaned: {stats['sessions_cleaned']}")
        self.stdout.write(f"\nFinal state:")
        self.stdout.write(f"  Active sessions: {active_sessions}")
        self.stdout.write(f"  Hourly metrics: {hourly_metrics}")
        self.stdout.write(f"  Total player distance: {total_player_distance:.2f} km")
        self.stdout.write(f"  Total device distance: {total_device_distance:.2f} km")
        self.stdout.write(f"  Total group distance: {total_group_distance:.2f} km")
        
        self.stdout.write(f"\nPlayer details:")
        for player in players:
            sessions = PlayerDeviceCurrentMileage.objects.filter(player=player)
            metrics = HourlyMetric.objects.filter(player=player)
            self.stdout.write(
                f"  {player.user_id}: {float(player.distance_total):.2f} km, "
                f"{sessions.count()} active sessions, {metrics.count()} hourly metrics"
            )
        
        self.stdout.write(f"\nDevice details:")
        for device in devices:
            sessions = PlayerDeviceCurrentMileage.objects.filter(device=device)
            metrics = HourlyMetric.objects.filter(device=device)
            self.stdout.write(
                f"  {device.name}: {float(device.distance_total):.2f} km, "
                f"{sessions.count()} active sessions, {metrics.count()} hourly metrics"
            )
        
        self.stdout.write(f"\nGroup details:")
        for group in groups:
            self.stdout.write(f"  {group.name}: {float(group.distance_total):.2f} km")
        
        self.stdout.write(f"\nHourly metrics by hour:")
        for metric in HourlyMetric.objects.order_by('timestamp', 'player', 'device'):
            self.stdout.write(
                f"  {metric.timestamp} | {metric.player.user_id if metric.player else 'N/A'} | "
                f"{metric.device.name} | {float(metric.distance_km):.2f} km"
            )
        
        self.stdout.write(f"{'='*80}\n")
        
        if not cleanup:
            self.stdout.write(self.style.WARNING(
                "Test data has been kept in the database for manual inspection."
            ))
            self.stdout.write(self.style.WARNING(
                "Use --cleanup flag to remove test data after completion."
            ))
        else:
            self.stdout.write("Cleaning up test data...")
            self._cleanup_test_data(players, devices, groups)
            self.stdout.write(self.style.SUCCESS("Test data cleaned up."))
    
    def _create_groups(self):
        """Create test groups. Reuse existing groups if they exist."""
        groups = []
        for i in range(1, 3):
            group, created = Group.objects.get_or_create(
                name=f'ExtendedTestGroup{i}',
                defaults={'distance_total': Decimal('0.00000')}
            )
            if not created:
                # Reset distance for existing group
                group.distance_total = Decimal('0.00000')
                group.save()
            groups.append(group)
        return groups
    
    def _create_players(self, num_players, groups):
        """Create test players. Reuse existing players if they exist."""
        players = []
        for i in range(1, num_players + 1):
            player, created = Player.objects.get_or_create(
                id_tag=f'extended-test-tag-{i:02d}',
                defaults={
                    'user_id': f'extended-test-player{i}',
                    'distance_total': Decimal('0.00000'),
                    'is_km_collection_enabled': True
                }
            )
            if not created:
                # Reset distance for existing player
                player.distance_total = Decimal('0.00000')
                player.user_id = f'extended-test-player{i}'
                player.is_km_collection_enabled = True
                player.save()
            # Clear existing group assignments and assign to groups alternately
            player.groups.clear()
            group = groups[i % len(groups)]
            player.groups.add(group)
            players.append(player)
        return players
    
    def _create_devices(self, num_devices):
        """Create test devices. Reuse existing devices if they exist."""
        devices = []
        for i in range(1, num_devices + 1):
            device, created = Device.objects.get_or_create(
                name=f'extended-test-device-{i:02d}',
                defaults={
                    'distance_total': Decimal('0.00000'),
                    'is_km_collection_enabled': True
                }
            )
            if not created:
                # Reset distance for existing device
                device.distance_total = Decimal('0.00000')
                device.is_km_collection_enabled = True
                device.save()
            devices.append(device)
        return devices
    
    def _send_update_data(self, client, api_key, player, device, distance):
        """Send update-data API request."""
        try:
            url = reverse('update_data')
            response = client.post(
                url,
                data=json.dumps({
                    'id_tag': player.id_tag,
                    'device_id': device.name,
                    'distance': str(distance)
                }),
                content_type='application/json',
                HTTP_X_API_KEY=api_key
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Error sending update data: {e}")
            return False
    
    def _cleanup_test_data(self, players, devices, groups):
        """Clean up test data."""
        # Delete hourly metrics
        HourlyMetric.objects.filter(player__in=players).delete()
        HourlyMetric.objects.filter(device__in=devices).delete()
        
        # Delete sessions
        PlayerDeviceCurrentMileage.objects.filter(player__in=players).delete()
        
        # Delete players
        for player in players:
            player.delete()
        
        # Delete devices
        for device in devices:
            device.delete()
        
        # Delete groups
        for group in groups:
            group.delete()

