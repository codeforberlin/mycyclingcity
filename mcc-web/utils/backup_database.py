# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    backup_database.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
"""
Automated database backup script for MCC-Web production.

This script creates timestamped backups of the SQLite database
and optionally rotates old backups.

Usage:
    python utils/backup_database.py
    python utils/backup_database.py --keep-days 7
    python utils/backup_database.py --compress
"""

import os
import sys
import shutil
import argparse
import gzip
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional


def get_database_path(project_dir: Path) -> Optional[Path]:
    """
    Get the database path from Django settings.
    
    Args:
        project_dir: Project root directory
    
    Returns:
        Path to database file, or None if not found
    """
    try:
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
        sys.path.insert(0, str(project_dir))
        
        import django
        django.setup()
        
        from django.conf import settings
        db_path = Path(settings.DATABASES['default']['NAME'])
        return db_path
    except Exception:
        return None


def create_backup(
    db_path: Path,
    backup_dir: Path,
    compress: bool = False
) -> Optional[Path]:
    """
    Create a backup of the database.
    
    Args:
        db_path: Path to database file
        backup_dir: Directory for backups
        compress: Whether to compress the backup
    
    Returns:
        Path to backup file, or None if failed
    """
    if not db_path.exists():
        print(f"Error: Database file not found: {db_path}")
        return None
    
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_filename = f"db_backup_{timestamp}.sqlite3"
    backup_path = backup_dir / backup_filename
    
    try:
        # Copy database file
        shutil.copy2(db_path, backup_path)
        
        # Also backup WAL and SHM files if they exist
        wal_path = Path(str(db_path) + '-wal')
        shm_path = Path(str(db_path) + '-shm')
        
        if wal_path.exists():
            shutil.copy2(wal_path, backup_dir / f"{backup_filename}-wal")
        if shm_path.exists():
            shutil.copy2(shm_path, backup_dir / f"{backup_filename}-shm")
        
        # Compress if requested
        if compress:
            compressed_path = backup_path.with_suffix('.sqlite3.gz')
            with open(backup_path, 'rb') as f_in:
                with gzip.open(compressed_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            backup_path.unlink()  # Remove uncompressed file
            backup_path = compressed_path
        
        size_mb = backup_path.stat().st_size / (1024 * 1024)
        print(f"✓ Backup created: {backup_path} ({size_mb:.2f} MB)")
        return backup_path
    except Exception as e:
        print(f"✗ Error creating backup: {e}")
        return None


def rotate_backups(backup_dir: Path, keep_days: int = 7) -> int:
    """
    Delete backups older than specified days.
    
    Args:
        backup_dir: Directory containing backups
        keep_days: Number of days to keep backups
    
    Returns:
        Number of backups deleted
    """
    if not backup_dir.exists():
        return 0
    
    cutoff_date = datetime.now() - timedelta(days=keep_days)
    deleted_count = 0
    
    for backup_file in backup_dir.glob('db_backup_*'):
        try:
            # Extract timestamp from filename
            # Format: db_backup_YYYYMMDD_HHMMSS.sqlite3[.gz]
            parts = backup_file.stem.split('_')
            if len(parts) >= 3:
                date_str = parts[2]  # YYYYMMDD
                time_str = parts[3] if len(parts) > 3 else '000000'  # HHMMSS
                timestamp_str = f"{date_str}_{time_str}"
                file_date = datetime.strptime(timestamp_str, '%Y%m%d_%H%M%S')
                
                if file_date < cutoff_date:
                    backup_file.unlink()
                    # Also delete associated WAL/SHM files
                    for ext in ['-wal', '-shm']:
                        associated = backup_dir / f"{backup_file.stem}{ext}"
                        if associated.exists():
                            associated.unlink()
                    deleted_count += 1
                    print(f"  Deleted old backup: {backup_file.name}")
        except Exception as e:
            print(f"  Warning: Could not process {backup_file.name}: {e}")
    
    return deleted_count


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Create database backup for MCC-Web'
    )
    parser.add_argument(
        '--project-dir',
        type=str,
        default='.',
        help='Project root directory (default: current directory)'
    )
    parser.add_argument(
        '--backup-dir',
        type=str,
        default=None,
        help='Backup directory (default: project_dir/backups)'
    )
    parser.add_argument(
        '--compress',
        action='store_true',
        help='Compress backup with gzip'
    )
    parser.add_argument(
        '--keep-days',
        type=int,
        default=7,
        help='Keep backups for this many days (default: 7)'
    )
    parser.add_argument(
        '--rotate-only',
        action='store_true',
        help='Only rotate old backups, do not create new one'
    )
    
    args = parser.parse_args()
    
    # Default to project root (parent of utils/)
    if args.project_dir == '.':
        project_dir = Path(__file__).parent.parent.resolve()
    else:
        project_dir = Path(args.project_dir).resolve()
    
    # Bestimme Standard-Backup-Verzeichnis
    if args.backup_dir:
        backup_dir = Path(args.backup_dir)
    else:
        # Prüfe ob wir in Produktion sind (Pfad enthält /data/appl/mcc)
        if '/data/appl/mcc' in str(project_dir) or os.environ.get('MCC_ENV') == 'production':
            backup_dir = Path('/data/var/mcc/backups')
        else:
            # Entwicklung: lokales Verzeichnis
            backup_dir = project_dir / 'backups'
    
    print("MCC-Web Database Backup")
    print("=" * 50)
    
    # Get database path
    db_path = get_database_path(project_dir)
    if not db_path:
        print("Error: Could not determine database path")
        return 1
    
    print(f"Database: {db_path}")
    print(f"Backup directory: {backup_dir}")
    
    # Create backup
    if not args.rotate_only:
        backup_path = create_backup(db_path, backup_dir, compress=args.compress)
        if not backup_path:
            return 1
    
    # Rotate old backups
    if args.keep_days > 0:
        print(f"\nRotating backups (keeping {args.keep_days} days)...")
        deleted = rotate_backups(backup_dir, keep_days=args.keep_days)
        print(f"Deleted {deleted} old backup(s)")
    
    print("\n✓ Backup operation completed")
    return 0


if __name__ == '__main__':
    sys.exit(main())

