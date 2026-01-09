#!/usr/bin/env python3
"""
Test script to fetch device configuration via HTTP.

Usage:
    python test/fetch_device_config.py --device mcc-test-002
    python test/fetch_device_config.py --device mcc-test-002 --pretty
"""

import requests
import argparse
import sys
import json
import os
import configparser
from pathlib import Path

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


def fetch_device_config(device_id: str, pretty: bool = False) -> bool:
    """
    Fetch device configuration from server.
    
    Args:
        device_id: Device name (e.g., 'mcc-test-002')
        pretty: Whether to pretty-print JSON output
    
    Returns:
        True if successful, False otherwise
    """
    url = f"{SERVER_URL}/api/device/config/fetch"
    headers = {
        'X-Api-Key': API_KEY,
        'Content-Type': 'application/json',
    }
    params = {
        'device_id': device_id
    }
    
    print(f"📡 Lade Gerätekonfiguration für '{device_id}'...")
    print(f"   URL: {url}")
    print(f"   Parameter: {params}")
    print()
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        
        if response.status_code == 200:
            try:
                data = response.json()
                
                print("✅ Konfiguration erfolgreich abgerufen!")
                print("=" * 80)
                
                if pretty:
                    print(json.dumps(data, indent=2, ensure_ascii=False))
                else:
                    # Formatierte Ausgabe der wichtigsten Konfigurationswerte
                    print(f"Gerät: {data.get('device_name', 'N/A')}")
                    print(f"Konfiguration vorhanden: {data.get('config_exists', False)}")
                    
                    if data.get('config'):
                        config_data = data['config']
                        print("\n📋 Gerätekonfiguration:")
                        print("-" * 80)
                        
                        # Basis-Konfiguration
                        if 'device_name' in config_data:
                            print(f"  Gerätename: {config_data['device_name']}")
                        if 'default_id_tag' in config_data:
                            print(f"  Standard-ID-Tag: {config_data['default_id_tag']}")
                        if 'send_interval_seconds' in config_data:
                            print(f"  Sendeintervall: {config_data['send_interval_seconds']} Sekunden")
                        if 'debug_mode' in config_data:
                            print(f"  Debug-Modus: {config_data['debug_mode']}")
                        if 'test_mode' in config_data:
                            print(f"  Test-Modus: {config_data['test_mode']}")
                        if 'deep_sleep_time_seconds' in config_data:
                            print(f"  Deep-Sleep-Zeit: {config_data['deep_sleep_time_seconds']} Sekunden")
                        if 'wheel_size_inches' in config_data:
                            print(f"  Radgröße: {config_data['wheel_size_inches']} Zoll")
                        if 'server_url' in config_data:
                            print(f"  Server-URL: {config_data['server_url']}")
                        
                        # WLAN-Konfiguration
                        if 'wlan_ssid' in config_data:
                            print(f"\n📶 WLAN-Konfiguration:")
                            print(f"  SSID: {config_data['wlan_ssid']}")
                            if 'wlan_password' in config_data:
                                password_display = '*' * len(config_data['wlan_password']) if config_data['wlan_password'] else '(leer)'
                                print(f"  Passwort: {password_display}")
                        
                        # Firmware-Informationen
                        if 'firmware_version' in config_data:
                            print(f"\n💾 Firmware:")
                            print(f"  Version: {config_data.get('firmware_version', 'N/A')}")
                            if 'firmware_name' in config_data:
                                print(f"  Name: {config_data['firmware_name']}")
                            if 'firmware_checksum' in config_data:
                                print(f"  MD5 Checksum: {config_data['firmware_checksum']}")
                            if 'firmware_download_url' in config_data:
                                print(f"  Download-URL: {config_data['firmware_download_url']}")
                        
                        # API-Key-Informationen (nur wenn vorhanden)
                        if 'device_specific_api_key' in config_data and config_data['device_specific_api_key']:
                            api_key_display = config_data['device_specific_api_key'][:10] + '...' if len(config_data['device_specific_api_key']) > 10 else config_data['device_specific_api_key']
                            print(f"\n🔑 API-Key:")
                            print(f"  Geräte-spezifischer API-Key: {api_key_display}")
                            if 'api_key_rotation_enabled' in config_data:
                                print(f"  Rotation aktiviert: {config_data['api_key_rotation_enabled']}")
                            if 'api_key_rotation_interval_days' in config_data:
                                print(f"  Rotationsintervall: {config_data['api_key_rotation_interval_days']} Tage")
                            if 'api_key_last_rotated' in config_data:
                                print(f"  Zuletzt rotiert: {config_data['api_key_last_rotated']}")
                        
                        # Weitere Konfigurationswerte
                        print(f"\n📝 Weitere Konfigurationswerte:")
                        for key, value in config_data.items():
                            if key not in ['device_name', 'default_id_tag', 'send_interval_seconds', 
                                          'debug_mode', 'test_mode', 'deep_sleep_time_seconds', 
                                          'wheel_size_inches', 'server_url', 'wlan_ssid', 'wlan_password',
                                          'firmware_version', 'firmware_name', 'firmware_checksum', 
                                          'firmware_download_url', 'device_specific_api_key',
                                          'api_key_rotation_enabled', 'api_key_rotation_interval_days',
                                          'api_key_last_rotated']:
                                print(f"  {key}: {value}")
                    
                    elif data.get('message'):
                        print(f"\nℹ️  {data['message']}")
                    
                    print("\n" + "=" * 80)
                    print("\n💡 Tipp: Verwenden Sie --pretty für vollständige JSON-Ausgabe")
                
                return True
                
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
                print(f"❌ Fehler: Gerät oder Konfiguration nicht gefunden (404)")
            return False
            
        elif response.status_code == 400:
            try:
                error_data = response.json()
                error_msg = error_data.get('error', 'Unbekannter Fehler')
                print(f"❌ Fehler: {error_msg} (400)")
            except:
                print(f"❌ Fehler: Ungültige Anfrage (400)")
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
        print(f"❌ Fehler: Zeitüberschreitung beim Abrufen der Konfiguration")
        return False
    except requests.exceptions.ConnectionError as e:
        print(f"❌ Fehler: Verbindungsfehler - {e}")
        print(f"   Bitte prüfen Sie, ob der Server unter {SERVER_URL} erreichbar ist.")
        return False
    except Exception as e:
        print(f"❌ Fehler: {type(e).__name__}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Ruft die Gerätekonfiguration für ein Gerät über HTTP ab."
    )
    parser.add_argument(
        '--device',
        type=str,
        required=True,
        help="Gerätename (z.B. 'mcc-test-002')"
    )
    parser.add_argument(
        '--pretty',
        action='store_true',
        help="Vollständige JSON-Ausgabe (pretty-printed)"
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
    
    success = fetch_device_config(args.device, args.pretty)
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()

