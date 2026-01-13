# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    send_heartbeat.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
"""
Test script to simulate device heartbeats and verify health status tracking.

Usage:
    python test/send_heartbeat.py --device mcc-test-002
    python test/send_heartbeat.py --device mcc-test-002 --interval 30 --count 5
    python test/send_heartbeat.py --device mcc-test-002 --check-health
"""

import requests
import argparse
import sys
import json
import time
import os
import configparser
from pathlib import Path
from datetime import datetime

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


def send_heartbeat(device_id: str, metadata: dict = None) -> bool:
    """
    Send heartbeat signal from device to server.
    
    Args:
        device_id: Device name (e.g., 'mcc-test-002')
        metadata: Optional metadata dictionary
    
    Returns:
        True if successful, False otherwise
    """
    url = f"{SERVER_URL}/api/device/heartbeat"
    headers = {
        'X-Api-Key': API_KEY,
        'Content-Type': 'application/json',
    }
    
    payload = {
        'device_id': device_id,
    }
    
    if metadata:
        payload['metadata'] = metadata
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        
        if response.status_code == 200:
            try:
                data = response.json()
                if data.get('success'):
                    print(f"✅ Heartbeat gesendet: {data.get('message', 'Erfolgreich')}")
                    return True
                else:
                    print(f"⚠️  Antwort: {data}")
                    return False
            except json.JSONDecodeError:
                print(f"⚠️  Ungültige JSON-Antwort: {response.text[:200]}")
                return False
                
        elif response.status_code == 403:
            print(f"❌ Fehler: Ungültiger API-Key (403)")
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
        print(f"❌ Fehler: Zeitüberschreitung beim Senden des Heartbeats")
        return False
    except requests.exceptions.ConnectionError as e:
        print(f"❌ Fehler: Verbindungsfehler - {e}")
        return False
    except Exception as e:
        print(f"❌ Fehler: {type(e).__name__}: {e}")
        return False


def check_health_status(device_id: str):
    """Check device health status from database."""
    try:
        import subprocess
        result = subprocess.run(
            [
                'python', 'manage.py', 'shell', '-c',
                f"""
from iot.models import Device, DeviceHealth, DeviceAuditLog
from django.utils import timezone
from datetime import timedelta

device = Device.objects.get(name='{device_id}')
health, created = DeviceHealth.objects.get_or_create(device=device)

print("=" * 80)
print(f"📊 Health-Status für Gerät: {{device.name}}")
print("=" * 80)
print(f"Status: {{health.status}}")
print(f"Letzter Heartbeat: {{health.last_heartbeat}}")
print(f"Heartbeat-Intervall: {{health.heartbeat_interval_seconds}} Sekunden")
print(f"Offline-Schwelle: {{health.offline_threshold_seconds}} Sekunden")
print(f"Konsekutive Fehler: {{health.consecutive_failures}}")
if health.last_error_message:
    print(f"Letzte Fehlermeldung: {{health.last_error_message}}")

# Check if device is offline
is_offline = health.is_offline()
print(f"Gerät offline: {{is_offline}}")

# Show recent audit logs
print(f"\\n📝 Letzte Audit-Log-Einträge (Heartbeat):")
audit_logs = DeviceAuditLog.objects.filter(
    device=device,
    action='heartbeat_received'
).order_by('-created_at')[:5]

if audit_logs.exists():
    for log in audit_logs:
        print(f"  - {{log.created_at.strftime('%Y-%m-%d %H:%M:%S')}}: {{log.action}}")
        if log.details:
            print(f"    Details: {{log.details}}")
else:
    print("  Keine Heartbeat-Audit-Logs gefunden")

print("=" * 80)
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
            print(f"⚠️  Konnte Health-Status nicht prüfen: {result.stderr}")
    except Exception as e:
        print(f"⚠️  Fehler beim Prüfen des Health-Status: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Simuliert Heartbeat-Signale von einem Gerät und prüft den Health-Status."
    )
    parser.add_argument(
        '--device',
        type=str,
        required=True,
        help="Gerätename (z.B. 'mcc-test-002')"
    )
    parser.add_argument(
        '--count',
        type=int,
        default=1,
        help="Anzahl der Heartbeats (Standard: 1)"
    )
    parser.add_argument(
        '--interval',
        type=float,
        default=5.0,
        help="Intervall zwischen Heartbeats in Sekunden (Standard: 5.0)"
    )
    parser.add_argument(
        '--check-health',
        action='store_true',
        help="Prüft den Health-Status nach dem Senden"
    )
    parser.add_argument(
        '--metadata',
        type=str,
        default=None,
        help="Zusätzliche Metadaten als JSON-String (z.B. '{\"battery\": 85, \"signal\": -65}')"
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
    
    # Parse metadata if provided
    metadata = None
    if args.metadata:
        try:
            metadata = json.loads(args.metadata)
        except json.JSONDecodeError:
            print(f"❌ Fehler: Ungültiges JSON-Format für --metadata")
            sys.exit(1)
    
    print(f"📡 Sende Heartbeats für Gerät '{args.device}'...")
    print(f"   Anzahl: {args.count}")
    print(f"   Intervall: {args.interval} Sekunden")
    if metadata:
        print(f"   Metadaten: {metadata}")
    print()
    
    success_count = 0
    for i in range(args.count):
        if i > 0:
            time.sleep(args.interval)
        
        print(f"[{i+1}/{args.count}] ", end='', flush=True)
        if send_heartbeat(args.device, metadata):
            success_count += 1
    
    print()
    print(f"✅ Erfolgreich gesendet: {success_count}/{args.count}")
    
    if args.check_health:
        print()
        check_health_status(args.device)
    
    sys.exit(0 if success_count == args.count else 1)


if __name__ == '__main__':
    main()

