# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    load_test_leaderboards.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
"""
Load test script for testing leaderboard endpoints with real database data.

This script:
1. Loads all devices and cyclists from the database
2. Sends HTTP requests to update-data endpoints to simulate activity
3. Tests leaderboard endpoints (cyclists, groups)
4. Verifies the data is correctly displayed
5. Generates a test report

Usage:
    python test/load_test_leaderboards.py [--base-url URL] [--iterations N] [--delay SECONDS]
"""

import os
import sys
import django
import argparse
import time
import requests
import configparser
from pathlib import Path
from datetime import datetime, timedelta
from decimal import Decimal
import json

# Load environment variables from .env file (before Django setup)
try:
    from dotenv import load_dotenv
    # Load .env from /data/appl/mcc/.env (production) or project root (development)
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    
    # Try production path first
    env_path = Path('/data/appl/mcc/.env')
    if not env_path.exists():
        # Fallback to project directory (development)
        env_path = project_root / '.env'
    
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    # python-dotenv not installed, continue without it
    pass

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from api.models import Cyclist, Group
from iot.models import Device, DeviceConfiguration
from django.conf import settings
from django.utils import timezone

# Load configuration: .env takes priority, then config file
BASE_DIR = Path(__file__).parent
CONFIG_FILE = BASE_DIR / 'mcc_api_test.cfg'
DEFAULT_API_KEY = None
DEFAULT_SERVER_URL = 'http://localhost:8000'

# First try .env
DEFAULT_API_KEY = os.getenv('MCC_APP_API_KEY')
SERVER_IP = os.getenv('TEST_SERVER_IP')
SERVER_PORT = os.getenv('TEST_SERVER_PORT')

if SERVER_IP and SERVER_PORT:
    DEFAULT_SERVER_URL = f"http://{SERVER_IP}:{SERVER_PORT}"

# Fallback to config file
if CONFIG_FILE.exists():
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)
    if 'general' in config:
        GENERAL_SETTINGS = config['general']
        if not SERVER_IP:
            SERVER_IP = GENERAL_SETTINGS.get('server_ip', 'localhost')
        if not SERVER_PORT:
            SERVER_PORT = GENERAL_SETTINGS.getint('server_port', 8000)
        if not DEFAULT_API_KEY:
            DEFAULT_API_KEY = GENERAL_SETTINGS.get('api_key')
        if not DEFAULT_SERVER_URL or DEFAULT_SERVER_URL == 'http://localhost:8000':
            DEFAULT_SERVER_URL = f"http://{SERVER_IP}:{SERVER_PORT}"


class LeaderboardLoadTest:
    """Load test for leaderboard endpoints."""
    
    def __init__(self, base_url='http://localhost:8000', iterations=10, delay=1.0, show_live_leaderboard=True):
        self.base_url = base_url.rstrip('/')
        self.iterations = iterations
        self.delay = delay
        self.show_live_leaderboard = show_live_leaderboard
        self.results = {
            'start_time': datetime.now().isoformat(),
            'base_url': base_url,
            'iterations': iterations,
            'devices_tested': 0,
            'cyclists_tested': 0,
            'updates_sent': 0,
            'updates_successful': 0,
            'updates_failed': 0,
            'leaderboard_tests': [],
            'live_leaderboard_snapshots': [],
            'errors': []
        }
        
    def get_api_key(self, device=None):
        """Get API key for device or use global key."""
        if device:
            try:
                config = DeviceConfiguration.objects.get(device=device)
                if config.device_specific_api_key:
                    return config.device_specific_api_key
            except DeviceConfiguration.DoesNotExist:
                pass
        
        # For update-data endpoint, always use global API key
        # Priority: .env > config file > Django settings
        if DEFAULT_API_KEY:
            return DEFAULT_API_KEY
        api_key = getattr(settings, 'MCC_APP_API_KEY', '')
        if not api_key:
            print("⚠️  Warning: No API key found. Please set MCC_APP_API_KEY in .env file.")
        return api_key
    
    def load_devices_and_cyclists(self):
        """Load all active devices and cyclists from database."""
        devices = Device.objects.filter(
            is_visible=True,
            is_km_collection_enabled=True
        ).select_related('configuration')
        
        cyclists = Cyclist.objects.filter(
            is_visible=True,
            is_km_collection_enabled=True
        )
        
        return list(devices), list(cyclists)
    
    def send_update_data(self, device, cyclist, distance_delta, api_key):
        """Send update-data request to simulate device activity."""
        url = f"{self.base_url}/api/update-data"
        
        payload = {
            'id_tag': cyclist.id_tag,
            'device_id': device.name,
            'distance': float(distance_delta),  # API expects 'distance', not 'distance_delta'
            'timestamp': timezone.now().isoformat()
        }
        
        headers = {
            'Content-Type': 'application/json',
            'X-Api-Key': api_key
        }
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            if response.status_code == 200:
                return True, response
            else:
                # Return error details for debugging
                error_msg = f"Status {response.status_code}: {response.text[:200]}"
                return False, error_msg
        except Exception as e:
            return False, str(e)
    
    def test_leaderboard_cyclists(self, api_key, sort='total', limit=10):
        """Test get-leaderboard/cyclists endpoint."""
        url = f"{self.base_url}/api/get-leaderboard/cyclists"
        
        params = {
            'sort': sort,
            'limit': limit
        }
        
        headers = {
            'X-Api-Key': api_key
        }
        
        try:
            response = requests.get(url, params=params, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return True, data
            else:
                return False, f"Status {response.status_code}: {response.text}"
        except Exception as e:
            return False, str(e)
    
    def test_leaderboard_groups(self, api_key, sort='total', limit=10):
        """Test get-leaderboard/groups endpoint."""
        url = f"{self.base_url}/api/get-leaderboard/groups"
        
        params = {
            'sort': sort,
            'limit': limit
        }
        
        headers = {
            'X-Api-Key': api_key
        }
        
        try:
            response = requests.get(url, params=params, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return True, data
            else:
                return False, f"Status {response.status_code}: {response.text}"
        except Exception as e:
            return False, str(e)
    
    def test_get_cyclist_distance(self, cyclist, api_key):
        """Test get-cyclist-distance endpoint."""
        url = f"{self.base_url}/api/get-cyclist-distance/{cyclist.id_tag}"
        
        headers = {
            'X-Api-Key': api_key
        }
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return True, data
            else:
                return False, f"Status {response.status_code}: {response.text}"
        except Exception as e:
            return False, str(e)
    
    def test_get_group_distance(self, group, api_key):
        """Test get-group-distance endpoint."""
        url = f"{self.base_url}/api/get-group-distance/{group.id}"
        
        headers = {
            'X-Api-Key': api_key
        }
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return True, data
            else:
                return False, f"Status {response.status_code}: {response.text}"
        except Exception as e:
            return False, str(e)
    
    def get_active_cyclists(self, api_key, limit=10):
        """Get list of currently active cyclists."""
        url = f"{self.base_url}/api/get-active-cyclists"
        
        params = {
            'limit': limit
        }
        
        headers = {
            'X-Api-Key': api_key
        }
        
        try:
            response = requests.get(url, params=params, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return True, data
            else:
                return False, f"Status {response.status_code}: {response.text}"
        except Exception as e:
            return False, str(e)
    
    def display_live_leaderboard(self, api_key, iteration=None):
        """Display current leaderboard state during test run."""
        if not self.show_live_leaderboard:
            return
        
        print("\n" + "=" * 80)
        if iteration:
            print(f"📊 Live Leaderboard - Iteration {iteration}")
        else:
            print("📊 Live Leaderboard")
        print("=" * 80)
        
        # Get active cyclists
        success_active, data_active = self.get_active_cyclists(api_key, limit=10)
        if success_active and data_active.get('cyclists'):
            print(f"\n🟢 Aktive Radler ({len(data_active['cyclists'])}):")
            for i, cyclist in enumerate(data_active['cyclists'][:10], 1):
                session_km = cyclist.get('session_km', 0)
                total_km = cyclist.get('total_km', 0)
                device = cyclist.get('device_name', 'Unknown')
                print(f"  {i:2d}. {cyclist.get('user_id', 'N/A'):15s} | "
                      f"Session: {session_km:6.2f} km | "
                      f"Total: {total_km:8.2f} km | "
                      f"Device: {device}")
        else:
            print("\n⚠️  Keine aktiven Radler gefunden")
        
        # Get leaderboard cyclists (total)
        success_total, data_total = self.test_leaderboard_cyclists(api_key, sort='total', limit=5)
        if success_total and data_total.get('cyclists'):
            print(f"\n🏆 Top 5 Radler (Gesamt):")
            for i, cyclist in enumerate(data_total['cyclists'][:5], 1):
                distance = cyclist.get('distance_total', 0)
                user_id = cyclist.get('user_id', 'N/A')
                print(f"  {i}. {user_id:15s} - {distance:8.2f} km")
        
        # Get leaderboard cyclists (daily)
        success_daily, data_daily = self.test_leaderboard_cyclists(api_key, sort='daily', limit=5)
        if success_daily and data_daily.get('cyclists'):
            print(f"\n📅 Top 5 Radler (Heute):")
            for i, cyclist in enumerate(data_daily['cyclists'][:5], 1):
                distance = cyclist.get('distance_daily', 0)
                user_id = cyclist.get('user_id', 'N/A')
                print(f"  {i}. {user_id:15s} - {distance:8.2f} km")
        
        # Get leaderboard groups (total)
        success_groups, data_groups = self.test_leaderboard_groups(api_key, sort='total', limit=5)
        if success_groups and data_groups.get('leaderboard'):
            print(f"\n🏫 Top 5 Gruppen (Gesamt):")
            for i, group in enumerate(data_groups['leaderboard'][:5], 1):
                distance = group.get('distance', 0)
                name = group.get('name', 'N/A')
                print(f"  {i}. {name:30s} - {distance:8.2f} km")
        
        print("=" * 80)
        
        # Store snapshot for results
        snapshot = {
            'timestamp': datetime.now().isoformat(),
            'iteration': iteration,
            'active_cyclists': data_active.get('cyclists', []) if success_active else [],
            'top_cyclists_total': data_total.get('cyclists', []) if success_total else [],
            'top_cyclists_daily': data_daily.get('cyclists', []) if success_daily else [],
            'top_groups_total': data_groups.get('leaderboard', []) if success_groups else [],
        }
        self.results['live_leaderboard_snapshots'].append(snapshot)
    
    def run_load_test(self):
        """Run the complete load test."""
        print("=" * 80)
        print("Leaderboard Load Test")
        print("=" * 80)
        print(f"Base URL: {self.base_url}")
        print(f"Iterations: {self.iterations}")
        print(f"Delay between iterations: {self.delay}s")
        print()
        
        # Load devices and cyclists
        print("Loading devices and cyclists from database...")
        devices, cyclists = self.load_devices_and_cyclists()
        
        if not devices:
            print("ERROR: No devices found in database!")
            self.results['errors'].append("No devices found in database")
            return self.results
        
        if not cyclists:
            print("ERROR: No cyclists found in database!")
            self.results['errors'].append("No cyclists found in database")
            return self.results
        
        print(f"Found {len(devices)} devices and {len(cyclists)} cyclists")
        self.results['devices_tested'] = len(devices)
        self.results['cyclists_tested'] = len(cyclists)
        print()
        
        # Get API key (always use global key for update-data endpoint)
        api_key = self.get_api_key()
        if not api_key:
            print("ERROR: No API key available!")
            self.results['errors'].append("No API key available")
            return self.results
        
        print(f"Using API key: {api_key[:20]}...")
        print()
        
        # Run iterations
        print("Starting load test iterations...")
        print("-" * 80)
        
        for iteration in range(1, self.iterations + 1):
            print(f"\nIteration {iteration}/{self.iterations}")
            
            # Send update-data requests for random device-cyclist combinations
            import random
            updates_this_iteration = min(5, len(devices) * len(cyclists))
            
            for _ in range(updates_this_iteration):
                device = random.choice(devices)
                cyclist = random.choice(cyclists)
                distance_delta = Decimal(str(random.uniform(0.1, 5.0)))
                
                # Always use global API key for update-data endpoint
                success, response = self.send_update_data(
                    device, cyclist, distance_delta, api_key
                )
                
                self.results['updates_sent'] += 1
                if success:
                    self.results['updates_successful'] += 1
                    print(f"  ✓ Update: {device.name} -> {cyclist.user_id} (+{distance_delta} km)")
                else:
                    self.results['updates_failed'] += 1
                    print(f"  ✗ Update failed: {device.name} -> {cyclist.user_id}")
                    self.results['errors'].append(f"Update failed: {device.name} -> {cyclist.user_id}: {response}")
            
            # Display live leaderboard after each iteration
            if self.show_live_leaderboard:
                self.display_live_leaderboard(api_key, iteration=iteration)
            
            # Wait between iterations
            if iteration < self.iterations:
                time.sleep(self.delay)
        
        # Show final leaderboard state
        if self.show_live_leaderboard:
            print("\n" + "-" * 80)
            print("Final Leaderboard State:")
            print("-" * 80)
            self.display_live_leaderboard(api_key, iteration="Final")
        
        print("\n" + "-" * 80)
        print("Testing leaderboard endpoints...")
        print("-" * 80)
        
        # Test leaderboard endpoints
        leaderboard_tests = [
            ('cyclists_total', 'total'),
            ('cyclists_daily', 'daily'),
            ('groups_total', 'total'),
            ('groups_daily', 'daily'),
        ]
        
        for test_name, sort_type in leaderboard_tests:
            print(f"\nTesting {test_name} (sort={sort_type})...")
            
            if 'cyclists' in test_name:
                success, data = self.test_leaderboard_cyclists(api_key, sort=sort_type)
            else:
                success, data = self.test_leaderboard_groups(api_key, sort=sort_type)
            
            if success:
                count = len(data.get('leaderboard', []))
                print(f"  ✓ Success: {count} entries returned")
                self.results['leaderboard_tests'].append({
                    'test': test_name,
                    'sort': sort_type,
                    'success': True,
                    'entries_count': count,
                    'data': data
                })
            else:
                print(f"  ✗ Failed: {data}")
                self.results['leaderboard_tests'].append({
                    'test': test_name,
                    'sort': sort_type,
                    'success': False,
                    'error': str(data)
                })
                self.results['errors'].append(f"{test_name} failed: {data}")
        
        # Test individual cyclist/group distances
        print("\n" + "-" * 80)
        print("Testing individual cyclist/group distance endpoints...")
        print("-" * 80)
        
        # Test a few random cyclists
        import random
        test_cyclists = random.sample(cyclists, min(3, len(cyclists)))
        for cyclist in test_cyclists:
            print(f"\nTesting cyclist distance: {cyclist.user_id} ({cyclist.id_tag})...")
            success, data = self.test_get_cyclist_distance(cyclist, api_key)
            if success:
                distance = data.get('distance_total', 0)
                print(f"  ✓ Success: Total distance = {distance} km")
            else:
                print(f"  ✗ Failed: {data}")
                self.results['errors'].append(f"Cyclist distance test failed for {cyclist.user_id}: {data}")
        
        # Test a few random groups
        groups = Group.objects.filter(is_visible=True)[:5]
        for group in groups:
            print(f"\nTesting group distance: {group.name}...")
            success, data = self.test_get_group_distance(group, api_key)
            if success:
                distance = data.get('distance_total', 0)
                print(f"  ✓ Success: Total distance = {distance} km")
            else:
                print(f"  ✗ Failed: {data}")
                self.results['errors'].append(f"Group distance test failed for {group.name}: {data}")
        
        # Finalize results
        self.results['end_time'] = datetime.now().isoformat()
        duration = datetime.fromisoformat(self.results['end_time']) - datetime.fromisoformat(self.results['start_time'])
        self.results['duration_seconds'] = duration.total_seconds()
        
        return self.results
    
    def save_results(self, filename='load_test_results.json'):
        """Save test results to JSON file."""
        filepath = os.path.join(os.path.dirname(__file__), filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, indent=2, ensure_ascii=False)
        print(f"\nResults saved to: {filepath}")
        return filepath
    
    def print_summary(self):
        """Print test summary."""
        print("\n" + "=" * 80)
        print("Test Summary")
        print("=" * 80)
        print(f"Duration: {self.results.get('duration_seconds', 0):.2f} seconds")
        print(f"Devices tested: {self.results['devices_tested']}")
        print(f"Cyclists tested: {self.results['cyclists_tested']}")
        print(f"Updates sent: {self.results['updates_sent']}")
        print(f"Updates successful: {self.results['updates_successful']}")
        print(f"Updates failed: {self.results['updates_failed']}")
        print(f"Leaderboard tests: {len(self.results['leaderboard_tests'])}")
        
        successful_tests = sum(1 for t in self.results['leaderboard_tests'] if t.get('success'))
        print(f"Successful leaderboard tests: {successful_tests}/{len(self.results['leaderboard_tests'])}")
        
        if self.results['errors']:
            print(f"\nErrors: {len(self.results['errors'])}")
            for error in self.results['errors'][:5]:  # Show first 5 errors
                print(f"  - {error}")
            if len(self.results['errors']) > 5:
                print(f"  ... and {len(self.results['errors']) - 5} more errors")
        else:
            print("\n✓ No errors!")
        
        print("=" * 80)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Load test for leaderboard endpoints')
    parser.add_argument(
        '--base-url',
        default=DEFAULT_SERVER_URL,
        help=f'Base URL of the API server (default: {DEFAULT_SERVER_URL})'
    )
    parser.add_argument(
        '--iterations',
        type=int,
        default=10,
        help='Number of test iterations (default: 10)'
    )
    parser.add_argument(
        '--delay',
        type=float,
        default=1.0,
        help='Delay between iterations in seconds (default: 1.0)'
    )
    parser.add_argument(
        '--output',
        default='load_test_results.json',
        help='Output filename for results (default: load_test_results.json)'
    )
    parser.add_argument(
        '--no-live-leaderboard',
        action='store_true',
        help='Disable live leaderboard display during test run'
    )
    
    args = parser.parse_args()
    
    # Run load test
    test = LeaderboardLoadTest(
        base_url=args.base_url,
        iterations=args.iterations,
        delay=args.delay,
        show_live_leaderboard=not args.no_live_leaderboard
    )
    
    results = test.run_load_test()
    test.save_results(args.output)
    test.print_summary()
    
    # Exit with error code if there were failures
    if results['errors']:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()

