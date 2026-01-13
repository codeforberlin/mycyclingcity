# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    mcc_api_test.py
# @author  Roland Rutz

#
import requests
import json
import random
import time
import os
import sys
import configparser
import argparse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    # Load .env from project root (parent of test/)
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    env_path = project_root / '.env'
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    # python-dotenv not installed, continue without it
    pass

# Try to import Django for local database access
DJANGO_AVAILABLE = False
Cyclist = None
Device = None
Decimal = None

try:
    # Add parent directory to path to import Django settings
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    
    # Set Django settings module
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    
    import django  # type: ignore
    django.setup()
    
    from api.models import Cyclist  # type: ignore
    from iot.models import Device  # type: ignore
    from decimal import Decimal  # type: ignore
    
    DJANGO_AVAILABLE = True
except (ImportError, Exception):
    # Django not available - will use test data files instead
    DJANGO_AVAILABLE = False

# --- Load configuration ---
parser = argparse.ArgumentParser(description="Sends test data to the MCC-DB Backend.")
parser.add_argument("--id_tag", type=str, help="The ID tag of the cyclist (e.g. 'mcc-cyclist-01').")
parser.add_argument("--distance", type=float, help="The distance in kilometers to be sent.")
parser.add_argument("--device", type=str, help="The device ID (e.g. 'cbm-demo01').")
parser.add_argument("--interval", type=int, help="The send interval in seconds. Overrides the value in the configuration file.")
parser.add_argument("--config", "-c", type=str, help="Path to the configuration file.")
parser.add_argument("--dns", action="store_true", help="Uses the DNS URL (HTTPS) instead of IP:Port (HTTP).")
parser.add_argument("--loop", action="store_true", help="Continuously sends test data at the specified interval.")
# NEW: Option to test the get-user-id endpoint
parser.add_argument("--get-user-id", action="store_true", help="Tests the /api/get-user-id endpoint with the specified --id_tag.")
# --- Parameters for realistic simulation ---
parser.add_argument("--wheel-size", type=int, choices=[20, 24, 26, 28], help="The wheel size in inches (20, 24, 26, 28).")
parser.add_argument("--speed", type=float, help="A fixed speed in km/h for the simulation.")
parser.add_argument("--test-data-file", type=str, help="Path to a JSON file with lists of devices and id_tags for automated tests.")
parser.add_argument("--cyclist-duration", type=int, help="Duration a cyclist stays on a device in seconds. Overrides the value in the configuration file.")
parser.add_argument("--max-concurrent", type=int, help="Maximum number of concurrent connections/threads. Default: number of devices (unlimited).")
parser.add_argument("--send-jitter", type=float, default=0.5, help="Maximum random time offset in seconds for send pulses (default: 0.5s). Simulates realistic time shifts between devices.")
parser.add_argument("--max-devices", type=int, help="Maximum number of devices to use. Limits the number of devices from the configuration (default: all devices).")
parser.add_argument("--retry-attempts", type=int, default=3, help="Number of retry attempts on errors (default: 3). Simulates the behavior of real devices that retry sending on errors.")
parser.add_argument("--retry-delay", type=float, default=1.0, help="Base delay in seconds between retry attempts (default: 1.0s). Uses exponential backoff.")
# NEW: Functional test parameters
parser.add_argument("--functional-test", action="store_true", help="Runs a functional test with extended test file (requires --test-data-file).")
parser.add_argument("--test-duration", type=int, help="Duration of the functional test in seconds. If not specified, the test runs until all target kilometers are reached.")
parser.add_argument("--report-file", type=str, help="Path to the report file (default: test_report_<timestamp>.json in the current directory).")
parser.add_argument("--create-test-data", action="store_true", help="Creates test data (devices and cyclists) in the database when run locally. Ignored if Django is not available.")
args = parser.parse_args()

config = configparser.ConfigParser()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

if args.config:
    CONFIG_FILE = args.config
else:
    # CORRECTION: Now searches for the new configuration file mcc_api_test.cfg
    CONFIG_FILE = os.path.join(BASE_DIR, 'mcc_api_test.cfg')

if not os.path.exists(CONFIG_FILE):
    print(f"❌ Error: Configuration file '{CONFIG_FILE}' not found.")
    sys.exit(1)

config.read(CONFIG_FILE)
GENERAL_SETTINGS = config['general']

# Load configuration: .env takes priority, then config file
SERVER_IP = os.getenv('TEST_SERVER_IP') or GENERAL_SETTINGS.get('server_ip')
SERVER_PORT = int(os.getenv('TEST_SERVER_PORT', 0)) or GENERAL_SETTINGS.getint('server_port')
SEND_INTERVAL = args.interval if args.interval is not None else GENERAL_SETTINGS.getint('send_interval')
CYCLIST_DURATION = args.cyclist_duration if args.cyclist_duration is not None else GENERAL_SETTINGS.getint('cyclist_duration', fallback=60)

# API Key: .env takes priority, then config file
API_KEY = os.getenv('MCC_APP_API_KEY') or GENERAL_SETTINGS.get('api_key')
if not API_KEY:
    print("❌ Error: API key not found. Please set MCC_APP_API_KEY in .env file or api_key in config file.")
    sys.exit(1)

if args.dns:
    SERVER_DOMAIN = os.getenv('TEST_SERVER_DOMAIN') or GENERAL_SETTINGS.get('server_domain')
    if not SERVER_DOMAIN:
        print("❌ Error: Server domain not found. Please set TEST_SERVER_DOMAIN in .env file or server_domain in config file.")
        sys.exit(1)
    SERVER_URL = f"https://{SERVER_DOMAIN}"
    AUTH_HEADER = {'X-Api-Key': API_KEY}
else:
    SERVER_URL = f"http://{SERVER_IP}:{SERVER_PORT}"
    AUTH_HEADER = {'X-Api-Key': API_KEY}

# NEW: Path to Django update endpoint
DJANGO_UPDATE_PATH = "/api/update-data"
# NEW: Path to Django get-user-id endpoint
DJANGO_GET_USER_ID_PATH = "/api/get-user-id"
# NEW: API paths for validation
DJANGO_GET_CYCLIST_DISTANCE_PATH = "/api/get-cyclist-distance"
DJANGO_GET_ACTIVE_CYCLISTS_PATH = "/api/get-active-cyclists"


def load_json_data(file_path):
    """Loads JSON data from a file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"❌ Error: File '{file_path}' not found.")
        return None
    except json.JSONDecodeError:
        print(f"❌ Error: File '{file_path}' contains invalid JSON.")
        return None

def load_device_ids(file_path):
    """Loads device IDs from a configuration file."""
    device_config = configparser.ConfigParser()
    try:
        device_config.read(file_path)
        
        device_ids_str = device_config.get('devices', 'device_ids', fallback='')
        
        device_ids = [device_id.strip() for device_id in device_ids_str.split(',') if device_id.strip()]
        
        return device_ids
    except configparser.Error as e:
        print(f"❌ Error loading device configuration file '{file_path}': {e}")
        return []

def load_test_data_file(file_path):
    """
    Loads test data from a JSON file with lists of devices and id_tags.
    
    Expected format:
    {
        "devices": ["device1", "device2", ...],
        "id_tags": ["tag1", "tag2", ...]
    }
    
    Returns:
        tuple: (devices_list, id_tags_list) or (None, None) on error
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        devices = data.get('devices', [])
        id_tags = data.get('id_tags', [])
        
        if not isinstance(devices, list):
            print(f"❌ Error: 'devices' must be a list in '{file_path}'.")
            return None, None
        
        if not isinstance(id_tags, list):
            print(f"❌ Error: 'id_tags' must be a list in '{file_path}'.")
            return None, None
        
        # Filter empty entries
        devices = [d.strip() for d in devices if d and d.strip()]
        id_tags = [t.strip() for t in id_tags if t and t.strip()]
        
        if not devices:
            print(f"⚠️ Warning: No valid devices found in '{file_path}'.")
        
        if not id_tags:
            print(f"⚠️ Warning: No valid id_tags found in '{file_path}'.")
        
        return devices, id_tags
        
    except FileNotFoundError:
        print(f"❌ Error: File '{file_path}' not found.")
        return None, None
    except json.JSONDecodeError as e:
        print(f"❌ Error: File '{file_path}' contains invalid JSON: {e}")
        return None, None
    except Exception as e:
        print(f"❌ Error loading test data file '{file_path}': {e}")
        return None, None

def get_simulated_distance(interval_seconds, wheel_size=None, speed=None):
    """
    Simulates the distance traveled in a given interval.
    """
    if speed is not None and wheel_size is not None:
        simulated_speed = speed
        print(f"Simulating with fixed speed of {simulated_speed} km/h for wheel size {wheel_size} inches.")
    elif speed is not None:
        simulated_speed = speed
        print(f"Simulating with fixed speed: {simulated_speed} km/h")
    elif wheel_size is not None:
        if wheel_size == 20:
            speed_min, speed_max = 8, 15
        elif wheel_size == 24:
            speed_min, speed_max = 10, 18
        elif wheel_size == 26:
            speed_min, speed_max = 12, 22
        elif wheel_size == 28:
            speed_min, speed_max = 15, 25
        else:
            speed_min, speed_max = 10, 25 
            
        simulated_speed = random.uniform(speed_min, speed_max)
        print(f"Simulating with wheel size {wheel_size} inches. Random speed: {simulated_speed:.2f} km/h")
    else:
        simulated_speed = random.uniform(10, 25)
        print(f"Simulating with random speed: {simulated_speed:.2f} km/h")
        
    distance_km = simulated_speed * (interval_seconds / 3600)
    print(f"➡️ Distance calculation: {simulated_speed:.2f} km/h * ({interval_seconds}s / 3600s) = {distance_km:.2f} km")
    return round(distance_km, 2)

def send_test_data(id_tag, device_id, distance_to_send, verbose=True):
    """
    Sends simulated data to the MCC-DB Backend server.
    
    Args:
        id_tag: The ID tag of the cyclist
        device_id: The device ID
        distance_to_send: The distance to send
        verbose: Whether to output detailed information
    
    Returns:
        tuple: (success: bool, device_id: str, id_tag: str, message: str, retry_count: int)
    """
    # CORRECTION: Adds the Django path
    url = f"{SERVER_URL}{DJANGO_UPDATE_PATH}" 
    
    headers = {'Content-Type': 'application/json'}
    headers.update(AUTH_HEADER)
    
    payload = {
        "id_tag": id_tag,
        "device_id": device_id,
        "distance": distance_to_send
    }
    
    if verbose:
        print(f"-> Sending data to {url} for ID '{id_tag}'...")
        print(f"   Payload: {payload}")
    
    # Use default values from args if not provided
    max_retries = args.retry_attempts if hasattr(args, 'retry_attempts') else 3
    base_delay = args.retry_delay if hasattr(args, 'retry_delay') else 1.0
    
    last_exception = None
    last_status_code = None
    last_response_text = None
    
    for attempt in range(max_retries + 1):  # +1 for the first attempt
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=10)
            last_status_code = response.status_code
            last_response_text = response.text
            
            if response.status_code == 200:
                result_msg = f"✅ Success: {response.json()}"
                if verbose and attempt > 0:
                    print(f"   ✅ Success after {attempt} retry attempt(s)")
                elif verbose:
                    print(result_msg)
                return True, device_id, id_tag, result_msg, attempt
            elif response.status_code >= 500:
                # Server error (5xx) - should be retried
                error_msg = f"❌ Server error: HTTP status code {response.status_code}, response: {response.text[:100]}"
                if attempt < max_retries:
                    delay = base_delay * (2 ** attempt)  # Exponential backoff
                    if verbose:
                        print(f"   ⚠️  {error_msg}")
                        print(f"   🔄 Retry attempt {attempt + 1}/{max_retries} in {delay:.2f}s...")
                    time.sleep(delay)
                    continue
                else:
                    if verbose:
                        print(error_msg)
                    return False, device_id, id_tag, error_msg, attempt
            elif response.status_code >= 400:
                # Client error (4xx) - should not be retried
                error_msg = f"❌ Client error: HTTP status code {response.status_code}, response: {response.text[:100]}"
                if verbose:
                    print(error_msg)
                return False, device_id, id_tag, error_msg, attempt
            else:
                # Unexpected status code
                error_msg = f"❌ Unexpected status code: HTTP status code {response.status_code}, response: {response.text[:100]}"
                if attempt < max_retries:
                    delay = base_delay * (2 ** attempt)
                    if verbose:
                        print(f"   ⚠️  {error_msg}")
                        print(f"   🔄 Retry attempt {attempt + 1}/{max_retries} in {delay:.2f}s...")
                    time.sleep(delay)
                    continue
                else:
                    if verbose:
                        print(error_msg)
                    return False, device_id, id_tag, error_msg, attempt
                    
        except requests.exceptions.Timeout as e:
            last_exception = e
            error_msg = f"❌ Timeout: {e}"
            if attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                if verbose:
                    print(f"   ⚠️  {error_msg}")
                    print(f"   🔄 Wiederholungsversuch {attempt + 1}/{max_retries} in {delay:.2f}s...")
                time.sleep(delay)
                continue
            else:
                if verbose:
                    print(error_msg)
                return False, device_id, id_tag, error_msg, attempt
                
        except requests.exceptions.ConnectionError as e:
            last_exception = e
            error_msg = f"❌ Connection error: {e}"
            if attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                if verbose:
                    print(f"   ⚠️  {error_msg}")
                    print(f"   🔄 Retry attempt {attempt + 1}/{max_retries} in {delay:.2f}s...")
                time.sleep(delay)
                continue
            else:
                if verbose:
                    print(error_msg)
                return False, device_id, id_tag, error_msg, attempt
                
        except requests.exceptions.RequestException as e:
            last_exception = e
            error_msg = f"❌ Request error: {e}"
            if attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                if verbose:
                    print(f"   ⚠️  {error_msg}")
                    print(f"   🔄 Retry attempt {attempt + 1}/{max_retries} in {delay:.2f}s...")
                time.sleep(delay)
                continue
            else:
                if verbose:
                    print(error_msg)
                return False, device_id, id_tag, error_msg, attempt
    
    # If all attempts failed
    if last_exception:
        error_msg = f"❌ All {max_retries + 1} attempts failed. Last error: {last_exception}"
    elif last_status_code:
        error_msg = f"❌ All {max_retries + 1} attempts failed. Last status: {last_status_code}, response: {last_response_text[:100] if last_response_text else 'N/A'}"
    else:
        error_msg = f"❌ All {max_retries + 1} attempts failed."
    
    if verbose:
        print(error_msg)
    return False, device_id, id_tag, error_msg, max_retries

def get_user_id_test(id_tag):
    """
    Tests the /api/get-user-id endpoint.
    """
    url = f"{SERVER_URL}{DJANGO_GET_USER_ID_PATH}"
    
    headers = {'Content-Type': 'application/json'}
    headers.update(AUTH_HEADER)
    
    payload = {
        "id_tag": id_tag,
    }
    
    print(f"-> Querying user_id for ID tag '{id_tag}' via {url}...")
    print(f"   Payload: {payload}")
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        
        if response.status_code == 200:
            user_id = response.json().get("user_id", "ERROR: 'user_id' missing in response")
            if user_id == "NULL":
                print(f"✅ Success: ID tag '{id_tag}' is not assigned. Response: {response.json()}")
            else:
                print(f"✅ Success: ID tag '{id_tag}' is assigned to user_id: '{user_id}'. Response: {response.json()}")
        else:
            print(f"❌ Error: HTTP status code {response.status_code}, response: {response.text}")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ An error occurred: {e}")
        
    print("-" * 20)

def load_extended_test_data(file_path):
    """
    Loads extended test data from a JSON file.
    
    Expected format:
    {
        "cyclists": [
            {
                "id_tag": "rfid001",
                "target_km": 5.0
            },
            ...
        ],
        "devices": [
            {
                "device_id": "mcc-demo01",
                "wheel_size": 26
            },
            ...
        ],
        "device_switch_interval": 60,
        "send_interval": 10
    }
    
    Returns:
        dict: Test data dictionary or None on error
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        cyclists = data.get('cyclists', [])
        devices = data.get('devices', [])
        
        if not isinstance(cyclists, list) or not cyclists:
            print(f"❌ Error: 'cyclists' must be a non-empty list in '{file_path}'.")
            return None
        
        if not isinstance(devices, list) or not devices:
            print(f"❌ Error: 'devices' must be a non-empty list in '{file_path}'.")
            return None
        
        # Validate structure
        for i, cyclist in enumerate(cyclists):
            if not isinstance(cyclist, dict):
                print(f"❌ Error: cyclists[{i}] must be an object.")
                return None
            if 'id_tag' not in cyclist:
                print(f"❌ Error: cyclists[{i}] must contain 'id_tag'.")
                return None
            if 'target_km' not in cyclist:
                print(f"❌ Error: cyclists[{i}] must contain 'target_km'.")
                return None
            try:
                float(cyclist['target_km'])
            except (ValueError, TypeError):
                print(f"❌ Error: cyclists[{i}]['target_km'] must be a number.")
                return None
        
        for i, device in enumerate(devices):
            if not isinstance(device, dict):
                print(f"❌ Error: devices[{i}] must be an object.")
                return None
            if 'device_id' not in device:
                print(f"❌ Error: devices[{i}] must contain 'device_id'.")
                return None
            if 'wheel_size' not in device:
                print(f"❌ Error: devices[{i}] must contain 'wheel_size'.")
                return None
            if device['wheel_size'] not in [20, 24, 26, 28]:
                print(f"❌ Error: devices[{i}]['wheel_size'] must be 20, 24, 26, or 28.")
                return None
        
        return {
            'cyclists': cyclists,
            'devices': devices,
            'device_switch_interval': data.get('device_switch_interval', CYCLIST_DURATION),
            'send_interval': data.get('send_interval', SEND_INTERVAL)
        }
        
    except FileNotFoundError:
        print(f"❌ Error: File '{file_path}' not found.")
        return None
    except json.JSONDecodeError as e:
        print(f"❌ Error: File '{file_path}' contains invalid JSON: {e}")
        return None
    except Exception as e:
        print(f"❌ Error loading extended test data file '{file_path}': {e}")
        return None

def get_cyclist_distance_api(id_tag, start_date=None, end_date=None):
    """
    Retrieves the distance of a cyclist via the API.
    
    Args:
        id_tag: The ID tag of the cyclist
        start_date: Optional start date (YYYY-MM-DD)
        end_date: Optional end date (YYYY-MM-DD)
    
    Returns:
        tuple: (success: bool, distance: float, error_message: str)
    """
    url = f"{SERVER_URL}{DJANGO_GET_CYCLIST_DISTANCE_PATH}/{id_tag}"
    
    headers = {'Content-Type': 'application/json'}
    headers.update(AUTH_HEADER)
    
    params = {}
    if start_date:
        params['start_date'] = start_date
    if end_date:
        params['end_date'] = end_date
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            distance = float(data.get('distance_total', 0))
            return True, distance, None
        else:
            error_msg = f"HTTP {response.status_code}: {response.text[:200]}"
            return False, 0.0, error_msg
            
    except requests.exceptions.RequestException as e:
        return False, 0.0, str(e)

def get_active_cyclists_api():
    """
    Retrieves the list of active cyclists via the API.
    
    Returns:
        tuple: (success: bool, cyclists: list, error_message: str)
    """
    url = f"{SERVER_URL}{DJANGO_GET_ACTIVE_CYCLISTS_PATH}"
    
    headers = {'Content-Type': 'application/json'}
    headers.update(AUTH_HEADER)
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            cyclists = data.get('cyclists', [])
            return True, cyclists, None
        else:
            error_msg = f"HTTP {response.status_code}: {response.text[:200]}"
            return False, [], error_msg
            
    except requests.exceptions.RequestException as e:
        return False, [], str(e)

def delete_test_data_from_database(test_data):
    """
    Deletes test data (devices and cyclists) from the database.
    Only deletes data that is defined in the test data file.
    
    Args:
        test_data: Dictionary with test data (cyclists, devices)
    
    Returns:
        tuple: (success: bool, deleted_cyclists: list, deleted_devices: list, errors: list)
    """
    if not DJANGO_AVAILABLE:
        return False, [], [], ["Django not available - cannot delete database objects"]
    
    deleted_cyclists = []
    deleted_devices = []
    errors = []
    
    try:
        # Delete cyclists by id_tag
        for cyclist_data in test_data.get('cyclists', []):
            id_tag = cyclist_data.get('id_tag')
            if not id_tag:
                continue
            
            try:
                deleted_count, _ = Cyclist.objects.filter(id_tag=id_tag).delete()
                if deleted_count > 0:
                    deleted_cyclists.append(id_tag)
                    print(f"  🗑️  Cyclist deleted: {id_tag}")
            except Exception as e:
                error_msg = f"Error deleting cyclist {id_tag}: {e}"
                errors.append(error_msg)
                print(f"  ❌ {error_msg}")
        
        # Delete devices by name
        for device_data in test_data.get('devices', []):
            device_id = device_data.get('device_id')
            if not device_id:
                continue
            
            try:
                deleted_count, _ = Device.objects.filter(name=device_id).delete()
                if deleted_count > 0:
                    deleted_devices.append(device_id)
                    print(f"  🗑️  Device deleted: {device_id}")
            except Exception as e:
                error_msg = f"Error deleting device {device_id}: {e}"
                errors.append(error_msg)
                print(f"  ❌ {error_msg}")
        
        return True, deleted_cyclists, deleted_devices, errors
        
    except Exception as e:
        error_msg = f"General error deleting test data: {e}"
        errors.append(error_msg)
        return False, deleted_cyclists, deleted_devices, errors

def create_test_data_in_database(test_data):
    """
    Creates test data (devices and cyclists) in the database.
    
    Args:
        test_data: Dictionary with test data (cyclists, devices)
    
    Returns:
        tuple: (success: bool, created_cyclists: list, created_devices: list, errors: list)
    """
    if not DJANGO_AVAILABLE:
        return False, [], [], ["Django not available - cannot create database objects"]
    
    created_cyclists = []
    created_devices = []
    errors = []
    
    try:
        # Create cyclists
        for cyclist_data in test_data.get('cyclists', []):
            id_tag = cyclist_data.get('id_tag')
            if not id_tag:
                errors.append("Cyclist without id_tag found - skipping")
                continue
            
            try:
                cyclist, created = Cyclist.objects.get_or_create(
                    id_tag=id_tag,
                    defaults={
                        'user_id': cyclist_data.get('user_id', f"test-cyclist-{id_tag}"),
                        'distance_total': Decimal('0.00000'),
                        'is_km_collection_enabled': True,
                        'is_visible': True
                    }
                )
                if created:
                    created_cyclists.append(id_tag)
                    print(f"  ✅ Cyclist created: {id_tag} (user_id: {cyclist.user_id})")
                else:
                    print(f"  ℹ️  Cyclist already exists: {id_tag}")
            except Exception as e:
                error_msg = f"Error creating cyclist {id_tag}: {e}"
                errors.append(error_msg)
                print(f"  ❌ {error_msg}")
        
        # Create devices
        for device_data in test_data.get('devices', []):
            device_id = device_data.get('device_id')
            if not device_id:
                errors.append("Device without device_id found - skipping")
                continue
            
            try:
                device, created = Device.objects.get_or_create(
                    name=device_id,
                    defaults={
                        'display_name': device_data.get('display_name', device_id),
                        'distance_total': Decimal('0.00000'),
                        'is_km_collection_enabled': True,
                        'is_visible': True
                    }
                )
                if created:
                    created_devices.append(device_id)
                    print(f"  ✅ Device created: {device_id}")
                else:
                    print(f"  ℹ️  Device already exists: {device_id}")
            except Exception as e:
                error_msg = f"Error creating device {device_id}: {e}"
                errors.append(error_msg)
                print(f"  ❌ {error_msg}")
        
        return True, created_cyclists, created_devices, errors
        
    except Exception as e:
        error_msg = f"General error creating test data: {e}"
        errors.append(error_msg)
        return False, created_cyclists, created_devices, errors

def ensure_test_data_available(test_data_file):
    """
    Ensures that test data is available.
    Creates it in the database when run locally, otherwise uses the test file.
    
    Args:
        test_data_file: Path to the test data file
    
    Returns:
        dict: Test data dictionary or None on error
    """
    # Load test data from file
    test_data = load_extended_test_data(test_data_file)
    if test_data is None:
        return None
    
    # If --create-test-data is set and Django is available, create data in DB
    if args.create_test_data and DJANGO_AVAILABLE:
        # For functional tests, delete existing test data first to ensure clean state
        if args.functional_test:
            print("=" * 80)
            print("🧹 CLEANING UP EXISTING TEST DATA")
            print("=" * 80)
            print(f"Deleting existing test data from database...")
            print()
            
            delete_success, deleted_cyclists, deleted_devices, delete_errors = delete_test_data_from_database(test_data)
            
            if delete_success:
                print()
                print(f"✅ Test data cleanup completed:")
                print(f"   - {len(deleted_cyclists)} cyclist(s) deleted")
                print(f"   - {len(deleted_devices)} device(s) deleted")
                if delete_errors:
                    print(f"   ⚠️  {len(delete_errors)} warning(s)/error(s):")
                    for error in delete_errors:
                        print(f"      - {error}")
            else:
                print()
                print(f"⚠️  Warning during cleanup:")
                for error in delete_errors:
                    print(f"   - {error}")
            
            print("=" * 80)
            print()
        
        print("=" * 80)
        print("📦 CREATING TEST DATA IN DATABASE")
        print("=" * 80)
        print(f"Local database access available.")
        print(f"Creating devices and cyclists from test file: {test_data_file}")
        print()
        
        success, created_cyclists, created_devices, errors = create_test_data_in_database(test_data)
        
        if success:
            print()
            print(f"✅ Test data successfully created:")
            print(f"   - {len(created_cyclists)} new cyclists created")
            print(f"   - {len(created_devices)} new devices created")
            if errors:
                print(f"   ⚠️  {len(errors)} warning(s)/error(s):")
                for error in errors:
                    print(f"      - {error}")
        else:
            print()
            print(f"❌ Error creating test data:")
            for error in errors:
                print(f"   - {error}")
            print()
            print("⚠️  Using test data from file (may not exist in DB)")
        
        print("=" * 80)
        print()
    elif args.create_test_data and not DJANGO_AVAILABLE:
        print("⚠️  Warning: --create-test-data specified, but Django not available.")
        print("   Using test data from file (may not exist in DB)")
        print()
    else:
        print("ℹ️  Using test data from file.")
        if DJANGO_AVAILABLE:
            print("   (Hint: Use --create-test-data to create data in DB)")
        print()
    
    return test_data

def run_functional_test(test_data, test_duration=None, report_file=None):
    """
    Runs a functional test with extended test data.
    
    Args:
        test_data: Dictionary with test data (cyclists, devices, etc.)
        test_duration: Optional test duration in seconds
        report_file: Optional path to the report file
    """
    from datetime import datetime
    
    print("=" * 80)
    print("🚀 FUNCTIONAL TEST STARTED")
    print("=" * 80)
    
    cyclists = test_data['cyclists']
    devices = test_data['devices']
    device_switch_interval = test_data.get('device_switch_interval', CYCLIST_DURATION)
    send_interval = test_data.get('send_interval', SEND_INTERVAL)
    
    print(f"📊 Test configuration:")
    print(f"   - Cyclists: {len(cyclists)}")
    print(f"   - Devices: {len(devices)}")
    print(f"   - Send interval: {send_interval}s")
    print(f"   - Device switch interval: {device_switch_interval}s")
    if test_duration:
        print(f"   - Test duration: {test_duration}s")
    else:
        print(f"   - Test duration: Until all target kilometers are reached")
    print()
    
    # Initialize tracking data structures
    test_start_time = time.time()
    test_start_datetime = datetime.now()
    
    # Tracking for each cyclist
    cyclist_tracking = {}
    for cyclist in cyclists:
        cyclist_tracking[cyclist['id_tag']] = {
            'target_km': float(cyclist['target_km']),
            'sent_km': 0.0,
            'devices_used': [],
            'device_assignments': [],  # List of (device_id, start_time, end_time, km_sent)
            'current_device': None,
            'current_device_start': None,
            'goal_reached': False,
            'goal_reached_time': None
        }
    
    # Tracking for each device
    device_tracking = {}
    for device in devices:
        device_tracking[device['device_id']] = {
            'wheel_size': device['wheel_size'],
            'cyclists_used': [],
            'total_km_sent': 0.0,
            'current_cyclist': None,
            'current_cyclist_start': None
        }
    
    # Initial assignment: Each cyclist gets a device
    available_devices = devices.copy()
    random.shuffle(available_devices)
    
    for i, cyclist in enumerate(cyclists):
        if i < len(available_devices):
            device = available_devices[i]
            cyclist_tracking[cyclist['id_tag']]['current_device'] = device['device_id']
            cyclist_tracking[cyclist['id_tag']]['current_device_start'] = time.time()
            device_tracking[device['device_id']]['current_cyclist'] = cyclist['id_tag']
            device_tracking[device['device_id']]['current_cyclist_start'] = time.time()
            if device['device_id'] not in cyclist_tracking[cyclist['id_tag']]['devices_used']:
                cyclist_tracking[cyclist['id_tag']]['devices_used'].append(device['device_id'])
            if cyclist['id_tag'] not in device_tracking[device['device_id']]['cyclists_used']:
                device_tracking[device['device_id']]['cyclists_used'].append(cyclist['id_tag'])
    
    iteration = 0
    all_goals_reached = False
    
    print("🔄 Starting test run...")
    print("-" * 80)
    
    while True:
        iteration += 1
        current_time = time.time()
        elapsed_time = current_time - test_start_time
        
        # Check if test duration reached
        if test_duration and elapsed_time >= test_duration:
            print(f"\n⏱️  Test duration ({test_duration}s) reached. Ending test run.")
            break
        
        # Check if all goals reached
        all_goals_reached = all(
            tracking['goal_reached'] or tracking['sent_km'] >= tracking['target_km']
            for tracking in cyclist_tracking.values()
        )
        if all_goals_reached and not test_duration:
            print(f"\n✅ All target kilometers reached. Ending test run.")
            break
        
        # Device switch logic
        device_switches = []
        for cyclist_data in cyclists:
            id_tag = cyclist_data['id_tag']
            tracking = cyclist_tracking[id_tag]
            
            if tracking['current_device'] and tracking['current_device_start']:
                device_time = current_time - tracking['current_device_start']
                
                if device_time >= device_switch_interval:
                    # Device switch due
                    old_device = tracking['current_device']
                    
                    # Save the previous assignment
                    if tracking['current_device_start']:
                        km_on_device = tracking['sent_km'] - sum(
                            assignment['km_sent'] for assignment in tracking['device_assignments']
                        )
                        tracking['device_assignments'].append({
                            'device_id': old_device,
                            'start_time': tracking['current_device_start'],
                            'end_time': current_time,
                            'km_sent': km_on_device
                        })
                    
                    # Choose a new device (random, but not the current one)
                    available_devices_for_switch = [
                        d for d in devices 
                        if d['device_id'] != old_device
                    ]
                    if available_devices_for_switch:
                        new_device = random.choice(available_devices_for_switch)
                    else:
                        new_device = devices[0]  # Fallback
                    
                    # Update tracking
                    tracking['current_device'] = new_device['device_id']
                    tracking['current_device_start'] = current_time
                    if new_device['device_id'] not in tracking['devices_used']:
                        tracking['devices_used'].append(new_device['device_id'])
                    
                    # Update device tracking
                    if device_tracking[old_device]['current_cyclist'] == id_tag:
                        device_tracking[old_device]['current_cyclist'] = None
                        device_tracking[old_device]['current_cyclist_start'] = None
                    device_tracking[new_device['device_id']]['current_cyclist'] = id_tag
                    device_tracking[new_device['device_id']]['current_cyclist_start'] = current_time
                    if id_tag not in device_tracking[new_device['device_id']]['cyclists_used']:
                        device_tracking[new_device['device_id']]['cyclists_used'].append(id_tag)
                    
                    device_switches.append((id_tag, old_device, new_device['device_id']))
        
        if device_switches:
            print(f"\n[Iteration {iteration}] Device switch:")
            for id_tag, old_dev, new_dev in device_switches:
                print(f"   {id_tag}: {old_dev} → {new_dev}")
        
        # Calculate distance for each cyclist based on their current device
        distances_to_send = {}
        for cyclist_data in cyclists:
            id_tag = cyclist_data['id_tag']
            tracking = cyclist_tracking[id_tag]
            
            if tracking['goal_reached']:
                continue  # Skip cyclists who have already reached their goal
            
            current_device_id = tracking['current_device']
            if not current_device_id:
                continue
            
            # Find device configuration
            device_config = next((d for d in devices if d['device_id'] == current_device_id), None)
            if not device_config:
                continue
            
            wheel_size = device_config['wheel_size']
            distance = get_simulated_distance(send_interval, wheel_size, None)
            distances_to_send[id_tag] = (current_device_id, distance)
        
        if not distances_to_send:
            print(f"\n[Iteration {iteration}] All cyclists have reached their goal.")
            break
        
        # Send data in parallel
        print(f"\n[Iteration {iteration}] Sending data for {len(distances_to_send)} cyclists...")
        print(f"   Elapsed time: {elapsed_time:.1f}s")
        
        with ThreadPoolExecutor(max_workers=min(len(distances_to_send), args.max_concurrent or len(distances_to_send))) as executor:
            future_to_cyclist = {}
            for id_tag, (device_id, distance) in distances_to_send.items():
                jitter_delay = random.uniform(0, args.send_jitter)
                
                def send_with_delay(delay, tag, dev_id, dist):
                    if delay > 0:
                        time.sleep(delay)
                    return send_test_data(tag, dev_id, dist, verbose=False)
                
                future = executor.submit(send_with_delay, jitter_delay, id_tag, device_id, distance)
                future_to_cyclist[future] = (id_tag, device_id, distance)
            
            # Wait for results
            for future in as_completed(future_to_cyclist):
                id_tag, device_id, distance = future_to_cyclist[future]
                try:
                    success, _, _, message, retry_count = future.result()
                    if success:
                        cyclist_tracking[id_tag]['sent_km'] += distance
                        device_tracking[device_id]['total_km_sent'] += distance
                        
                        # Check if goal reached
                        tracking = cyclist_tracking[id_tag]
                        if not tracking['goal_reached'] and tracking['sent_km'] >= tracking['target_km']:
                            tracking['goal_reached'] = True
                            tracking['goal_reached_time'] = time.time()
                            print(f"   ✅ {id_tag} reached goal: {tracking['sent_km']:.2f} km / {tracking['target_km']:.2f} km")
                except Exception as exc:
                    print(f"   ❌ Error for {id_tag} on {device_id}: {exc}")
        
        # Show progress
        progress_lines = []
        for cyclist_data in cyclists:
            id_tag = cyclist_data['id_tag']
            tracking = cyclist_tracking[id_tag]
            progress = (tracking['sent_km'] / tracking['target_km'] * 100) if tracking['target_km'] > 0 else 0
            status = "✅" if tracking['goal_reached'] else "🔄"
            progress_lines.append(f"   {status} {id_tag}: {tracking['sent_km']:.2f}/{tracking['target_km']:.2f} km ({progress:.1f}%)")
        
        if iteration % 5 == 0:  # Show progress every 5 iterations
            print("\n📊 Progress:")
            for line in progress_lines:
                print(line)
        
        time.sleep(send_interval)
    
    # Test run ended - validate results
    print("\n" + "=" * 80)
    print("🔍 VALIDATING RESULTS")
    print("=" * 80)
    
    test_end_time = time.time()
    test_end_datetime = datetime.now()
    test_duration_actual = test_end_time - test_start_time
    
    # Wait briefly for all data to be processed
    print("⏳ Waiting 2 seconds for data processing...")
    time.sleep(2)
    
    validation_results = {}
    validation_errors = []
    
    for cyclist_data in cyclists:
        id_tag = cyclist_data['id_tag']
        tracking = cyclist_tracking[id_tag]
        
        print(f"\n🔍 Validating {id_tag}...")
        print(f"   Sent: {tracking['sent_km']:.2f} km")
        print(f"   Target: {tracking['target_km']:.2f} km")
        
        # Query API
        success, api_distance, error = get_cyclist_distance_api(
            id_tag,
            test_start_datetime.strftime('%Y-%m-%d'),
            test_end_datetime.strftime('%Y-%m-%d')
        )
        
        if success:
            # Compare with sent data
            # Note: The API returns the total distance, not just the test distance
            # We need to retrieve the distance before the test
            success_before, distance_before, _ = get_cyclist_distance_api(id_tag)
            if success_before:
                test_period_distance = api_distance - distance_before
                difference = abs(test_period_distance - tracking['sent_km'])
                difference_percent = (difference / tracking['sent_km'] * 100) if tracking['sent_km'] > 0 else 0
                
                validation_results[id_tag] = {
                    'sent_km': tracking['sent_km'],
                    'api_distance_before': distance_before,
                    'api_distance_after': api_distance,
                    'api_test_period_distance': test_period_distance,
                    'difference': difference,
                    'difference_percent': difference_percent,
                    'valid': difference_percent < 5.0,  # 5% tolerance
                    'goal_reached': tracking['goal_reached']
                }
                
                status = "✅" if validation_results[id_tag]['valid'] else "⚠️"
                print(f"   {status} API distance (test period): {test_period_distance:.2f} km")
                print(f"   {status} Difference: {difference:.2f} km ({difference_percent:.1f}%)")
            else:
                validation_errors.append(f"{id_tag}: Could not retrieve distance before test")
                print(f"   ❌ Could not retrieve distance before test")
        else:
            validation_errors.append(f"{id_tag}: {error}")
            print(f"   ❌ API error: {error}")
    
    # Generate report
    print("\n" + "=" * 80)
    print("📄 REPORT GENERATION")
    print("=" * 80)
    
    report = {
        'test_info': {
            'start_time': test_start_datetime.isoformat(),
            'end_time': test_end_datetime.isoformat(),
            'duration_seconds': test_duration_actual,
            'iterations': iteration,
            'send_interval': send_interval,
            'device_switch_interval': device_switch_interval
        },
        'test_config': {
            'cyclists': cyclists,
            'devices': devices
        },
        'cyclist_results': {},
        'device_results': {},
        'validation_results': validation_results,
        'validation_errors': validation_errors,
        'summary': {
            'total_cyclists': len(cyclists),
            'goals_reached': sum(1 for t in cyclist_tracking.values() if t['goal_reached']),
            'total_km_sent': sum(t['sent_km'] for t in cyclist_tracking.values()),
            'validations_passed': sum(1 for r in validation_results.values() if r['valid']),
            'validations_failed': len(validation_results) - sum(1 for r in validation_results.values() if r['valid'])
        }
    }
    
    # Add detailed results
    for cyclist_data in cyclists:
        id_tag = cyclist_data['id_tag']
        tracking = cyclist_tracking[id_tag]
        report['cyclist_results'][id_tag] = {
            'target_km': tracking['target_km'],
            'sent_km': tracking['sent_km'],
            'goal_reached': tracking['goal_reached'],
            'goal_reached_time': tracking['goal_reached_time'],
            'devices_used': tracking['devices_used'],
            'device_assignments': tracking['device_assignments']
        }
    
    for device in devices:
        device_id = device['device_id']
        tracking = device_tracking[device_id]
        report['device_results'][device_id] = {
            'wheel_size': tracking['wheel_size'],
            'total_km_sent': tracking['total_km_sent'],
            'cyclists_used': tracking['cyclists_used']
        }
    
    # Show summary
    print("\n📊 SUMMARY:")
    print(f"   Test duration: {test_duration_actual:.1f}s ({test_duration_actual/60:.1f} minutes)")
    print(f"   Iterations: {iteration}")
    print(f"   Cyclists: {report['summary']['total_cyclists']}")
    print(f"   Goals reached: {report['summary']['goals_reached']}/{report['summary']['total_cyclists']}")
    print(f"   Total sent: {report['summary']['total_km_sent']:.2f} km")
    print(f"   Validations passed: {report['summary']['validations_passed']}/{len(validation_results)}")
    print(f"   Validations failed: {report['summary']['validations_failed']}")
    
    if validation_errors:
        print(f"\n⚠️  Validation errors:")
        for error in validation_errors:
            print(f"   - {error}")
    
    # Save report
    if not report_file:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_file = f"test_report_{timestamp}.json"
    
    try:
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"\n✅ Report saved: {report_file}")
    except Exception as e:
        print(f"\n❌ Error saving report: {e}")
    
    print("\n" + "=" * 80)
    print("✅ FUNCTIONAL TEST COMPLETED")
    print("=" * 80)

# --- Main script logic ---
if __name__ == '__main__':
    
    # NEW: Logic for functional test
    if args.functional_test:
        if not args.test_data_file:
            print("❌ Error: --test-data-file must also be specified for --functional-test.")
            parser.print_help()
            sys.exit(1)
        
        test_data = ensure_test_data_available(args.test_data_file)
        if test_data is None:
            print("❌ Error: Could not load test data. Script will be terminated.")
            sys.exit(1)
        
        run_functional_test(test_data, args.test_duration, args.report_file)
        sys.exit(0)
    
    # NEW: Logic for query endpoint
    if args.get_user_id:
        if not args.id_tag:
            print("❌ Error: --id_tag must also be specified for --get-user-id.")
            parser.print_help()
            sys.exit(1)
        
        get_user_id_test(args.id_tag)
        sys.exit(0)
    
    
    data_dir = GENERAL_SETTINGS.get('data_directory')
    if data_dir:
        # Resolve paths relative to mcc_api_test.cfg
        DATA_DIR_PATH = os.path.abspath(os.path.join(os.path.dirname(CONFIG_FILE), data_dir))
    else:
        DATA_DIR_PATH = os.path.dirname(CONFIG_FILE)

    MAIN_MAPPING_FILE = os.path.join(DATA_DIR_PATH, GENERAL_SETTINGS.get('main_mapping_file'))
    DEVICE_LIST_CONFIG_FILE = os.path.join(DATA_DIR_PATH, GENERAL_SETTINGS.get('device_list_config_file'))
    
    if args.loop:
        if args.test_data_file:
            # Scenario: Automated test with configurable test data file
            print(f"Starting automated test with data from '{args.test_data_file}'...")
            print(f"Sending test data every {SEND_INTERVAL} seconds...")
            
            # Check if it's an extended test file
            test_data_extended = load_extended_test_data(args.test_data_file)
            if test_data_extended:
                # Extended test file - ensure data is available
                ensure_test_data_available(args.test_data_file)
                devices = [d['device_id'] for d in test_data_extended['devices']]
                id_tags = [c['id_tag'] for c in test_data_extended['cyclists']]
            else:
                # Simple test file (old format)
                devices, id_tags = load_test_data_file(args.test_data_file)
            if devices is None or id_tags is None:
                print("Script will be terminated.")
                sys.exit(1)
            
            if not devices:
                print("❌ Error: No valid devices found in test data file. Script will be terminated.")
                sys.exit(1)
            
            if not id_tags:
                print("❌ Error: No valid id_tags found in test data file. Script will be terminated.")
                sys.exit(1)
            
            # Limit the number of devices used, if desired
            original_device_count = len(devices)
            if args.max_devices and args.max_devices > 0:
                if args.max_devices < len(devices):
                    devices = devices[:args.max_devices]
                    print(f"🔧 Device count limited: {original_device_count} → {len(devices)} devices")
                elif args.max_devices > len(devices):
                    print(f"⚠️  Warning: --max-devices ({args.max_devices}) is greater than available devices ({len(devices)}). Using all {len(devices)} devices.")
            
            # Determine maximum number of concurrent connections
            max_workers = args.max_concurrent if args.max_concurrent else len(devices)
            if max_workers > len(devices):
                max_workers = len(devices)
                print(f"⚠️  Warning: --max-concurrent ({args.max_concurrent}) is greater than number of devices ({len(devices)}). Using {len(devices)}.")
            
            print(f"✅ Found devices: {devices} ({len(devices)} devices)")
            print(f"✅ Found ID tags: {id_tags} ({len(id_tags)} cyclists)")
            print(f"🔄 Starting infinite loop: Parallel data transmission for all {len(devices)} devices...")
            print(f"   Send interval: {SEND_INTERVAL} seconds")
            print(f"   Duration per cyclist: {CYCLIST_DURATION} seconds")
            print(f"   → Each cyclist sends {CYCLIST_DURATION // SEND_INTERVAL} updates, then switch")
            print(f"   ⚠️  Important: Each cyclist sends from only one device at a time")
            print(f"   🔧 Maximum concurrent connections: {max_workers}")
            if max_workers < len(devices):
                print(f"   ⚠️  Note: {len(devices) - max_workers} device(s) will be processed in batches")
            print(f"   ⏱️  Time offset (Jitter): {args.send_jitter:.2f} seconds (randomly distributed)")
            print(f"   🔄 Retry attempts on errors: {args.retry_attempts} (Base delay: {args.retry_delay:.2f}s)")
            print("-" * 60)
            
            # State for each device: (current_cyclist, start_time)
            device_states = {}
            # Assignment: cyclist -> device (to ensure a cyclist is only assigned to one device)
            cyclist_to_device = {}
            
            # Initial assignment: Each device gets a unique cyclist
            available_cyclists = id_tags.copy()
            random.shuffle(available_cyclists)
            
            for i, device_id in enumerate(devices):
                if i < len(available_cyclists):
                    assigned_cyclist = available_cyclists[i]
                else:
                    # If more devices than cyclists, repeat cyclists
                    assigned_cyclist = random.choice(id_tags)
                
                device_states[device_id] = {
                    'current_cyclist': assigned_cyclist,
                    'start_time': time.time()
                }
                cyclist_to_device[assigned_cyclist] = device_id
            
            iteration = 0
            start_time = time.time()
            
            while True:
                iteration += 1
                current_time = time.time()
                distance_to_send = get_simulated_distance(SEND_INTERVAL, args.wheel_size, args.speed)
                
                # Check for each device if the duration has elapsed
                cyclist_changes = []
                for device_id in devices:
                    state = device_states[device_id]
                    elapsed = current_time - state['start_time']
                    
                    if elapsed >= CYCLIST_DURATION:
                        # Duration elapsed, switch cyclist
                        old_cyclist = state['current_cyclist']
                        
                        # Remove old assignment
                        if old_cyclist in cyclist_to_device:
                            del cyclist_to_device[old_cyclist]
                        
                        # Find a new cyclist that is not yet assigned to a device
                        available_cyclists_for_switch = [c for c in id_tags if c not in cyclist_to_device]
                        
                        if available_cyclists_for_switch:
                            # There are still unassigned cyclists
                            new_cyclist = random.choice(available_cyclists_for_switch)
                        else:
                            # All cyclists are assigned, choose a random one (but not the old one)
                            candidates = [c for c in id_tags if c != old_cyclist]
                            if candidates:
                                new_cyclist = random.choice(candidates)
                                # Remove the new cyclist's assignment from their old device
                                if new_cyclist in cyclist_to_device:
                                    old_device = cyclist_to_device[new_cyclist]
                                    # Remove assignment from old device
                                    del cyclist_to_device[new_cyclist]
                            else:
                                # Only one cyclist available, use this one
                                new_cyclist = id_tags[0]
                        
                        # Ensure the same cyclist is not chosen (if more than 1 available)
                        if new_cyclist == old_cyclist and len(id_tags) > 1:
                            # Fallback: Choose another cyclist
                            candidates = [c for c in id_tags if c != old_cyclist]
                            if candidates:
                                new_cyclist = random.choice(candidates)
                                # Remove assignment from old device
                                if new_cyclist in cyclist_to_device:
                                    del cyclist_to_device[new_cyclist]
                        
                        # Set new assignment
                        device_states[device_id] = {
                            'current_cyclist': new_cyclist,
                            'start_time': current_time
                        }
                        cyclist_to_device[new_cyclist] = device_id
                        cyclist_changes.append((device_id, old_cyclist, new_cyclist))
                
                if cyclist_changes:
                    print(f"\n[Iteration {iteration}] Cyclist switch on {len(cyclist_changes)} device(s):")
                    for dev_id, old, new in cyclist_changes:
                        print(f"   {dev_id}: {old} → {new}")
                
                print(f"\n[Iteration {iteration}] Sending data in parallel to {len(devices)} devices...")
                print(f"   Simulated distance: {distance_to_send:.2f} km")
                if max_workers < len(devices):
                    print(f"   🔧 Processing in batches of {max_workers} concurrent connections")
                
                # Parallel execution for all devices (with optional limit)
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    # Create tasks for each device with random time offset
                    future_to_device = {}
                    for device_id in devices:
                        state = device_states[device_id]
                        id_tag = state['current_cyclist']
                        elapsed = current_time - state['start_time']
                        remaining = max(0, CYCLIST_DURATION - elapsed)
                        
                        # Random time offset for more realistic simulation
                        jitter_delay = random.uniform(0, args.send_jitter)
                        
                        def send_with_delay(delay, tag, dev_id, dist):
                            """Sends data with a random delay."""
                            if delay > 0:
                                time.sleep(delay)
                            return send_test_data(tag, dev_id, dist, verbose=False)
                        
                        future = executor.submit(send_with_delay, jitter_delay, id_tag, device_id, distance_to_send)
                        future_to_device[future] = (device_id, id_tag, remaining, jitter_delay)
                    
                    # Wait for all requests and collect results
                    results = []
                    for future in as_completed(future_to_device):
                        device_id, id_tag, remaining, jitter = future_to_device[future]
                        try:
                            success, dev_id, tag_id, message, retry_count = future.result()
                            results.append((success, dev_id, tag_id, remaining, jitter, retry_count, message))
                        except Exception as exc:
                            error_msg = f"❌ Exception for device {device_id}: {exc}"
                            results.append((False, device_id, id_tag, remaining, jitter, 0, error_msg))
                    
                    # Sort results by device for consistent output
                    results.sort(key=lambda x: x[1])  # Sort by device_id
                    
                    # Show results
                    success_count = sum(1 for success, _, _, _, _, _, _ in results if success)
                    total_retries = sum(retry_count for _, _, _, _, _, retry_count, _ in results)
                    print(f"   Results: {success_count}/{len(devices)} successful", end="")
                    if total_retries > 0:
                        print(f" (🔄 {total_retries} retry attempt(s) total)")
                    else:
                        print()
                    for success, dev_id, tag_id, remaining, jitter, retry_count, msg in results:
                        status = "✅" if success else "❌"
                        remaining_str = f" ({int(remaining)}s remaining)" if remaining > 0 else " (Switch due)"
                        jitter_str = f" [⏱️ +{jitter:.2f}s]" if jitter > 0.01 else ""
                        retry_str = f" [🔄 {retry_count}x]" if retry_count > 0 else ""
                        print(f"   {status} {dev_id} → {tag_id}{remaining_str}{jitter_str}{retry_str}: {msg.split(':')[0] if ':' in msg else msg}")
                
                print("-" * 60)
                time.sleep(SEND_INTERVAL)
                
        elif args.id_tag and args.distance is not None and args.device:
            # Scenario: Continuous run with specific values
            print("Starting infinite loop with command line parameters...")
            while True:
                send_test_data(args.id_tag, args.device, args.distance)
                time.sleep(SEND_INTERVAL)
        elif args.id_tag and args.device:
            # Scenario: Continuous run with simulated distance
            print(f"Starting send program. Sending test data every {SEND_INTERVAL} seconds...")
            while True:
                distance_to_send = get_simulated_distance(SEND_INTERVAL, args.wheel_size, args.speed)
                send_test_data(args.id_tag, args.device, distance_to_send)
                time.sleep(SEND_INTERVAL)
        else:
            # Scenario: Continuous run with data from configuration files
            print(f"Starting send program. Sending test data every {SEND_INTERVAL} seconds...")
            print("Reading data from configuration files...")
            
            main_mapping_data = load_json_data(MAIN_MAPPING_FILE)
            if main_mapping_data is None:
                print("Script will be terminated.")
                sys.exit(1)
                
            id_tags = list(main_mapping_data.keys())
            if not id_tags:
                print("No id_tags found in central mapping file. Script will be terminated.")
                sys.exit(1)
            
            print(f"✅ Found ID tags: {id_tags}")
            
            device_ids = load_device_ids(DEVICE_LIST_CONFIG_FILE)
            if not device_ids:
                print("No device_ids found in list. Script will be terminated.")
                sys.exit(1)
            
            print(f"✅ Found device IDs: {device_ids}")
            
            while True:
                # Choose random pair for more realistic testing
                id_tag = random.choice(id_tags)
                device_id = random.choice(device_ids)
                
                distance_to_send = get_simulated_distance(SEND_INTERVAL, args.wheel_size, args.speed)
                send_test_data(id_tag, device_id, distance_to_send)
                time.sleep(SEND_INTERVAL)
    
    # Single run (previous logic)
    elif args.id_tag and args.distance is not None and args.device:
        print(f"Sending specific data via command line.")
        send_test_data(args.id_tag, args.device, args.distance)
        print("Single send operation completed. Program will be terminated.")
        sys.exit(0)
    
    # Error case
    else:
        print("❌ Error: Insufficient arguments. Please specify --id_tag, --distance and --device or use --loop or --get-user-id.")
        parser.print_help()
        sys.exit(1)