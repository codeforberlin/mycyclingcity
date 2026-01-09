#!/usr/bin/env python3
"""
Pre-deployment validation checks for MCC-Web production deployment.

This script validates the environment and configuration before deployment.
"""

import os
import sys
import subprocess
from pathlib import Path
from typing import List, Tuple


class Colors:
    """ANSI color codes."""
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    RESET = '\033[0m'


def print_check(name: str, status: bool, message: str = "") -> None:
    """Print a check result."""
    icon = f"{Colors.GREEN}✓{Colors.RESET}" if status else f"{Colors.RED}✗{Colors.RESET}"
    print(f"{icon} {name}")
    if message:
        print(f"   {message}")


def check_python_version() -> Tuple[bool, str]:
    """Check Python version."""
    version = sys.version_info
    if version.major == 3 and version.minor >= 10:
        return True, f"Python {version.major}.{version.minor}.{version.micro}"
    return False, f"Python {version.major}.{version.minor}.{version.micro} (requires 3.10+)"


def check_dependencies(project_dir: Path) -> Tuple[bool, str]:
    """Check if all dependencies are installed."""
    try:
        result = subprocess.run(
            ['pip', 'check'],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            return True, "All dependencies satisfied"
        return False, result.stdout or "Dependency conflicts detected"
    except Exception as e:
        return False, f"Could not check dependencies: {e}"


def check_environment_variables(project_dir: Path) -> Tuple[bool, List[str]]:
    """Check required environment variables."""
    try:
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
        sys.path.insert(0, str(project_dir))
        
        import django
        django.setup()
        
        from django.conf import settings
        from decouple import config
        
        issues = []
        
        # Check SECRET_KEY
        secret_key = config('SECRET_KEY', default=None)
        if not secret_key or secret_key == 'django-insecure-YOUR_SECRET_KEY_HERE':
            issues.append("SECRET_KEY not set or using default value")
        
        # Check DEBUG
        debug = config('DEBUG', default=True, cast=bool)
        if debug:
            issues.append("DEBUG is True (should be False in production)")
        
        # Check ALLOWED_HOSTS
        allowed_hosts = config('ALLOWED_HOSTS', default='', cast=str)
        if not allowed_hosts or allowed_hosts == '*':
            issues.append("ALLOWED_HOSTS not properly configured")
        
        return len(issues) == 0, issues
    except Exception as e:
        return False, [f"Error checking environment: {e}"]


def check_database(project_dir: Path) -> Tuple[bool, str]:
    """Check database connectivity."""
    try:
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
        sys.path.insert(0, str(project_dir))
        
        import django
        django.setup()
        
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        
        return True, "Database connection OK"
    except Exception as e:
        return False, f"Database connection failed: {e}"


def check_static_files(project_dir: Path) -> Tuple[bool, str]:
    """Check if static files directory exists."""
    try:
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
        sys.path.insert(0, str(project_dir))
        
        import django
        django.setup()
        
        from django.conf import settings
        static_root = Path(settings.STATIC_ROOT)
        
        if static_root.exists():
            return True, f"Static files directory exists: {static_root}"
        return False, f"Static files directory not found: {static_root}"
    except Exception as e:
        return False, f"Error checking static files: {e}"


def check_media_files(project_dir: Path) -> Tuple[bool, str]:
    """Check if media files directory exists and is writable."""
    try:
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
        sys.path.insert(0, str(project_dir))
        
        import django
        django.setup()
        
        from django.conf import settings
        media_root = Path(settings.MEDIA_ROOT)
        
        if not media_root.exists():
            return False, f"Media directory not found: {media_root}"
        
        if not os.access(media_root, os.W_OK):
            return False, f"Media directory not writable: {media_root}"
        
        return True, f"Media directory OK: {media_root}"
    except Exception as e:
        return False, f"Error checking media files: {e}"


def check_migrations(project_dir: Path) -> Tuple[bool, str]:
    """Check if migrations are up to date."""
    try:
        result = subprocess.run(
            ['python', 'manage.py', 'showmigrations', '--plan'],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            return False, f"Migrations check failed: {result.stderr}"
        
        # Check for unapplied migrations
        if '[ ]' in result.stdout:
            return False, "Unapplied migrations detected"
        
        return True, "All migrations applied"
    except Exception as e:
        return False, f"Error checking migrations: {e}"


def check_file_permissions(project_dir: Path) -> Tuple[bool, List[str]]:
    """Check file permissions."""
    issues = []
    
    # Check database file permissions
    db_file = project_dir / 'db.sqlite3'
    if db_file.exists():
        if not os.access(db_file, os.R_OK | os.W_OK):
            issues.append(f"Database file not readable/writable: {db_file}")
    
    # Check media directory permissions
    media_dir = project_dir / 'media'
    if media_dir.exists():
        if not os.access(media_dir, os.W_OK):
            issues.append(f"Media directory not writable: {media_dir}")
    
    return len(issues) == 0, issues


def run_checks(project_dir: Path) -> bool:
    """Run all pre-deployment checks."""
    print(f"\n{Colors.BOLD}Pre-Deployment Checks{Colors.RESET}\n")
    print("=" * 60)
    
    all_passed = True
    
    # Python version
    status, msg = check_python_version()
    print_check("Python Version", status, msg)
    if not status:
        all_passed = False
    
    # Dependencies
    status, msg = check_dependencies(project_dir)
    print_check("Dependencies", status, msg)
    if not status:
        all_passed = False
    
    # Environment variables
    status, issues = check_environment_variables(project_dir)
    if issues:
        print_check("Environment Variables", False)
        for issue in issues:
            print(f"   ⚠ {issue}")
        all_passed = False
    else:
        print_check("Environment Variables", True)
    
    # Database
    status, msg = check_database(project_dir)
    print_check("Database", status, msg)
    if not status:
        all_passed = False
    
    # Static files
    status, msg = check_static_files(project_dir)
    print_check("Static Files", status, msg)
    if not status:
        all_passed = False
    
    # Media files
    status, msg = check_media_files(project_dir)
    print_check("Media Files", status, msg)
    if not status:
        all_passed = False
    
    # Migrations
    status, msg = check_migrations(project_dir)
    print_check("Migrations", status, msg)
    if not status:
        all_passed = False
    
    # File permissions
    status, issues = check_file_permissions(project_dir)
    if issues:
        print_check("File Permissions", False)
        for issue in issues:
            print(f"   ⚠ {issue}")
        all_passed = False
    else:
        print_check("File Permissions", True)
    
    print("\n" + "=" * 60)
    if all_passed:
        print(f"{Colors.GREEN}{Colors.BOLD}✓ All checks passed!{Colors.RESET}\n")
    else:
        print(f"{Colors.RED}{Colors.BOLD}✗ Some checks failed!{Colors.RESET}\n")
        print("Please fix the issues above before deploying.\n")
    
    return all_passed


def main() -> int:
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Run pre-deployment validation checks'
    )
    parser.add_argument(
        '--project-dir',
        type=str,
        default=None,
        help='Project root directory (default: auto-detect from script location)'
    )
    
    args = parser.parse_args()
    
    # Default to project root (parent of utils/)
    project_dir = Path(args.project_dir).resolve() if args.project_dir else Path(__file__).parent.parent.resolve()
    
    try:
        success = run_checks(project_dir)
        return 0 if success else 1
    except KeyboardInterrupt:
        print("\nChecks interrupted by user")
        return 1
    except Exception as e:
        print(f"Error running checks: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())

