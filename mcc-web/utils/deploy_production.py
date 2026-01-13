# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    deploy_production.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
"""
Production deployment script for MCC-Web application.

This script handles:
- Database backup (before migration)
- Database initialization or migration
- Static files collection
- Translation compilation
- Safety checks and validations
"""

import os
import sys
import shutil
import subprocess
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple


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


def print_step(step: int, total: int, message: str) -> None:
    """Print a step message."""
    print(f"\n{Colors.BOLD}[{step}/{total}]{Colors.RESET} {message}")


def run_command(
    command: list[str],
    cwd: Optional[Path] = None,
    check: bool = True,
    capture_output: bool = False
) -> Tuple[int, str, str]:
    """
    Run a shell command and return the result.
    
    Args:
        command: Command and arguments as list
        cwd: Working directory
        check: If True, raise exception on non-zero exit code
        capture_output: If True, capture stdout and stderr
    
    Returns:
        Tuple of (exit_code, stdout, stderr)
    """
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=capture_output,
            text=True,
            check=check
        )
        stdout = result.stdout if capture_output else ""
        stderr = result.stderr if capture_output else ""
        return result.returncode, stdout, stderr
    except subprocess.CalledProcessError as e:
        if capture_output:
            return e.returncode, e.stdout or "", e.stderr or ""
        raise


def check_django_environment(project_dir: Path) -> bool:
    """
    Check if Django environment is properly set up.
    
    Args:
        project_dir: Project root directory
    
    Returns:
        True if environment is valid, False otherwise
    """
    print_info("Checking Django environment...")
    
    # Check if manage.py exists
    manage_py = project_dir / 'manage.py'
    if not manage_py.exists():
        print_error(f"manage.py not found in {project_dir}")
        return False
    
    # Check if settings module can be imported
    try:
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
        sys.path.insert(0, str(project_dir))
        
        import django
        django.setup()
        
        from django.conf import settings
        print_success("Django environment is valid")
        return True
    except Exception as e:
        print_error(f"Django environment check failed: {e}")
        return False


def backup_database(project_dir: Path, db_path: Path, backup_dir: Optional[Path] = None) -> Optional[Path]:
    """
    Create a backup of the database before migration.
    
    Args:
        project_dir: Project root directory
        db_path: Path to the database file
        backup_dir: Directory for backups (default: project_dir/backups)
    
    Returns:
        Path to the backup file, or None if backup failed or not needed
    """
    if not db_path.exists():
        print_info("No existing database found - skipping backup")
        return None
    
    if backup_dir is None:
        backup_dir = project_dir / 'backups'
    
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_filename = f"db_backup_{timestamp}.sqlite3"
    backup_path = backup_dir / backup_filename
    
    try:
        print_info(f"Creating database backup: {backup_path}")
        shutil.copy2(db_path, backup_path)
        
        # Also backup WAL and SHM files if they exist
        wal_path = Path(str(db_path) + '-wal')
        shm_path = Path(str(db_path) + '-shm')
        
        if wal_path.exists():
            shutil.copy2(wal_path, backup_dir / f"{backup_filename}-wal")
        if shm_path.exists():
            shutil.copy2(shm_path, backup_dir / f"{backup_filename}-shm")
        
        print_success(f"Database backed up to {backup_path}")
        return backup_path
    except Exception as e:
        print_error(f"Failed to create database backup: {e}")
        return None


def check_database_exists(project_dir: Path) -> bool:
    """
    Check if database file exists.
    
    Args:
        project_dir: Project root directory
    
    Returns:
        True if database exists, False otherwise
    """
    try:
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
        sys.path.insert(0, str(project_dir))
        
        import django
        django.setup()
        
        from django.conf import settings
        db_path = Path(settings.DATABASES['default']['NAME'])
        return db_path.exists()
    except Exception:
        return False


def run_migrations(project_dir: Path, fake_initial: bool = False) -> bool:
    """
    Run Django migrations.
    
    Args:
        project_dir: Project root directory
        fake_initial: If True, mark initial migrations as applied without running them
    
    Returns:
        True if migrations succeeded, False otherwise
    """
    print_info("Running database migrations...")
    
    try:
        command = ['python', 'manage.py', 'migrate']
        if fake_initial:
            command.append('--fake-initial')
        
        exit_code, stdout, stderr = run_command(
            command,
            cwd=project_dir,
            check=False,
            capture_output=True
        )
        
        if exit_code == 0:
            print_success("Migrations completed successfully")
            if stdout:
                print(stdout)
            return True
        else:
            print_error(f"Migrations failed with exit code {exit_code}")
            if stderr:
                print(stderr)
            return False
    except Exception as e:
        print_error(f"Error running migrations: {e}")
        return False


def collect_static_files(project_dir: Path, clear: bool = False) -> bool:
    """
    Collect static files using Django's collectstatic command.
    
    Args:
        project_dir: Project root directory
        clear: If True, clear existing files before collecting
    
    Returns:
        True if collection succeeded, False otherwise
    """
    print_info("Collecting static files...")
    
    try:
        command = ['python', 'manage.py', 'collectstatic', '--noinput']
        if clear:
            command.append('--clear')
        
        exit_code, stdout, stderr = run_command(
            command,
            cwd=project_dir,
            check=False,
            capture_output=True
        )
        
        if exit_code == 0:
            print_success("Static files collected successfully")
            return True
        else:
            print_error(f"Static file collection failed with exit code {exit_code}")
            if stderr:
                print(stderr)
            return False
    except Exception as e:
        print_error(f"Error collecting static files: {e}")
        return False


def compile_messages(project_dir: Path) -> bool:
    """
    Compile translation messages.
    
    Args:
        project_dir: Project root directory
    
    Returns:
        True if compilation succeeded, False otherwise
    """
    print_info("Compiling translation messages...")
    
    try:
        exit_code, stdout, stderr = run_command(
            ['python', 'manage.py', 'compilemessages'],
            cwd=project_dir,
            check=False,
            capture_output=True
        )
        
        if exit_code == 0:
            print_success("Translation messages compiled successfully")
            return True
        else:
            # compilemessages may return non-zero if no .po files exist, which is OK
            if "no Django translation files found" in stderr.lower():
                print_warning("No translation files found (this is OK if not using i18n)")
                return True
            print_warning(f"Translation compilation had issues: {stderr}")
            return True  # Not critical, continue anyway
    except Exception as e:
        print_warning(f"Error compiling messages (non-critical): {e}")
        return True  # Not critical, continue anyway


def ensure_media_directories(project_dir: Path) -> bool:
    """
    Ensure required media directories exist.
    
    Args:
        project_dir: Project root directory
    
    Returns:
        True if directories were created/verified, False otherwise
    """
    try:
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
        sys.path.insert(0, str(project_dir))
        
        import django
        django.setup()
        
        from django.conf import settings
        media_root = Path(settings.MEDIA_ROOT)
        
        # Required subdirectories based on project structure
        required_dirs = [
            'firmware',
            'group_logos',
            'player_avatars',
            'tracks',
        ]
        
        created_dirs = []
        for subdir in required_dirs:
            dir_path = media_root / subdir
            if not dir_path.exists():
                dir_path.mkdir(parents=True, exist_ok=True)
                created_dirs.append(subdir)
        
        if created_dirs:
            print_success(f"Created media directories: {', '.join(created_dirs)}")
        else:
            print_info("Media directories already exist")
        
        return True
    except Exception as e:
        print_warning(f"Could not ensure media directories: {e}")
        return True  # Non-critical, continue anyway


def validate_deployment(project_dir: Path) -> bool:
    """
    Run basic validation checks after deployment.
    
    Args:
        project_dir: Project root directory
    
    Returns:
        True if validation passed, False otherwise
    """
    print_info("Validating deployment...")
    
    try:
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
        sys.path.insert(0, str(project_dir))
        
        import django
        django.setup()
        
        from django.conf import settings
        from django.core.management import call_command
        from io import StringIO
        
        # Check database connection
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        
        print_success("Database connection validated")
        
        # Check static files directory
        static_root = Path(settings.STATIC_ROOT)
        if static_root.exists():
            print_success(f"Static files directory exists: {static_root}")
        else:
            print_warning(f"Static files directory not found: {static_root}")
        
        return True
    except Exception as e:
        print_error(f"Deployment validation failed: {e}")
        return False


def deploy(
    project_dir: Path,
    skip_backup: bool = False,
    skip_static: bool = False,
    skip_compilemessages: bool = False,
    clear_static: bool = False,
    fake_initial: bool = False
) -> bool:
    """
    Main deployment function.
    
    Args:
        project_dir: Project root directory
        skip_backup: Skip database backup
        skip_static: Skip static file collection
        skip_compilemessages: Skip message compilation
        clear_static: Clear static files before collecting
        fake_initial: Fake initial migrations
    
    Returns:
        True if deployment succeeded, False otherwise
    """
    project_dir = Path(project_dir).resolve()
    
    if not project_dir.exists():
        print_error(f"Project directory does not exist: {project_dir}")
        return False
    
    print(f"\n{Colors.BOLD}=== MCC-Web Production Deployment ==={Colors.RESET}\n")
    print_info(f"Project directory: {project_dir}")
    
    # Step 1: Check Django environment
    print_step(1, 6, "Checking Django environment")
    if not check_django_environment(project_dir):
        return False
    
    # Step 2: Database backup
    print_step(2, 6, "Database backup")
    db_exists = check_database_exists(project_dir)
    
    if db_exists and not skip_backup:
        try:
            os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
            sys.path.insert(0, str(project_dir))
            
            import django
            django.setup()
            
            from django.conf import settings
            db_path = Path(settings.DATABASES['default']['NAME'])
            backup_path = backup_database(project_dir, db_path)
            if backup_path is None and db_exists:
                print_warning("Backup failed, but continuing...")
        except Exception as e:
            print_warning(f"Could not create backup: {e}")
            response = input("Continue without backup? (yes/no): ")
            if response.lower() != 'yes':
                print_error("Deployment aborted by user")
                return False
    elif skip_backup:
        print_info("Skipping backup (--skip-backup flag)")
    else:
        print_info("No existing database - initial deployment")
    
    # Step 3: Run migrations
    print_step(3, 6, "Running database migrations")
    if not run_migrations(project_dir, fake_initial=fake_initial):
        print_error("Migration failed - deployment aborted")
        return False
    
    # Step 4: Collect static files
    print_step(4, 6, "Collecting static files")
    if not skip_static:
        if not collect_static_files(project_dir, clear=clear_static):
            print_error("Static file collection failed - deployment aborted")
            return False
    else:
        print_info("Skipping static file collection (--skip-static flag)")
    
    # Step 5: Ensure media directories
    print_step(5, 7, "Ensuring media directories")
    ensure_media_directories(project_dir)  # Non-critical, don't fail on error
    
    # Step 6: Compile messages
    print_step(6, 7, "Compiling translation messages")
    if not skip_compilemessages:
        compile_messages(project_dir)  # Non-critical, don't fail on error
    else:
        print_info("Skipping message compilation (--skip-compilemessages flag)")
    
    # Step 7: Validate deployment
    print_step(7, 7, "Validating deployment")
    if not validate_deployment(project_dir):
        print_warning("Validation had issues, but deployment completed")
    
    print(f"\n{Colors.GREEN}{Colors.BOLD}=== Deployment completed successfully! ==={Colors.RESET}\n")
    
    # Print summary
    print(f"{Colors.BOLD}Summary:{Colors.RESET}")
    print(f"  - Database: {'Migrated' if db_exists else 'Initialized'}")
    if not skip_static:
        print(f"  - Static files: Collected")
    if not skip_compilemessages:
        print(f"  - Translations: Compiled")
    
    return True


def main() -> int:
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description='Deploy MCC-Web application to production',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full deployment (initial or update)
  python utils/deploy_production.py

  # Skip backup (not recommended)
  python utils/deploy_production.py --skip-backup

  # Clear static files before collecting
  python utils/deploy_production.py --clear-static

  # Skip static file collection
  python utils/deploy_production.py --skip-static
        """
    )
    
    parser.add_argument(
        '--project-dir',
        type=str,
        default=None,
        help='Project root directory (default: auto-detect from script location)'
    )
    
    parser.add_argument(
        '--skip-backup',
        action='store_true',
        help='Skip database backup (not recommended for production)'
    )
    
    parser.add_argument(
        '--skip-static',
        action='store_true',
        help='Skip static file collection'
    )
    
    parser.add_argument(
        '--skip-compilemessages',
        action='store_true',
        help='Skip translation message compilation'
    )
    
    parser.add_argument(
        '--clear-static',
        action='store_true',
        help='Clear existing static files before collecting'
    )
    
    parser.add_argument(
        '--fake-initial',
        action='store_true',
        help='Mark initial migrations as applied without running them'
    )
    
    args = parser.parse_args()
    
    # Default to project root (parent of utils/)
    project_dir = Path(args.project_dir) if args.project_dir else Path(__file__).parent.parent
    
    try:
        success = deploy(
            project_dir=project_dir,
            skip_backup=args.skip_backup,
            skip_static=args.skip_static,
            skip_compilemessages=args.skip_compilemessages,
            clear_static=args.clear_static,
            fake_initial=args.fake_initial
        )
        return 0 if success else 1
    except KeyboardInterrupt:
        print_error("\nDeployment interrupted by user")
        return 1
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())

