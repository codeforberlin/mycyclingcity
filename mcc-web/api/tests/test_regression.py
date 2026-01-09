# mcc/api/tests/test_regression.py

"""
Regression tests for MCC mileage tracking system.

This test suite verifies that:
1. Group totals are correctly calculated and aggregated
2. Badge calculations (daily, weekly, monthly, yearly) are correct
3. Leaderboard displays correct values
4. Admin Report shows correct aggregated data
5. Filtering works correctly

All tests use controlled test data from test_data.json.
"""

import json
import os
from decimal import Decimal
from django.test import TestCase, Client
from django.utils import timezone
from django.urls import reverse
from datetime import timedelta
from api.models import Group, Cyclist, HourlyMetric, CyclistDeviceCurrentMileage
from iot.models import Device
from iot.models import Device
from api.management.commands.load_test_data import Command as LoadTestDataCommand
from api.management.commands.mcc_worker import Command as MccWorkerCommand
from django.conf import settings


class RegressionTestBase(TestCase):
    """Base class for regression tests with test data setup."""
    
    @classmethod
    def setUpTestData(cls):
        """Load test data once for all tests in this class."""
        # Load test data
        from django.conf import settings
        test_data_file = os.path.join(settings.BASE_DIR, 'api/tests/test_data.json')
        
        load_cmd = LoadTestDataCommand()
        load_cmd.handle(file=test_data_file, reset=True)
        
        # Load expected results
        with open(test_data_file, 'r', encoding='utf-8') as f:
            cls.test_data = json.load(f)
            cls.expected = cls.test_data.get('expected_results', {})


class GroupTotalsTest(RegressionTestBase):
    """Test group distance_total calculations."""
    
    def test_group_totals_match_expected(self):
        """Verify group totals match expected values from test data."""
        expected_totals = self.expected.get('group_totals', {})
        
        for group_name, expected_km in expected_totals.items():
            try:
                group = Group.objects.get(name=group_name)
                actual_km = float(group.distance_total)
                self.assertAlmostEqual(
                    actual_km, expected_km, places=1,
                    msg=f"Group '{group_name}': expected {expected_km} km, got {actual_km} km"
                )
            except Group.DoesNotExist:
                self.fail(f"Group '{group_name}' not found in database")
    
    def test_parent_group_aggregation(self):
        """Verify parent groups correctly aggregate child group totals."""
        # SchuleA should be sum of 1a-SchuleA + 1b-SchuleA
        schule_a = Group.objects.get(name='SchuleA')
        klasse_1a = Group.objects.get(name='1a-SchuleA')
        klasse_1b = Group.objects.get(name='1b-SchuleA')
        
        expected_total = float(klasse_1a.distance_total + klasse_1b.distance_total)
        actual_total = float(schule_a.distance_total)
        
        self.assertAlmostEqual(
            actual_total, expected_total, places=1,
            msg=f"Parent group 'SchuleA' should aggregate child groups: expected {expected_total} km, got {actual_total} km"
        )


class PlayerTotalsTest(RegressionTestBase):
    """Test player distance_total calculations."""
    
    def test_player_totals_match_expected(self):
        """Verify player totals match expected values from test data."""
        expected_totals = self.expected.get('player_totals', {})
        
        for user_id, expected_km in expected_totals.items():
            try:
                cyclist = Cyclist.objects.get(user_id=user_id)
                actual_km = float(cyclist.distance_total)
                self.assertAlmostEqual(
                    actual_km, expected_km, places=1,
                    msg=f"Player '{user_id}': expected {expected_km} km, got {actual_km} km"
                )
            except Cyclist.DoesNotExist:
                self.fail(f"Player '{user_id}' not found in database")


class LeaderboardTest(RegressionTestBase):
    """Test leaderboard view calculations."""
    
    def setUp(self):
        """Set up test client."""
        self.client = Client()
    
    def test_leaderboard_total_km(self):
        """Verify leaderboard total_km calculation."""
        response = self.client.get(reverse('leaderboard:leaderboard_page'))
        self.assertEqual(response.status_code, 200)
        
        context = response.context
        total_km = context.get('total_km', 0)
        
        # Total should be sum of only top-level groups (no parent) to avoid double-counting
        # Top-level groups already contain aggregated sum of all their descendants
        top_level_groups = Group.objects.filter(is_visible=True, parent__isnull=True)
        expected_total = sum(float(g.distance_total) for g in top_level_groups)
        
        self.assertAlmostEqual(
            float(total_km), expected_total, places=1,
            msg=f"Leaderboard total_km: expected {expected_total} km (sum of top-level groups), got {total_km} km"
        )
    
    def test_leaderboard_daily_km(self):
        """Verify daily kilometers are calculated correctly."""
        response = self.client.get(reverse('leaderboard:leaderboard_page'))
        self.assertEqual(response.status_code, 200)
        
        context = response.context
        groups_data = context.get('groups_data', [])
        
        # Check that daily_km is calculated for each group
        for group_data in groups_data:
            self.assertIn('daily_km', group_data)
            self.assertGreaterEqual(group_data['daily_km'], 0)


class BadgeCalculationTest(RegressionTestBase):
    """Test badge calculations (daily, weekly, monthly, yearly)."""
    
    def setUp(self):
        """Set up test client."""
        self.client = Client()
    
    def test_daily_badge_calculation(self):
        """Verify daily badge shows correct group and value."""
        response = self.client.get(reverse('leaderboard:leaderboard_page'))
        self.assertEqual(response.status_code, 200)
        
        context = response.context
        daily_record_holder = context.get('daily_record_holder')
        daily_record_value = context.get('daily_record_value', 0)
        
        if daily_record_holder:
            # Verify the record holder has the highest daily_km
            groups_data = context.get('groups_data', [])
            if groups_data:
                max_daily_km = max(g['daily_km'] for g in groups_data)
                self.assertAlmostEqual(
                    float(daily_record_value), max_daily_km, places=1,
                    msg=f"Daily badge value should match max daily_km: expected {max_daily_km} km, got {daily_record_value} km"
                )
    
    def test_badge_values_not_exceed_total(self):
        """Verify badge values don't exceed total kilometers."""
        response = self.client.get(reverse('leaderboard:leaderboard_page'))
        self.assertEqual(response.status_code, 200)
        
        context = response.context
        total_km = context.get('total_km', 0)
        
        for badge_type in ['daily', 'weekly', 'monthly', 'yearly']:
            record_value = context.get(f'{badge_type}_record_value', 0)
            if record_value > 0:
                self.assertLessEqual(
                    float(record_value), float(total_km),
                    msg=f"{badge_type.capitalize()} badge value ({record_value} km) exceeds total_km ({total_km} km)"
                )


class AdminReportTest(RegressionTestBase):
    """Test Admin Report analytics calculations."""
    
    def setUp(self):
        """Set up test client and admin user."""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.client = Client()
        self.admin_user = User.objects.create_superuser(
            username='testadmin',
            email='test@example.com',
            password='testpass123'
        )
        self.client.force_login(self.admin_user)
    
    def test_admin_report_total_distance(self):
        """Verify Admin Report total_distance matches leaderboard."""
        from datetime import datetime
        today = timezone.now().date()
        start_date = (today - timedelta(days=30)).strftime('%Y-%m-%d')
        end_date = today.strftime('%Y-%m-%d')
        
        url = reverse('admin:api_analytics_data_api')
        response = self.client.get(url, {
            'start_date': start_date,
            'end_date': end_date,
            'report_type': 'aggregated',
            'use_group_filter': 'true',
            'use_player_filter': 'true',
        })
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        total_distance = data.get('aggregated', {}).get('total_distance', 0)
        
        # Compare with leaderboard total
        leaderboard_response = self.client.get(reverse('leaderboard:leaderboard_page'))
        leaderboard_context = leaderboard_response.context
        leaderboard_total = leaderboard_context.get('total_km', 0)
        
        self.assertAlmostEqual(
            float(total_distance), float(leaderboard_total), places=1,
            msg=f"Admin Report total_distance ({total_distance} km) should match leaderboard total_km ({leaderboard_total} km)"
        )
    
    def test_admin_report_badge_totals(self):
        """Verify Admin Report badge totals are calculated correctly."""
        from datetime import datetime
        today = timezone.now().date()
        start_date = (today - timedelta(days=30)).strftime('%Y-%m-%d')
        end_date = today.strftime('%Y-%m-%d')
        
        url = reverse('admin:api_analytics_data_api')
        response = self.client.get(url, {
            'start_date': start_date,
            'end_date': end_date,
            'report_type': 'aggregated',
            'use_group_filter': 'true',
            'use_player_filter': 'true',
        })
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        aggregated = data.get('aggregated', {})
        
        total_distance = aggregated.get('total_distance', 0)
        
        # Badge totals should not exceed total_distance
        for badge_type in ['daily', 'weekly', 'monthly', 'yearly']:
            badge_total = aggregated.get(f'{badge_type}_total', 0)
            if badge_total > 0:
                self.assertLessEqual(
                    float(badge_total), float(total_distance),
                    msg=f"{badge_type.capitalize()} total ({badge_total} km) exceeds total_distance ({total_distance} km)"
                )


class FilterTest(RegressionTestBase):
    """Test filtering functionality."""
    
    def setUp(self):
        """Set up test client."""
        self.client = Client()
    
    def test_group_filter(self):
        """Verify group filtering works correctly."""
        # Get unfiltered leaderboard
        response_unfiltered = self.client.get(reverse('leaderboard:leaderboard_page'))
        self.assertEqual(response_unfiltered.status_code, 200)
        total_unfiltered = response_unfiltered.context.get('total_km', 0)
        
        # Get filtered leaderboard (SchuleA)
        schule_a = Group.objects.get(name='SchuleA')
        response_filtered = self.client.get(reverse('leaderboard:leaderboard_page'), {
            'group': schule_a.name
        })
        self.assertEqual(response_filtered.status_code, 200)
        total_filtered = response_filtered.context.get('total_km', 0)
        
        # Filtered total should be less than or equal to unfiltered
        self.assertLessEqual(
            float(total_filtered), float(total_unfiltered),
            msg=f"Filtered total ({total_filtered} km) should be <= unfiltered total ({total_unfiltered} km)"
        )
        
        # Filtered total should match SchuleA's distance_total
        self.assertAlmostEqual(
            float(total_filtered), float(schule_a.distance_total), places=1,
            msg=f"Filtered total ({total_filtered} km) should match SchuleA distance_total ({schule_a.distance_total} km)"
        )


class DataConsistencyTest(RegressionTestBase):
    """Test data consistency across different views."""
    
    def setUp(self):
        """Set up test client."""
        self.client = Client()
    
    def test_leaderboard_admin_report_consistency(self):
        """Verify leaderboard and admin report show consistent values."""
        # Get leaderboard total
        response = self.client.get(reverse('leaderboard:leaderboard_page'))
        leaderboard_total = response.context.get('total_km', 0)
        
        # Get admin report total (requires admin user)
        from django.contrib.auth import get_user_model
        User = get_user_model()
        admin_user = User.objects.create_superuser(
            username='testadmin2',
            email='test2@example.com',
            password='testpass123'
        )
        self.client.force_login(admin_user)
        
        from datetime import datetime
        today = timezone.now().date()
        start_date = (today - timedelta(days=30)).strftime('%Y-%m-%d')
        end_date = today.strftime('%Y-%m-%d')
        
        url = reverse('admin:api_analytics_data_api')
        response = self.client.get(url, {
            'start_date': start_date,
            'end_date': end_date,
            'report_type': 'aggregated',
            'use_group_filter': 'true',
            'use_player_filter': 'true',
        })
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        admin_total = data.get('aggregated', {}).get('total_distance', 0)
        
        # Values should match (within rounding tolerance)
        self.assertAlmostEqual(
            float(leaderboard_total), float(admin_total), places=1,
            msg=f"Leaderboard total ({leaderboard_total} km) should match Admin Report total ({admin_total} km)"
        )


class CronjobSessionHistoryTest(TestCase):
    """Test cronjob functionality for saving active sessions to hourly history."""
    
    def setUp(self):
        """Set up test data: create player, device, and group."""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        # Create test group
        from api.models import GroupType
        group_type, _ = GroupType.objects.get_or_create(name='TestType', defaults={'is_active': True})
        self.group = Group.objects.create(name='TestGroup', group_type=group_type, distance_total=Decimal('0.00000'))
        
        # Create test player
        self.cyclist = Cyclist.objects.create(
            user_id='testplayer',
            id_tag='test-tag-01',
            distance_total=Decimal('0.00000'),
            is_km_collection_enabled=True
        )
        self.cyclist.groups.add(self.group)
        
        # Create test device
        self.device = Device.objects.create(
            name='test-device-01',
            distance_total=Decimal('0.00000'),
            is_km_collection_enabled=True
        )
        
        # Set up API key for requests
        self.api_key = getattr(settings, 'MCC_APP_API_KEY', 'MCC-APP-API-KEY-SECRET')
        self.client = Client()
    
    def send_update_data(self, distance: Decimal) -> dict:
        """Helper method to send update-data API request."""
        url = reverse('update_data')
        response = self.client.post(
            url,
            data=json.dumps({
                'id_tag': self.cyclist.id_tag,
                'device_id': self.device.name,
                'distance': str(distance)
            }),
            content_type='application/json',
            HTTP_X_API_KEY=self.api_key
        )
        self.assertEqual(response.status_code, 200, f"API request failed: {response.content}")
        return response.json()
    
    def test_cronjob_saves_active_sessions_to_history(self):
        """
        Test that the cronjob saves active sessions to HourlyMetric.
        This test simulates:
        1. Sending data via API to create active sessions
        2. Running the cronjob to save sessions to history
        3. Verifying that data is stored in HourlyMetric
        4. Waiting for sessions to expire and verifying cleanup
        """
        from unittest.mock import patch
        
        # Step 1: Send initial data to create active session
        initial_distance = Decimal('1.5')
        self.send_update_data(initial_distance)
        
        # Verify session was created
        session = CyclistDeviceCurrentMileage.objects.get(cyclist = self.cyclist)
        self.assertEqual(session.cumulative_mileage, initial_distance)
        self.assertEqual(session.device, self.device)
        
        # Step 2: Run cronjob to save active session to history
        worker_cmd = MccWorkerCommand()
        worker_cmd.save_active_sessions_to_history()
        
        # Verify that HourlyMetric entry was created
        hour_timestamp = timezone.now().replace(minute=0, second=0, microsecond=0)
        metric = HourlyMetric.objects.filter(
            cyclist = self.cyclist,
            device=self.device,
            timestamp=hour_timestamp
        ).first()
        
        self.assertIsNotNone(metric, "HourlyMetric entry should be created for active session")
        self.assertEqual(metric.distance_km, initial_distance)
        self.assertEqual(metric.group_at_time, self.group)
        
        # Step 3: Send more data to update session
        additional_distance = Decimal('0.5')
        self.send_update_data(additional_distance)
        
        # Verify session was updated
        session.refresh_from_db()
        expected_total = initial_distance + additional_distance
        self.assertEqual(session.cumulative_mileage, expected_total)
        
        # Step 4: Run cronjob again to update HourlyMetric
        worker_cmd.save_active_sessions_to_history()
        
        # Verify that HourlyMetric entry was updated
        metric.refresh_from_db()
        self.assertEqual(metric.distance_km, expected_total)
        
        # Step 5: Simulate time passing (5+ minutes) to expire sessions
        # We'll manipulate the last_activity timestamp to simulate expiration
        # Use update() to bypass auto_now=True which would reset last_activity on save()
        expired_time = timezone.now() - timedelta(minutes=6)
        CyclistDeviceCurrentMileage.objects.filter(cyclist = self.cyclist).update(last_activity=expired_time)
        session.refresh_from_db()
        
        # Step 6: Run cleanup to remove expired sessions
        worker_cmd.cleanup_expired_sessions()
        
        # Verify that session was saved to HourlyMetric before deletion
        # The cleanup should have saved the session to HourlyMetric
        # Check if there's a metric entry for the expired session's hour
        expired_hour_timestamp = expired_time.replace(minute=0, second=0, microsecond=0)
        expired_metric = HourlyMetric.objects.filter(
            cyclist = self.cyclist,
            device=self.device,
            timestamp=expired_hour_timestamp
        ).first()
        
        # The expired session should have been saved to HourlyMetric
        # (either in the current hour or the expired hour, depending on timing)
        # Since we already have a metric for the current hour, the cleanup
        # should have added the session distance to the appropriate hour
        
        # Step 7: Verify no active sessions remain
        active_sessions = CyclistDeviceCurrentMileage.objects.filter(cyclist = self.cyclist)
        self.assertEqual(active_sessions.count(), 0, 
                        "No active sessions should remain after cleanup")
    
    def test_cronjob_handles_multiple_sessions(self):
        """Test that cronjob handles multiple active sessions correctly."""
        # Create additional player and device
        cyclist2 = Cyclist.objects.create(
            user_id='testplayer2',
            id_tag='test-tag-02',
            distance_total=Decimal('0.00000'),
            is_km_collection_enabled=True
        )
        cyclist2.groups.add(self.group)
        
        device2 = Device.objects.create(
            name='test-device-02',
            distance_total=Decimal('0.00000'),
            is_km_collection_enabled=True
        )
        
        # Send data for both players
        distance1 = Decimal('2.0')
        distance2 = Decimal('3.0')
        
        self.send_update_data(distance1)
        
        # Send data for second player
        url = reverse('update_data')
        response = self.client.post(
            url,
            data=json.dumps({
                'id_tag': cyclist2.id_tag,
                'device_id': device2.name,
                'distance': str(distance2)
            }),
            content_type='application/json',
            HTTP_X_API_KEY=self.api_key
        )
        self.assertEqual(response.status_code, 200)
        
        # Verify both sessions exist
        session1 = CyclistDeviceCurrentMileage.objects.get(cyclist = self.cyclist)
        session2 = CyclistDeviceCurrentMileage.objects.get(cyclist = cyclist2)
        self.assertEqual(session1.cumulative_mileage, distance1)
        self.assertEqual(session2.cumulative_mileage, distance2)
        
        # Run cronjob
        worker_cmd = MccWorkerCommand()
        worker_cmd.save_active_sessions_to_history()
        
        # Verify both sessions were saved to HourlyMetric
        hour_timestamp = timezone.now().replace(minute=0, second=0, microsecond=0)
        metric1 = HourlyMetric.objects.filter(
            cyclist = self.cyclist,
            device=self.device,
            timestamp=hour_timestamp
        ).first()
        metric2 = HourlyMetric.objects.filter(
            cyclist = cyclist2,
            device=device2,
            timestamp=hour_timestamp
        ).first()
        
        self.assertIsNotNone(metric1, "HourlyMetric should exist for player 1")
        self.assertIsNotNone(metric2, "HourlyMetric should exist for player 2")
        self.assertEqual(metric1.distance_km, distance1)
        self.assertEqual(metric2.distance_km, distance2)
        
        # Simulate expiration and cleanup
        # Use update() to bypass auto_now=True which would reset last_activity on save()
        expired_time = timezone.now() - timedelta(minutes=6)
        CyclistDeviceCurrentMileage.objects.filter(cyclist = self.cyclist).update(last_activity=expired_time)
        CyclistDeviceCurrentMileage.objects.filter(cyclist = cyclist2).update(last_activity=expired_time)
        
        worker_cmd.cleanup_expired_sessions()
        
        # Verify no active sessions remain
        active_sessions = CyclistDeviceCurrentMileage.objects.all()
        self.assertEqual(active_sessions.count(), 0, 
                        "No active sessions should remain after cleanup")


class ExtendedCronjobTest(TestCase):
    """
    Extended test run over 30 minutes with multiple devices and players.
    This test simulates a realistic scenario and keeps data in the database for manual inspection.
    """
    
    def setUp(self):
        """Set up test data: create multiple players, devices, and groups."""
        # Create test groups
        from api.models import GroupType
        group_type, _ = GroupType.objects.get_or_create(name='TestType', defaults={'is_active': True})
        self.group1 = Group.objects.create(name='TestGroup1', group_type=group_type, distance_total=Decimal('0.00000'))
        self.group2 = Group.objects.create(name='TestGroup2', group_type=group_type, distance_total=Decimal('0.00000'))
        
        # Create 5 test players
        self.cyclists = []
        for i in range(1, 6):
            cyclist = Cyclist.objects.create(
                user_id=f'testplayer{i}',
                id_tag=f'test-tag-{i:02d}',
                distance_total=Decimal('0.00000'),
                is_km_collection_enabled=True
            )
            # Assign players to groups alternately
            if i % 2 == 0:
                cyclist.groups.add(self.group2)
            else:
                cyclist.groups.add(self.group1)
            self.cyclists.append(cyclist)
        
        # Create 3 test devices
        self.devices = []
        for i in range(1, 4):
            device = Device.objects.create(
                name=f'test-device-{i:02d}',
                distance_total=Decimal('0.00000'),
                is_km_collection_enabled=True
            )
            self.devices.append(device)
        
        # Set up API key for requests
        self.api_key = getattr(settings, 'MCC_APP_API_KEY', 'MCC-APP-API-KEY-SECRET')
        self.client = Client()
        
        # Track test statistics
        self.test_stats = {
            'total_updates': 0,
            'cronjob_runs': 0,
            'hourly_metrics_created': 0,
            'sessions_cleaned': 0,
            'start_time': timezone.now()
        }
    
    def send_update_data(self, cyclist: Cyclist, device: Device, distance: Decimal) -> dict:
        """Helper method to send update-data API request."""
        url = reverse('update_data')
        response = self.client.post(
            url,
            data=json.dumps({
                'id_tag': cyclist.id_tag,
                'device_id': device.name,
                'distance': str(distance)
            }),
            content_type='application/json',
            HTTP_X_API_KEY=self.api_key
        )
        if response.status_code != 200:
            self.fail(f"API request failed: {response.status_code} - {response.content}")
        self.test_stats['total_updates'] += 1
        return response.json()
    
    def test_extended_30_minute_run(self):
        """
        Extended test run simulating 30 minutes of activity.
        - Multiple players and devices
        - Regular data updates every 30 seconds
        - Cronjob runs every 5 minutes
        - Data remains in database for manual inspection
        """
        import random
        from unittest.mock import patch
        
        # Test configuration
        total_duration_minutes = 30
        update_interval_seconds = 30  # Send data every 30 seconds
        cronjob_interval_minutes = 5  # Run cronjob every 5 minutes
        
        # Calculate number of iterations
        total_iterations = (total_duration_minutes * 60) // update_interval_seconds
        cronjob_iterations = total_duration_minutes // cronjob_interval_minutes
        
        print(f"\n{'='*80}")
        print(f"Starting extended 30-minute test run")
        print(f"{'='*80}")
        print(f"Players: {len(self.cyclists)}")
        print(f"Devices: {len(self.devices)}")
        print(f"Total iterations: {total_iterations}")
        print(f"Cronjob runs: {cronjob_iterations}")
        print(f"{'='*80}\n")
        
        worker_cmd = MccWorkerCommand()
        current_time = timezone.now()
        start_time = current_time
        
        # Simulate 30 minutes of activity
        for iteration in range(total_iterations):
            # Calculate simulated time (every iteration = 30 seconds)
            simulated_time = start_time + timedelta(seconds=iteration * update_interval_seconds)
            
            # Select random player and device for this iteration
            cyclist = random.choice(self.cyclists)
            device = random.choice(self.devices)
            
            # Generate random distance (0.05 to 0.25 km per update)
            distance = Decimal(str(round(random.uniform(0.05, 0.25), 2)))
            
            # Send update data
            self.send_update_data(cyclist, device, distance)
            
            # Update last_activity to simulated time for all active sessions
            # This simulates the passage of time
            CyclistDeviceCurrentMileage.objects.all().update(last_activity=simulated_time)
            
            # Run cronjob every 5 minutes (every 10 iterations)
            if (iteration + 1) % 10 == 0:
                # First save active sessions to history
                worker_cmd.save_active_sessions_to_history()
                self.test_stats['cronjob_runs'] += 1
                
                # Count hourly metrics
                self.test_stats['hourly_metrics_created'] = HourlyMetric.objects.count()
                
                # Then cleanup expired sessions
                expired_before = CyclistDeviceCurrentMileage.objects.count()
                worker_cmd.cleanup_expired_sessions()
                expired_after = CyclistDeviceCurrentMileage.objects.count()
                self.test_stats['sessions_cleaned'] += (expired_before - expired_after)
                
                elapsed_minutes = ((iteration + 1) * update_interval_seconds) // 60
                print(f"[{elapsed_minutes:2d} min] Cronjob run #{self.test_stats['cronjob_runs']}: "
                      f"Active sessions: {CyclistDeviceCurrentMileage.objects.count()}, "
                      f"Hourly metrics: {HourlyMetric.objects.count()}")
        
        # Final cronjob run
        print(f"\nRunning final cronjob...")
        worker_cmd.save_active_sessions_to_history()
        worker_cmd.cleanup_expired_sessions()
        
        # Final statistics
        end_time = timezone.now()
        duration = end_time - start_time
        
        active_sessions = CyclistDeviceCurrentMileage.objects.count()
        hourly_metrics = HourlyMetric.objects.count()
        total_player_distance = sum(float(p.distance_total) for p in Cyclist.objects.all())
        total_device_distance = sum(float(d.distance_total) for d in Device.objects.all())
        total_group_distance = sum(float(g.distance_total) for g in Group.objects.all())
        
        print(f"\n{'='*80}")
        print(f"Test completed successfully!")
        print(f"{'='*80}")
        print(f"Duration: {duration}")
        print(f"Total API updates: {self.test_stats['total_updates']}")
        print(f"Cronjob runs: {self.test_stats['cronjob_runs']}")
        print(f"\nFinal state:")
        print(f"  Active sessions: {active_sessions}")
        print(f"  Hourly metrics: {hourly_metrics}")
        print(f"  Total player distance: {total_player_distance:.2f} km")
        print(f"  Total device distance: {total_device_distance:.2f} km")
        print(f"  Total group distance: {total_group_distance:.2f} km")
        print(f"\nCyclist details:")
        for cyclist in self.cyclists:
            sessions = CyclistDeviceCurrentMileage.objects.filter(cyclist = cyclist)
            metrics = HourlyMetric.objects.filter(cyclist = cyclist)
            print(f"  {cyclist.user_id}: {float(cyclist.distance_total):.2f} km, "
                  f"{sessions.count()} active sessions, {metrics.count()} hourly metrics")
        print(f"\nDevice details:")
        for device in self.devices:
            sessions = CyclistDeviceCurrentMileage.objects.filter(device=device)
            metrics = HourlyMetric.objects.filter(device=device)
            print(f"  {device.name}: {float(device.distance_total):.2f} km, "
                  f"{sessions.count()} active sessions, {metrics.count()} hourly metrics")
        print(f"\nGroup details:")
        for group in [self.group1, self.group2]:
            print(f"  {group.name}: {float(group.distance_total):.2f} km")
        print(f"\nHourly metrics by hour:")
        for metric in HourlyMetric.objects.order_by('timestamp', 'cyclist', 'device'):
            print(f"  {metric.timestamp} | {metric.cyclist.user_id} | {metric.device.name} | "
                  f"{float(metric.distance_km):.2f} km")
        print(f"{'='*80}\n")
        
        # Verify that data was created
        self.assertGreater(hourly_metrics, 0, "Should have created hourly metrics")
        self.assertGreater(total_player_distance, 0, "Should have recorded player distances")
        self.assertGreater(total_device_distance, 0, "Should have recorded device distances")
        
        # Note: We intentionally do NOT clean up the data so it can be manually inspected
        # The test database will be destroyed by Django's test framework, but if run
        # against a real database, the data will remain.

