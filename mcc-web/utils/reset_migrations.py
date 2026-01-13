# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    reset_migrations.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
"""
Reset or squash database migrations for a clean production setup.

This script provides two options:
1. Squash migrations (recommended) - Combines migrations while preserving history
2. Reset migrations - Deletes all migrations and regenerates from models

WARNING: Only use this if you can recreate your development database!
"""

import os
import sys
import shutil
import subprocess
import argparse
from pathlib import Path
from typing import List, Optional


class Colors:
    """ANSI color codes for terminal output."""
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    RESET = '\033[0m'


def print_success(message: str) -> None:
    """Print a success message."""
    print(f"{Colors.GREEN}✓{Colors.RESET} {message}")


def print_warning(message: str) -> None:
    """Print a warning message."""
    print(f"{Colors.YELLOW}⚠{Colors.RESET} {message}")


def print_error(message: str) -> None:
    """Print an error message."""
    print(f"{Colors.RED}✗{Colors.RESET} {message}")


def print_info(message: str) -> None:
    """Print an info message."""
    print(f"{Colors.BLUE}ℹ{Colors.RESET} {message}")


def find_migration_directories(project_dir: Path) -> List[Path]:
    """
    Find all migration directories in the project.
    
    Args:
        project_dir: Project root directory
    
    Returns:
        List of migration directory paths
    """
    migration_dirs = []
    
    for app_dir in project_dir.iterdir():
        if app_dir.is_dir() and not app_dir.name.startswith('.'):
            migrations_dir = app_dir / 'migrations'
            if migrations_dir.exists() and migrations_dir.is_dir():
                migration_dirs.append(migrations_dir)
    
    return migration_dirs


def backup_migrations(migration_dirs: List[Path], backup_dir: Path) -> bool:
    """
    Backup migration files before deletion.
    
    Args:
        migration_dirs: List of migration directories
        backup_dir: Directory to store backups
    
    Returns:
        True if backup succeeded, False otherwise
    """
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        for migrations_dir in migration_dirs:
            app_name = migrations_dir.parent.name
            app_backup_dir = backup_dir / app_name
            app_backup_dir.mkdir(parents=True, exist_ok=True)
            
            # Copy all migration files
            for migration_file in migrations_dir.glob('*.py'):
                if migration_file.name != '__init__.py':
                    shutil.copy2(migration_file, app_backup_dir / migration_file.name)
        
        print_success(f"Migrations backed up to {backup_dir}")
        return True
    except Exception as e:
        print_error(f"Failed to backup migrations: {e}")
        return False


def delete_migrations(migration_dirs: List[Path], keep_init: bool = True) -> None:
    """
    Delete all migration files except __init__.py.
    
    Args:
        migration_dirs: List of migration directories
        keep_init: If True, keep __init__.py files
    """
    for migrations_dir in migration_dirs:
        for migration_file in migrations_dir.glob('*.py'):
            if migration_file.name == '__init__.py' and keep_init:
                continue
            migration_file.unlink()
            print_info(f"Deleted: {migration_file}")


def extract_data_migrations(migration_dirs: List[Path]) -> dict:
    """
    Extract data migration code from existing migrations.
    
    Args:
        migration_dirs: List of migration directories
    
    Returns:
        Dictionary mapping app names to data migration code
    """
    data_migrations = {}
    
    for migrations_dir in migration_dirs:
        app_name = migrations_dir.parent.name
        app_data_migrations = []
        
        for migration_file in sorted(migrations_dir.glob('*.py')):
            if migration_file.name == '__init__.py':
                continue
            
            try:
                content = migration_file.read_text(encoding='utf-8')
                # Check if migration contains RunPython
                if 'RunPython' in content or 'migrations.RunPython' in content:
                    app_data_migrations.append({
                        'file': migration_file.name,
                        'content': content
                    })
            except Exception:
                pass
        
        if app_data_migrations:
            data_migrations[app_name] = app_data_migrations
    
    return data_migrations


def squash_migrations(project_dir: Path, apps: Optional[List[str]] = None) -> bool:
    """
    Squash migrations using Django's squashmigrations command.
    
    Args:
        project_dir: Project root directory
        apps: List of app names to squash (None = all apps)
    
    Returns:
        True if squashing succeeded, False otherwise
    """
    print_info("Squashing migrations...")
    
    if apps is None:
        # Find all apps with migrations
        migration_dirs = find_migration_directories(project_dir)
        apps = [m.parent.name for m in migration_dirs]
    
    success = True
    for app in apps:
        print_info(f"Squashing migrations for {app}...")
        try:
            result = subprocess.run(
                ['python', 'manage.py', 'squashmigrations', app],
                cwd=project_dir,
                capture_output=True,
                text=True,
                check=False
            )
            
            if result.returncode == 0:
                print_success(f"Migrations squashed for {app}")
                if result.stdout:
                    print(result.stdout)
            else:
                print_warning(f"Squashing {app} had issues: {result.stderr}")
                # Squashing might fail if there are no migrations to squash
                if "no migrations to squash" not in result.stderr.lower():
                    success = False
        except Exception as e:
            print_error(f"Error squashing {app}: {e}")
            success = False
    
    return success


def regenerate_migrations(project_dir: Path, apps: Optional[List[str]] = None) -> bool:
    """
    Regenerate migrations from models.
    
    Args:
        project_dir: Project root directory
        apps: List of app names (None = all apps)
    
    Returns:
        True if regeneration succeeded, False otherwise
    """
    print_info("Regenerating migrations...")
    
    try:
        command = ['python', 'manage.py', 'makemigrations']
        if apps:
            command.extend(apps)
        
        result = subprocess.run(
            command,
            cwd=project_dir,
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.returncode == 0:
            print_success("Migrations regenerated")
            if result.stdout:
                print(result.stdout)
            return True
        else:
            print_error(f"Migration generation failed: {result.stderr}")
            return False
    except Exception as e:
        print_error(f"Error regenerating migrations: {e}")
        return False


def delete_database(project_dir: Path) -> bool:
    """
    Delete the database file.
    
    Args:
        project_dir: Project root directory
    
    Returns:
        True if deletion succeeded or database didn't exist, False otherwise
    """
    try:
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
        sys.path.insert(0, str(project_dir))
        
        import django
        django.setup()
        
        from django.conf import settings
        db_path = Path(settings.DATABASES['default']['NAME'])
        
        if db_path.exists():
            # Also delete WAL and SHM files
            wal_path = Path(str(db_path) + '-wal')
            shm_path = Path(str(db_path) + '-shm')
            
            db_path.unlink()
            if wal_path.exists():
                wal_path.unlink()
            if shm_path.exists():
                shm_path.unlink()
            
            print_success(f"Database deleted: {db_path}")
        else:
            print_info("No database file found")
        
        return True
    except Exception as e:
        print_error(f"Error deleting database: {e}")
        return False


def create_initial_database(project_dir: Path) -> bool:
    """
    Create initial database with new migrations.
    
    Args:
        project_dir: Project root directory
    
    Returns:
        True if creation succeeded, False otherwise
    """
    print_info("Creating initial database...")
    
    try:
        result = subprocess.run(
            ['python', 'manage.py', 'migrate'],
            cwd=project_dir,
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.returncode == 0:
            print_success("Initial database created")
            if result.stdout:
                print(result.stdout)
            return True
        else:
            print_error(f"Database creation failed: {result.stderr}")
            return False
    except Exception as e:
        print_error(f"Error creating database: {e}")
        return False


def reset_migrations(
    project_dir: Path,
    mode: str = 'reset',
    backup: bool = True,
    delete_db: bool = True,
    create_db: bool = True,
    apps: Optional[List[str]] = None
) -> bool:
    """
    Main function to reset or squash migrations.
    
    Args:
        project_dir: Project root directory
        mode: 'reset' or 'squash'
        backup: Whether to backup migrations before deletion
        delete_db: Whether to delete existing database
        create_db: Whether to create new database after reset
        apps: List of app names (None = all apps)
    
    Returns:
        True if operation succeeded, False otherwise
    """
    project_dir = Path(project_dir).resolve()
    
    print(f"\n{Colors.BOLD}=== Migration Reset/Squash Tool ==={Colors.RESET}\n")
    print_info(f"Project directory: {project_dir}")
    print_info(f"Mode: {mode}")
    
    if mode == 'reset':
        print_warning("This will DELETE all migration files and regenerate them!")
        print_warning("Make sure you have backed up your database if needed!")
        
        response = input("\nContinue? (yes/no): ")
        if response.lower() != 'yes':
            print_error("Operation cancelled")
            return False
        
        # Find migration directories
        migration_dirs = find_migration_directories(project_dir)
        
        if not migration_dirs:
            print_warning("No migration directories found")
            return False
        
        # Backup migrations
        if backup:
            backup_dir = project_dir / 'migration_backups'
            if not backup_migrations(migration_dirs, backup_dir):
                response = input("Backup failed. Continue anyway? (yes/no): ")
                if response.lower() != 'yes':
                    return False
        
        # Extract data migrations before deletion
        data_migrations = extract_data_migrations(migration_dirs)
        if data_migrations:
            print_warning(f"Found data migrations in: {', '.join(data_migrations.keys())}")
            print_warning("You may need to manually add these to the new migrations!")
        
        # Delete migrations
        print_info("Deleting migration files...")
        delete_migrations(migration_dirs)
        
        # Delete database if requested
        if delete_db:
            if not delete_database(project_dir):
                response = input("Database deletion failed. Continue? (yes/no): ")
                if response.lower() != 'yes':
                    return False
        
        # Regenerate migrations
        if not regenerate_migrations(project_dir, apps):
            return False
        
        # Create initial database if requested
        if create_db:
            if not create_initial_database(project_dir):
                print_warning("Database creation failed, but migrations were regenerated")
        
        print(f"\n{Colors.GREEN}{Colors.BOLD}=== Migration reset completed! ==={Colors.RESET}\n")
        print_info("Next steps:")
        print_info("1. Review the new migration files")
        if data_migrations:
            print_info("2. Add data migrations manually if needed")
        print_info("3. Test the migrations on a clean database")
        print_info("4. Update your deployment scripts if needed")
        
        return True
    
    elif mode == 'squash':
        print_info("Squashing migrations (preserving history)...")
        
        if not squash_migrations(project_dir, apps):
            return False
        
        print(f"\n{Colors.GREEN}{Colors.BOLD}=== Migration squashing completed! ==={Colors.RESET}\n")
        print_info("Next steps:")
        print_info("1. Review the squashed migration files")
        print_info("2. Test the squashed migrations")
        print_info("3. Once verified, you can delete old migrations")
        
        return True
    
    else:
        print_error(f"Unknown mode: {mode}")
        return False


def main() -> int:
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description='Reset or squash database migrations for clean production setup',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Reset all migrations (deletes and regenerates)
  python utils/reset_migrations.py --mode reset

  # Squash migrations (preserves history)
  python utils/reset_migrations.py --mode squash

  # Reset without deleting database
  python utils/reset_migrations.py --mode reset --no-delete-db

  # Reset specific apps only
  python utils/reset_migrations.py --mode reset --apps api kiosk
        """
    )
    
    parser.add_argument(
        '--project-dir',
        type=str,
        default=None,
        help='Project root directory (default: auto-detect from script location)'
    )
    
    parser.add_argument(
        '--mode',
        type=str,
        choices=['reset', 'squash'],
        default='reset',
        help='Operation mode: reset (delete and regenerate) or squash (combine)'
    )
    
    parser.add_argument(
        '--no-backup',
        action='store_true',
        help='Skip backing up migrations before deletion'
    )
    
    parser.add_argument(
        '--no-delete-db',
        action='store_true',
        help='Do not delete existing database'
    )
    
    parser.add_argument(
        '--no-create-db',
        action='store_true',
        help='Do not create new database after reset'
    )
    
    parser.add_argument(
        '--apps',
        nargs='+',
        help='Specific apps to process (default: all apps)'
    )
    
    args = parser.parse_args()
    
    # Default to project root (parent of utils/)
    project_dir = Path(args.project_dir) if args.project_dir else Path(__file__).parent.parent
    
    try:
        success = reset_migrations(
            project_dir=project_dir,
            mode=args.mode,
            backup=not args.no_backup,
            delete_db=not args.no_delete_db,
            create_db=not args.no_create_db,
            apps=args.apps
        )
        return 0 if success else 1
    except KeyboardInterrupt:
        print_error("\nOperation interrupted by user")
        return 1
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())

