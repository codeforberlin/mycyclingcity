# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    cleanup_old_tables.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).
#
"""
Script zum manuellen Löschen alter Tabellen nach erfolgreichem Test.

Nutzung:
    python utils/cleanup_old_tables.py --version 1.0.0 --dry-run
    python utils/cleanup_old_tables.py --version 1.0.0 --confirm
"""

import os
import sys
import argparse
from pathlib import Path
from typing import List, Optional

# Django Setup
def setup_django(project_dir: Path) -> None:
    """Setup Django environment."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    sys.path.insert(0, str(project_dir))
    
    import django
    django.setup()


def get_tables_for_version(version: str) -> List[str]:
    """
    Ermittelt welche Tabellen zu einer bestimmten Version gehören.
    
    Dies ist eine vereinfachte Implementierung. In einer vollständigen
    Implementierung würde man:
    - Die Migrationen der alten Version analysieren
    - Eine Mapping-Datei verwenden
    - Oder die Django-Modelle der alten Version prüfen
    
    Args:
        version: Version deren Tabellen gelöscht werden sollen
    
    Returns:
        Liste von Tabellennamen
    """
    # TODO: Diese Funktion sollte erweitert werden, um tatsächlich
    # die Tabellen der alten Version zu identifizieren.
    # Für jetzt: Manuelle Liste oder Analyse der Migrationen
    
    # Beispiel: Leere Liste - muss vom Admin manuell gefüllt werden
    # oder durch Analyse der Migrationen bestimmt werden
    return []


def get_all_tables() -> List[str]:
    """Holt alle Tabellennamen aus der Datenbank."""
    from django.db import connection
    
    with connection.cursor() as cursor:
        if connection.vendor == 'sqlite':
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        elif connection.vendor == 'postgresql':
            cursor.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            )
        else:
            raise ValueError(f"Unsupported database vendor: {connection.vendor}")
        
        return [row[0] for row in cursor.fetchall()]


def cleanup_old_tables(version: str, dry_run: bool = True, tables: Optional[List[str]] = None) -> bool:
    """
    Löscht Tabellen einer alten Version.
    
    Args:
        version: Version deren Tabellen gelöscht werden sollen
        dry_run: Wenn True, nur anzeigen, nicht löschen
        tables: Liste von Tabellennamen zum Löschen (optional)
    
    Returns:
        True wenn erfolgreich
    """
    from django.db import connection
    
    # Wenn keine Tabellen angegeben, versuche sie automatisch zu ermitteln
    if tables is None:
        tables = get_tables_for_version(version)
    
    # Wenn immer noch keine Tabellen, zeige alle an
    if not tables:
        print(f"Warnung: Keine Tabellen für Version {version} gefunden.")
        print("Verwenden Sie --tables um spezifische Tabellen anzugeben.")
        all_tables = get_all_tables()
        print(f"\nVerfügbare Tabellen in der Datenbank:")
        for table in sorted(all_tables):
            print(f"  - {table}")
        return False
    
    if dry_run:
        print(f"DRY RUN: Folgende Tabellen würden gelöscht werden (Version {version}):")
        for table in tables:
            print(f"  - {table}")
        print(f"\nGesamt: {len(tables)} Tabelle(n)")
        return True
    
    # Bestätigung erforderlich
    print(f"WARNUNG: Folgende Tabellen werden gelöscht (Version {version}):")
    for table in tables:
        print(f"  - {table}")
    print(f"\nGesamt: {len(tables)} Tabelle(n)")
    
    confirm = input("\nWirklich fortfahren? (yes/no): ")
    if confirm.lower() != 'yes':
        print("Abgebrochen.")
        return False
    
    # Tabellen löschen
    from django.db import connection
    
    deleted_count = 0
    with connection.cursor() as cursor:
        for table in tables:
            try:
                if connection.vendor == 'sqlite':
                    cursor.execute(f"DROP TABLE IF EXISTS {table};")
                elif connection.vendor == 'postgresql':
                    cursor.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE;')
                else:
                    raise ValueError(f"Unsupported database vendor: {connection.vendor}")
                
                print(f"✓ Tabelle {table} gelöscht")
                deleted_count += 1
            except Exception as e:
                print(f"✗ Fehler beim Löschen von {table}: {e}")
    
    print(f"\n✓ {deleted_count} von {len(tables)} Tabelle(n) erfolgreich gelöscht")
    return True


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Löscht alte Tabellen einer bestimmten Version nach erfolgreichem Test'
    )
    parser.add_argument(
        '--version',
        type=str,
        required=True,
        help='Version deren Tabellen gelöscht werden sollen (z.B. 1.0.0)'
    )
    parser.add_argument(
        '--project-dir',
        type=str,
        default='.',
        help='Project root directory (default: current directory)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        default=True,
        help='Nur anzeigen, nicht löschen (default: True)'
    )
    parser.add_argument(
        '--confirm',
        action='store_true',
        help='Bestätigt das Löschen (überschreibt --dry-run)'
    )
    parser.add_argument(
        '--tables',
        type=str,
        nargs='+',
        help='Liste von Tabellennamen zum Löschen (optional)'
    )
    
    args = parser.parse_args()
    
    # Default to project root (parent of utils/)
    if args.project_dir == '.':
        project_dir = Path(__file__).parent.parent.resolve()
    else:
        project_dir = Path(args.project_dir).resolve()
    
    # Setup Django
    try:
        setup_django(project_dir)
    except Exception as e:
        print(f"Fehler beim Setup von Django: {e}")
        return 1
    
    # Determine dry_run
    dry_run = args.dry_run and not args.confirm
    
    # Run cleanup
    success = cleanup_old_tables(
        version=args.version,
        dry_run=dry_run,
        tables=args.tables
    )
    
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
