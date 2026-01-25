# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    generate_live_test_data.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
"""
Script to generate live test kilometer data for devices and cyclists.
Sends HTTP requests to the API endpoint to simulate real device activity.

Usage:
    python test/generate_live_test_data.py [--iterations N] [--interval SECONDS] [--base-url URL]
"""

import os
import sys
import django
import json
import time
import random
import argparse
import requests
from pathlib import Path
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor, as_completed

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

from api.models import Cyclist
from iot.models import Device
from django.conf import settings


def get_api_key():
    """Get API key from .env or Django settings."""
    # First try .env directly (works even if Django not fully loaded)
    api_key = os.getenv('MCC_APP_API_KEY')
    if api_key:
        return api_key
    
    # Fallback to Django settings
    api_key = getattr(settings, 'MCC_APP_API_KEY', None)
    if not api_key:
        print("ERROR: MCC_APP_API_KEY not found in .env file or Django settings!")
        print("Please set MCC_APP_API_KEY in your .env file or settings.py")
        sys.exit(1)
    return api_key


def send_update(base_url, api_key, id_tag, device_id, distance):
    """Send an update request to the API."""
    url = f"{base_url}/api/update-data"
    headers = {
        'X-Api-Key': api_key,
        'Content-Type': 'application/json'
    }
    data = {
        'id_tag': id_tag,
        'device_id': device_id,
        'distance': str(distance)
    }
    
    try:
        response = requests.post(url, json=data, headers=headers, timeout=10)
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                return True, result
            else:
                return False, result.get('error', 'Unknown error')
        else:
            return False, f"HTTP {response.status_code}: {response.text}"
    except requests.exceptions.RequestException as e:
        return False, str(e)


def generate_test_data(base_url, api_key, iterations=10, interval=5, classes=None):
    """Generate test kilometer data for active devices and cyclists.
    
    Each cyclist is assigned to exactly one device, ensuring that a cyclist
    can only use one device at a time.
    """
    
    # Get all visible devices with KM collection enabled
    devices = Device.objects.filter(is_visible=True, is_km_collection_enabled=True)
    if devices.exists():
        print(f"Found {devices.count()} active device(s)")
    else:
        print("WARNING: No active devices found!")
        print("Please create at least one device in the admin interface.")
        return
    
    # Get all cyclists with id_tag
    cyclists = Cyclist.objects.filter(id_tag__isnull=False).exclude(id_tag='')
    
    # Filter by classes if specified
    if classes:
        from api.models import Group
        # Find SchuleA
        try:
            schule_a = Group.objects.get(name='SchuleA')
            # Get cyclists from specified classes
            class_groups = Group.objects.filter(parent=schule_a, name__in=classes, is_visible=True)
            if class_groups.exists():
                class_ids = list(class_groups.values_list('id', flat=True))
                cyclists = cyclists.filter(groups__id__in=class_ids).distinct()
                print(f"Filtering by classes: {', '.join(classes)}")
                print(f"Found {class_groups.count()} matching class(es)")
            else:
                print(f"WARNING: No classes found matching: {classes}")
                return
        except Group.DoesNotExist:
            print("WARNING: SchuleA not found!")
            return
    
    if not cyclists.exists():
        print("WARNING: No cyclists with id_tag found!")
        print("Please create at least one cyclist with an id_tag in the admin interface.")
        return
    
    print(f"Found {cyclists.count()} cyclist(s) with id_tag")
    
    # Create device-cyclist assignments (one cyclist per device)
    device_list = list(devices)
    cyclist_list = list(cyclists)
    
    if not device_list or not cyclist_list:
        print("ERROR: Need at least one device and one cyclist!")
        return
    
    # Assign each cyclist to a device (round-robin if more cyclists than devices)
    assignments = {}
    for idx, cyclist in enumerate(cyclist_list):
        device = device_list[idx % len(device_list)]
        assignments[cyclist.id] = device
        print(f"  {cyclist.user_id} ({cyclist.id_tag}) → {device.name}")
    
    print(f"\nGenerating test data for {iterations} iterations with {interval}s interval...")
    print("=" * 60)
    
    successful_updates = 0
    failed_updates = 0
    
    for iteration in range(1, iterations + 1):
        print(f"\n--- Iteration {iteration}/{iterations} ---")
        print(f"Sending updates for all {len(cyclist_list)} cyclists simultaneously...")
        
        # Prepare updates for all cyclists
        update_tasks = []
        for cyclist in cyclist_list:
            device = assignments[cyclist.id]
            # Generate a realistic distance delta (0.1 to 2.0 km)
            distance_delta = Decimal(str(round(random.uniform(0.1, 2.0), 5)))
            update_tasks.append((cyclist, device, distance_delta))
        
        # Send all updates in parallel
        with ThreadPoolExecutor(max_workers=len(cyclist_list)) as executor:
            # Submit all tasks
            future_to_task = {
                executor.submit(
                    send_update, 
                    base_url, 
                    api_key, 
                    cyclist.id_tag, 
                    device.name, 
                    distance_delta
                ): (cyclist, device, distance_delta)
                for cyclist, device, distance_delta in update_tasks
            }
            
            # Process results as they complete
            for future in as_completed(future_to_task):
                cyclist, device, distance_delta = future_to_task[future]
                try:
                    success, result = future.result()
                    if success:
                        print(f"  ✅ {cyclist.user_id} on {device.name}: {distance_delta} km")
                        successful_updates += 1
                    else:
                        print(f"  ❌ {cyclist.user_id} on {device.name}: {result}")
                        failed_updates += 1
                except Exception as e:
                    print(f"  ❌ {cyclist.user_id} on {device.name}: Exception - {e}")
                    failed_updates += 1
        
        # Wait before next iteration (except for the last one)
        if iteration < iterations:
            print(f"\nWaiting {interval} seconds before next iteration...")
            time.sleep(interval)
    
    print("\n" + "=" * 60)
    print(f"Summary:")
    print(f"  Successful updates: {successful_updates}")
    print(f"  Failed updates: {failed_updates}")
    print(f"  Total iterations: {iterations}")
    
    if successful_updates > 0:
        print(f"\n✅ Test data generation completed!")
        print(f"   Check the leaderboard at: {base_url}/de/map/")
        print(f"   Or the admin interface at: {base_url}/de/admin/")


def main():
    parser = argparse.ArgumentParser(
        description='Generate live test kilometer data for devices and cyclists',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate 10 updates with 5 second intervals
  python test/generate_live_test_data.py
  
  # Generate 20 updates with 3 second intervals
  python test/generate_live_test_data.py --iterations 20 --interval 3
  
  # Use custom base URL
  python test/generate_live_test_data.py --base-url http://localhost:8000
        """
    )
    parser.add_argument(
        '--iterations',
        type=int,
        default=10,
        help='Number of iterations (default: 10)'
    )
    parser.add_argument(
        '--interval',
        type=int,
        default=5,
        help='Interval between iterations in seconds (default: 5)'
    )
    parser.add_argument(
        '--base-url',
        type=str,
        default='http://127.0.0.1:8000',
        help='Base URL of the Django application (default: http://127.0.0.1:8000)'
    )
    parser.add_argument(
        '--classes',
        type=str,
        nargs='+',
        default=None,
        help='Filter cyclists by class names (e.g., --classes "1a-SchuleA" "1b-SchuleA")'
    )
    
    args = parser.parse_args()
    
    # Get API key
    api_key = get_api_key()
    
    # Generate test data
    generate_test_data(
        base_url=args.base_url,
        api_key=api_key,
        iterations=args.iterations,
        interval=args.interval,
        classes=args.classes
    )


if __name__ == '__main__':
    main()

