# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    send_device_config_report.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
"""
Test script to send device configuration report with slight differences.

Usage:
    python test/send_device_config_report.py --device mcc-test-002
    python test/send_device_config_report.py --device mcc-test-002 --check-diffs
"""

import requests
import argparse
import sys
import json
import os
import configparser
from pathlib import Path
from datetime import datetime

# Load environment variables from .env file
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

# Load configuration
BASE_DIR = Path(__file__).parent
CONFIG_FILE = BASE_DIR / 'mcc_api_test.cfg'

if not CONFIG_FILE.exists():
    print(f"❌ Fehler: Konfigurationsdatei '{CONFIG_FILE}' nicht gefunden.")
    sys.exit(1)

config = configparser.ConfigParser()
config.read(CONFIG_FILE)
GENERAL_SETTINGS = config['general']

# Load configuration: .env takes priority, then config file
SERVER_IP = os.getenv('TEST_SERVER_IP') or GENERAL_SETTINGS.get('server_ip')
SERVER_PORT = int(os.getenv('TEST_SERVER_PORT', 0)) or GENERAL_SETTINGS.getint('server_port')
API_KEY = os.getenv('MCC_APP_API_KEY') or GENERAL_SETTINGS.get('api_key')
if not API_KEY:
    print("❌ Error: API key not found. Please set MCC_APP_API_KEY in .env file or api_key in config file.")
    sys.exit(1)

SERVER_URL = f"http://{SERVER_IP}:{SERVER_PORT}"


def fetch_current_config(device_id: str) -> dict:
    """Fetch current server configuration for comparison."""
    url = f"{SERVER_URL}/api/device/config/fetch"
    headers = {
        'X-Api-Key': API_KEY,
        'Content-Type': 'application/json',
    }
    params = {'device_id': device_id}
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return data.get('config', {})
    except Exception as e:
        print(f"⚠️  Warnung: Konnte aktuelle Konfiguration nicht abrufen: {e}")
    
    return {}


def create_modified_config(base_config: dict) -> dict:
    """Create a slightly modified configuration for testing."""
    # Only include expected fields
    expected_fields = [
        'device_name', 'default_id_tag', 'send_interval_seconds', 'server_url',
        'wifi_ssid', 'wifi_password', 'debug_mode', 'test_mode',
        'deep_sleep_seconds', 'wheel_size', 'device_api_key'
    ]
    
    modified = {k: v for k, v in base_config.items() if k in expected_fields}
    
    # Make some slight modifications
    if 'send_interval_seconds' in modified:
        modified['send_interval_seconds'] = modified.get('send_interval_seconds', 60) + 10  # +10 seconds
    
    if 'debug_mode' in modified:
        modified['debug_mode'] = not modified.get('debug_mode', False)  # Toggle debug mode
    
    if 'deep_sleep_seconds' in modified:
        modified['deep_sleep_seconds'] = modified.get('deep_sleep_seconds', 300) - 50  # -50 seconds
    
    if 'wheel_size' in modified:
        # Change wheel size (in mm): 2075 (26") -> 2232 (28") -> 1916 (24") -> 2075 (26")
        current_size = modified.get('wheel_size', 2075.0)
        if abs(current_size - 2075.0) < 10:  # 26 Zoll = 2075 mm
            modified['wheel_size'] = 2232.0  # 28 Zoll = 2232 mm
        elif abs(current_size - 2232.0) < 10:  # 28 Zoll = 2232 mm
            modified['wheel_size'] = 1916.0  # 24 Zoll = 1916 mm
        else:
            modified['wheel_size'] = 2075.0  # 26 Zoll = 2075 mm
    
    return modified


def send_config_report(device_id: str, device_config: dict, check_diffs: bool = False) -> bool:
    """
    Send device configuration report to server.
    
    Args:
        device_id: Device name (e.g., 'mcc-test-002')
        device_config: Device configuration dictionary
        check_diffs: Whether to check for differences after sending
    
    Returns:
        True if successful, False otherwise
    """
    url = f"{SERVER_URL}/api/device/config/report"
    headers = {
        'X-Api-Key': API_KEY,
        'Content-Type': 'application/json',
    }
    
    payload = {
        'device_id': device_id,
        'config': device_config
    }
    
    print(f"📤 Sende Gerätekonfiguration für '{device_id}'...")
    print(f"   URL: {url}")
    print(f"\n📋 Zu sendende Konfiguration:")
    print("-" * 80)
    for key, value in sorted(device_config.items()):
        if key in ['wifi_password', 'device_api_key']:
            display_value = '*' * len(str(value)) if value else '(leer)'
            print(f"  {key}: {display_value}")
        else:
            print(f"  {key}: {value}")
    print("-" * 80)
    print()
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        
        if response.status_code == 200:
            try:
                data = response.json()
                
                print("✅ Konfiguration erfolgreich gesendet!")
                print("=" * 80)
                
                if data.get('success'):
                    print(f"Status: {data.get('message', 'Erfolgreich')}")
                    
                    if 'differences' in data:
                        diff_count = len(data['differences'])
                        print(f"\n🔍 Unterschiede erkannt: {diff_count}")
                        
                        if diff_count > 0:
                            print("\n📊 Unterschiede-Details:")
                            print("-" * 80)
                            for i, diff in enumerate(data['differences'], 1):
                                field = diff.get('field', 'unknown')
                                server_val = diff.get('server_value', 'N/A')
                                device_val = diff.get('device_value', 'N/A')
                                print(f"\n  {i}. Feld: {field}")
                                print(f"     Server-Wert: {server_val}")
                                print(f"     Geräte-Wert: {device_val}")
                            print("-" * 80)
                        else:
                            print("✓ Keine Unterschiede - Konfiguration stimmt überein!")
                    
                    if check_diffs:
                        print("\n🔍 Prüfe Berichte in der Datenbank...")
                        check_database_diffs(device_id)
                    
                    return True
                else:
                    print(f"⚠️  Antwort: {data}")
                    return False
                    
            except json.JSONDecodeError:
                print(f"❌ Fehler: Ungültige JSON-Antwort")
                print(f"   Antwort: {response.text[:500]}")
                return False
                
        elif response.status_code == 403:
            print(f"❌ Fehler: Ungültiger API-Key (403)")
            print(f"   Bitte prüfen Sie den API-Key in der Konfigurationsdatei.")
            return False
            
        elif response.status_code == 404:
            try:
                error_data = response.json()
                error_msg = error_data.get('error', 'Unbekannter Fehler')
                print(f"❌ Fehler: {error_msg} (404)")
            except:
                print(f"❌ Fehler: Gerät nicht gefunden (404)")
            return False
            
        elif response.status_code == 400:
            try:
                error_data = response.json()
                error_msg = error_data.get('error', 'Unbekannter Fehler')
                print(f"❌ Fehler: {error_msg} (400)")
            except:
                print(f"❌ Fehler: Ungültige Anfrage (400)")
                print(f"   Antwort: {response.text[:200]}")
            return False
            
        else:
            print(f"❌ Fehler: HTTP {response.status_code}")
            try:
                error_data = response.json()
                error_msg = error_data.get('error', 'Unbekannter Fehler')
                print(f"   Nachricht: {error_msg}")
            except:
                print(f"   Antwort: {response.text[:200]}")
            return False
            
    except requests.exceptions.Timeout:
        print(f"❌ Fehler: Zeitüberschreitung beim Senden der Konfiguration")
        return False
    except requests.exceptions.ConnectionError as e:
        print(f"❌ Fehler: Verbindungsfehler - {e}")
        print(f"   Bitte prüfen Sie, ob der Server unter {SERVER_URL} erreichbar ist.")
        return False
    except Exception as e:
        print(f"❌ Fehler: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


def check_database_diffs(device_id: str):
    """Check for configuration differences in the database."""
    try:
        import subprocess
        result = subprocess.run(
            [
                'python', 'manage.py', 'shell', '-c',
                f"""
from iot.models import Device, DeviceConfigurationReport, DeviceConfigurationDiff
device = Device.objects.get(name='{device_id}')
reports = DeviceConfigurationReport.objects.filter(device=device).order_by('-created_at')[:1]
if reports:
    report = reports[0]
    print(f"Neuester Bericht: {{report.created_at}}")
    diffs = DeviceConfigurationDiff.objects.filter(report=report, is_resolved=False)
    print(f"Ungelöste Unterschiede: {{diffs.count()}}")
    for diff in diffs:
        print(f"  - {{diff.field_name}}: Server='{{diff.server_value}}', Gerät='{{diff.device_value}}'")
else:
    print("Keine Berichte gefunden")
"""
            ],
            cwd=BASE_DIR.parent,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            print(result.stdout)
        else:
            print(f"⚠️  Konnte Datenbank nicht prüfen: {result.stderr}")
    except Exception as e:
        print(f"⚠️  Fehler beim Prüfen der Datenbank: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Sendet eine Gerätekonfiguration mit leichten Abweichungen zum Testen."
    )
    parser.add_argument(
        '--device',
        type=str,
        required=True,
        help="Gerätename (z.B. 'mcc-test-002')"
    )
    parser.add_argument(
        '--check-diffs',
        action='store_true',
        help="Prüft die Datenbank auf Unterschiede nach dem Senden"
    )
    parser.add_argument(
        '--use-current',
        action='store_true',
        help="Verwendet die aktuelle Server-Konfiguration als Basis"
    )
    parser.add_argument(
        '--server',
        type=str,
        default=None,
        help="Server-URL (überschreibt Konfiguration)"
    )
    
    args = parser.parse_args()
    
    # Override server URL if provided
    global SERVER_URL
    if args.server:
        SERVER_URL = args.server
    
    # Get base configuration
    if args.use_current:
        print("📥 Lade aktuelle Server-Konfiguration...")
        base_config = fetch_current_config(args.device)
        if not base_config:
            print("❌ Konnte aktuelle Konfiguration nicht abrufen.")
            sys.exit(1)
        print("✓ Aktuelle Konfiguration geladen\n")
    else:
        # Use a test configuration
        base_config = {
            'device_name': args.device,
            'default_id_tag': 'test-tag-001',
            'send_interval_seconds': 60,
            'server_url': '',
            'wifi_ssid': '',
            'wifi_password': '',
            'debug_mode': False,
            'test_mode': False,
            'deep_sleep_seconds': 300,
            'wheel_size': 2075.0,  # 26 Zoll = 2075 mm
            'device_api_key': '',
        }
    
    # Create modified configuration
    modified_config = create_modified_config(base_config)
    
    # Show what changed
    print("🔄 Änderungen gegenüber Server-Konfiguration:")
    print("-" * 80)
    for key in modified_config:
        if key not in base_config or modified_config[key] != base_config.get(key):
            old_val = base_config.get(key, '(nicht gesetzt)')
            new_val = modified_config[key]
            print(f"  {key}: {old_val} → {new_val}")
    print("-" * 80)
    print()
    
    # Send configuration
    success = send_config_report(args.device, modified_config, args.check_diffs)
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()

