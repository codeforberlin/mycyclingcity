#!/usr/bin/env python3
"""
Test script to download firmware image for a device via HTTP.

Usage:
    python test/download_firmware.py --device mcc-test-02
    python test/download_firmware.py --device mcc-test-02 --output firmware.bin
"""

import requests
import argparse
import sys
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


def download_firmware(device_id: str, output_file: str = None) -> bool:
    """
    Download firmware image for a device.
    
    Args:
        device_id: Device name (e.g., 'mcc-test-02')
        output_file: Optional output filename. If None, uses firmware version from headers.
    
    Returns:
        True if successful, False otherwise
    """
    url = f"{SERVER_URL}/api/device/firmware/download"
    headers = {
        'X-Api-Key': API_KEY,
    }
    params = {
        'device_id': device_id
    }
    
    print(f"📡 Lade Firmware für Gerät '{device_id}'...")
    print(f"   URL: {url}")
    print(f"   Parameter: {params}")
    
    try:
        response = requests.get(url, headers=headers, params=params, stream=True, timeout=30)
        
        if response.status_code == 200:
            # Get firmware metadata from headers
            firmware_version = response.headers.get('X-Firmware-Version', 'unknown')
            firmware_checksum = response.headers.get('X-Firmware-Checksum', '')
            firmware_size = response.headers.get('X-Firmware-Size', '0')
            
            print(f"✅ Firmware gefunden!")
            print(f"   Version: {firmware_version}")
            print(f"   Größe: {firmware_size} Bytes")
            if firmware_checksum:
                print(f"   MD5 Checksum: {firmware_checksum}")
            
            # Determine output filename
            if output_file is None:
                output_file = f"firmware_{device_id}_{firmware_version}.bin"
            
            # Download file
            total_size = int(firmware_size) if firmware_size.isdigit() else 0
            downloaded = 0
            
            print(f"💾 Speichere Firmware in '{output_file}'...")
            
            with open(output_file, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            percent = (downloaded / total_size) * 100
                            print(f"\r   Fortschritt: {downloaded}/{total_size} Bytes ({percent:.1f}%)", end='', flush=True)
            
            print(f"\n✅ Firmware erfolgreich heruntergeladen!")
            print(f"   Datei: {output_file}")
            print(f"   Größe: {downloaded} Bytes")
            
            # Verify file size
            file_size = os.path.getsize(output_file)
            if total_size > 0 and file_size != total_size:
                print(f"⚠️  Warnung: Dateigröße stimmt nicht überein (erwartet: {total_size}, erhalten: {file_size})")
            else:
                print(f"✓ Dateigröße verifiziert: {file_size} Bytes")
            
            return True
            
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
                print(f"❌ Fehler: Gerät oder Firmware nicht gefunden (404)")
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
        print(f"❌ Fehler: Zeitüberschreitung beim Herunterladen")
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
        description="Lädt ein Firmware-Image für ein Gerät über HTTP herunter."
    )
    parser.add_argument(
        '--device',
        type=str,
        required=True,
        help="Gerätename (z.B. 'mcc-test-02')"
    )
    parser.add_argument(
        '--output', '-o',
        type=str,
        default=None,
        help="Ausgabedatei (Standard: firmware_<device>_<version>.bin)"
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
    
    success = download_firmware(args.device, args.output)
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()

