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


def find_python_executable(project_dir: Path, verbose: bool = False) -> Optional[str]:
    """
    Find the Python executable from virtual environment.
    
    Checks for virtual environment in:
    1. /data/appl/mcc/venv/bin/python (Produktion)
    2. project_dir/venv/bin/python (Entwicklung)
    3. ~/venv_mcc/bin/python (Entwicklung)
    4. Falls back to system 'python' if no venv found
    
    Args:
        project_dir: Project root directory
        verbose: If True, print debug information
    
    Returns:
        Path to Python executable, or None if not found
    """
    # Prüfe ob wir in Produktion sind
    if '/data/appl/mcc' in str(project_dir) or os.environ.get('MCC_ENV') == 'production':
        venv_dir = Path('/data/appl/mcc/venv')
        if venv_dir.exists() and venv_dir.is_dir():
            venv_python = venv_dir / 'bin' / 'python'
            if venv_python.exists():
                if verbose:
                    print_info(f"Found production venv Python: {venv_python}")
                return str(venv_python)
            venv_python3 = venv_dir / 'bin' / 'python3'
            if venv_python3.exists():
                if verbose:
                    print_info(f"Found production venv Python3: {venv_python3}")
                return str(venv_python3)
    
    # Check for venv in project directory
    venv_dir = project_dir / 'venv'
    if venv_dir.exists() and venv_dir.is_dir():
        venv_python = venv_dir / 'bin' / 'python'
        if venv_python.exists():
            if verbose:
                print_info(f"Found venv Python: {venv_python}")
            return str(venv_python)
        
        # Check for venv in project directory (alternative name)
        venv_python3 = venv_dir / 'bin' / 'python3'
        if venv_python3.exists():
            if verbose:
                print_info(f"Found venv Python3: {venv_python3}")
            return str(venv_python3)
        
        # Venv directory exists but no Python executable found
        if verbose:
            print_warning(f"Virtual environment directory found at {venv_dir}, but Python executable not found")
            print_warning(f"  Checked: {venv_python} and {venv_python3}")
    
    # Check for development venv in home directory
    home_venv = Path.home() / 'venv_mcc' / 'bin' / 'python'
    if home_venv.exists():
        if verbose:
            print_info(f"Found home venv Python: {home_venv}")
        return str(home_venv)
    
    home_venv3 = Path.home() / 'venv_mcc' / 'bin' / 'python3'
    if home_venv3.exists():
        if verbose:
            print_info(f"Found home venv Python3: {home_venv3}")
        return str(home_venv3)
    
    # Check if VIRTUAL_ENV is set (already activated)
    if 'VIRTUAL_ENV' in os.environ:
        venv_path = Path(os.environ['VIRTUAL_ENV'])
        venv_python = venv_path / 'bin' / 'python'
        if venv_python.exists():
            if verbose:
                print_info(f"Found VIRTUAL_ENV Python: {venv_python}")
            return str(venv_python)
        venv_python3 = venv_path / 'bin' / 'python3'
        if venv_python3.exists():
            if verbose:
                print_info(f"Found VIRTUAL_ENV Python3: {venv_python3}")
            return str(venv_python3)
    
    # Fallback to system python
    if verbose:
        print_warning("No virtual environment found, will use system Python")
    return None


def get_python_executable(project_dir: Path, verbose: bool = False) -> str:
    """
    Get Python executable, preferring virtual environment.
    
    Args:
        project_dir: Project root directory
        verbose: If True, print debug information
    
    Returns:
        Path to Python executable
    
    Raises:
        RuntimeError: If no Python executable can be found
    """
    if verbose:
        print_info(f"Searching for Python executable in: {project_dir}")
    
    python_exe = find_python_executable(project_dir, verbose=verbose)
    
    if python_exe:
        if verbose:
            print_success(f"Found Python in virtual environment: {python_exe}")
        return python_exe
    
    # Try to find system python
    if verbose:
        print_warning("No virtual environment found, trying system Python...")
    for python_cmd in ['python3', 'python']:
        try:
            result = subprocess.run(
                [python_cmd, '--version'],
                capture_output=True,
                text=True,
                check=True
            )
            if verbose:
                print_warning(f"Using system Python: {python_cmd} ({result.stdout.strip()})")
                print_warning("⚠ WARNING: System Python may not have Django installed!")
                print_warning("   Consider creating a virtual environment:")
                print_warning(f"     cd {project_dir}")
                print_warning(f"     python3 -m venv venv")
                print_warning(f"     source venv/bin/activate")
                print_warning(f"     pip install -r requirements.txt")
            return python_cmd
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
    
    raise RuntimeError(
        f"No Python executable found. Please ensure:\n"
        f"  1. Virtual environment is activated, OR\n"
        f"  2. Virtual environment exists at: {project_dir}/venv/, OR\n"
        f"  3. System Python (python3 or python) is available\n"
        f"\nChecked paths:\n"
        f"  - {project_dir / 'venv' / 'bin' / 'python'}\n"
        f"  - {project_dir / 'venv' / 'bin' / 'python3'}\n"
        f"  - {Path.home() / 'venv_mcc' / 'bin' / 'python'}\n"
        f"  - {Path.home() / 'venv_mcc' / 'bin' / 'python3'}"
    )


def run_command(
    command: list[str],
    cwd: Optional[Path] = None,
    check: bool = True,
    capture_output: bool = False,
    python_exe: Optional[str] = None
) -> Tuple[int, str, str]:
    """
    Run a shell command and return the result.
    
    Args:
        command: Command and arguments as list
        cwd: Working directory
        check: If True, raise exception on non-zero exit code
        capture_output: If True, capture stdout and stderr
        python_exe: Python executable to use (if command starts with 'python')
    
    Returns:
        Tuple of (exit_code, stdout, stderr)
    """
    # Replace 'python' with actual python executable if provided
    if python_exe and len(command) > 0 and command[0] == 'python':
        command = [python_exe] + command[1:]
    
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


def check_django_environment(project_dir: Path, python_exe: Optional[str] = None) -> bool:
    """
    Check if Django environment is properly set up.
    
    Args:
        project_dir: Project root directory
        python_exe: Python executable to use
    
    Returns:
        True if environment is valid, False otherwise
    """
    print_info("Checking Django environment...")
    
    # Check if manage.py exists
    manage_py = project_dir / 'manage.py'
    if not manage_py.exists():
        print_error(f"manage.py not found in {project_dir}")
        return False
    
    # Try to find Python executable if not provided
    if python_exe is None:
        try:
            python_exe = get_python_executable(project_dir)
        except RuntimeError as e:
            print_error(str(e))
            return False
    
    # Verify Python executable exists and is executable
    python_path = Path(python_exe)
    if not python_path.exists():
        print_error(f"Python executable not found: {python_exe}")
        return False
    
    if not os.access(python_path, os.X_OK):
        print_error(f"Python executable is not executable: {python_exe}")
        return False
    
    print_info(f"Using Python: {python_exe}")
    
    # Check Python version first
    try:
        exit_code, stdout, stderr = run_command(
            [python_exe, '--version'],
            cwd=project_dir,
            check=False,
            capture_output=True
        )
        if exit_code == 0:
            print_info(f"Python version: {stdout.strip()}")
        else:
            print_warning(f"Could not get Python version: {stderr.strip()}")
    except Exception as e:
        print_warning(f"Could not check Python version: {e}")
    
    # Check if Django is available by running a simple check command
    try:
        exit_code, stdout, stderr = run_command(
            [python_exe, '-c', 'import django; print(django.__version__)'],
            cwd=project_dir,
            check=False,
            capture_output=True
        )
        
        if exit_code == 0:
            django_version = stdout.strip()
            print_success(f"Django environment is valid (Django {django_version})")
            return True
        else:
            error_msg = stderr.strip() if stderr else stdout.strip()
            print_error(f"Django not found in Python environment: {error_msg}")
            print_info(f"Python executable used: {python_exe}")
            print_info("Hint: Make sure virtual environment is activated or exists at project_dir/venv/")
            print_info("      Try: source project_dir/venv/bin/activate")
            return False
    except Exception as e:
        print_error(f"Django environment check failed: {e}")
        import traceback
        traceback.print_exc()
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
        # Prüfe ob wir in Produktion sind
        if '/data/appl/mcc' in str(project_dir) or os.environ.get('MCC_ENV') == 'production':
            backup_dir = Path('/data/var/mcc/backups')
        else:
            # Entwicklung: lokales Verzeichnis
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


def check_database_exists(project_dir: Path, python_exe: Optional[str] = None) -> bool:
    """
    Check if database file exists.
    
    Args:
        project_dir: Project root directory
        python_exe: Python executable to use
    
    Returns:
        True if database exists, False otherwise
    """
    try:
        if python_exe is None:
            python_exe = get_python_executable(project_dir)
        
        # Use Python to check database existence
        # Clear sys.path to avoid conflicts with old installations
        check_script = f"""
import os
import sys
from pathlib import Path
# Clear sys.path and only keep the current project directory
# This prevents conflicts with old installations at /data/games/mcc/mcc-web
project_dir = Path('{project_dir}').resolve()
sys.path = [str(project_dir)] + [p for p in sys.path if '/data/games/mcc' not in p and str(project_dir) not in p]
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.conf import settings
db_path = Path(settings.DATABASES['default']['NAME'])
print('EXISTS' if db_path.exists() else 'NOT_EXISTS')
"""
        exit_code, stdout, stderr = run_command(
            [python_exe, '-c', check_script],
            cwd=project_dir,
            check=False,
            capture_output=True
        )
        
        if exit_code == 0 and 'EXISTS' in stdout:
            return True
        return False
    except Exception:
        return False


def run_migrations(project_dir: Path, fake_initial: bool = False, python_exe: Optional[str] = None, retry_count: int = 0) -> bool:
    """
    Run Django migrations.
    
    Handles special cases:
    - Ensures django.contrib.sessions migrations run first to create django_session table
    - Handles case where game.0003 migration tries to create django_session table that already exists
    
    Args:
        project_dir: Project root directory
        fake_initial: If True, mark initial migrations as applied without running them
        python_exe: Python executable to use
        retry_count: Internal counter to prevent infinite recursion (max 1 retry)
    
    Returns:
        True if migrations succeeded, False otherwise
    """
    print_info("Running database migrations...")
    
    try:
        if python_exe is None:
            python_exe = get_python_executable(project_dir)
        
        # First, ensure Django built-in app migrations are run (especially sessions)
        # This is important because game.0003 might depend on django_session table existing
        if retry_count == 0:
            print_info("Ensuring Django built-in app migrations are applied...")
            builtin_apps = ['contenttypes', 'auth', 'sessions', 'admin', 'messages']
            for app in builtin_apps:
                builtin_command = [python_exe, 'manage.py', 'migrate', app]
                if fake_initial:
                    builtin_command.append('--fake-initial')
                
                builtin_exit_code, builtin_stdout, builtin_stderr = run_command(
                    builtin_command,
                    cwd=project_dir,
                    check=False,
                    capture_output=True
                )
                
                if builtin_exit_code != 0:
                    print_warning(f"Warning: Migration for {app} failed, but continuing...")
                    if builtin_stderr:
                        print_warning(f"  {builtin_stderr[:200]}")
        
        # Now run all migrations
        command = [python_exe, 'manage.py', 'migrate']
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
            # Check if the error is about django_session table already existing
            error_output = (stderr or '').lower()
            if 'django_session' in error_output and 'already exists' in error_output and retry_count == 0:
                print_warning("Migration error: django_session table already exists")
                print_info("Attempting to mark problematic migration as fake...")
                
                # Try to fake the game.0003 migration if it exists
                fake_command = [python_exe, 'manage.py', 'migrate', 'game', '0003', '--fake']
                fake_exit_code, fake_stdout, fake_stderr = run_command(
                    fake_command,
                    cwd=project_dir,
                    check=False,
                    capture_output=True
                )
                
                if fake_exit_code == 0:
                    print_success("Marked game.0003 migration as fake")
                    # Try running migrations again (only once)
                    return run_migrations(project_dir, fake_initial=fake_initial, python_exe=python_exe, retry_count=1)
                else:
                    # If fake didn't work, try to fake all pending game migrations
                    print_info("Trying to fake all pending game migrations...")
                    fake_all_command = [python_exe, 'manage.py', 'migrate', 'game', '--fake']
                    fake_all_exit_code, fake_all_stdout, fake_all_stderr = run_command(
                        fake_all_command,
                        cwd=project_dir,
                        check=False,
                        capture_output=True
                    )
                    
                    if fake_all_exit_code == 0:
                        print_success("Marked pending game migrations as fake")
                        # Try running migrations again (only once)
                        return run_migrations(project_dir, fake_initial=fake_initial, python_exe=python_exe, retry_count=1)
            
            # Check if the error is about django_session table not existing
            if 'django_session' in error_output and ('no such table' in error_output or 'does not exist' in error_output) and retry_count == 0:
                print_warning("Migration error: django_session table does not exist")
                print_info("Ensuring sessions app migrations are applied first...")
                
                # Run sessions migrations explicitly
                sessions_command = [python_exe, 'manage.py', 'migrate', 'sessions']
                sessions_exit_code, sessions_stdout, sessions_stderr = run_command(
                    sessions_command,
                    cwd=project_dir,
                    check=False,
                    capture_output=True
                )
                
                if sessions_exit_code == 0:
                    print_success("Sessions app migrations applied")
                    # Try running migrations again (only once)
                    return run_migrations(project_dir, fake_initial=fake_initial, python_exe=python_exe, retry_count=1)
                else:
                    print_error(f"Failed to apply sessions migrations: {sessions_stderr}")
            
            print_error(f"Migrations failed with exit code {exit_code}")
            if stderr:
                print(stderr)
            return False
    except Exception as e:
        print_error(f"Error running migrations: {e}")
        return False


def collect_static_files(project_dir: Path, clear: bool = False, python_exe: Optional[str] = None) -> bool:
    """
    Collect static files using Django's collectstatic command.
    
    Args:
        project_dir: Project root directory
        clear: If True, clear existing files before collecting
        python_exe: Python executable to use
    
    Returns:
        True if collection succeeded, False otherwise
    """
    print_info("Collecting static files...")
    
    try:
        if python_exe is None:
            python_exe = get_python_executable(project_dir)
        
        command = [python_exe, 'manage.py', 'collectstatic', '--noinput']
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


def compile_messages(project_dir: Path, python_exe: Optional[str] = None) -> bool:
    """
    Compile translation messages.
    
    Args:
        project_dir: Project root directory
        python_exe: Python executable to use
    
    Returns:
        True if compilation succeeded, False otherwise
    """
    print_info("Compiling translation messages...")
    
    try:
        if python_exe is None:
            python_exe = get_python_executable(project_dir)
        
        exit_code, stdout, stderr = run_command(
            [python_exe, 'manage.py', 'compilemessages'],
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


def ensure_media_directories(project_dir: Path, python_exe: Optional[str] = None) -> bool:
    """
    Ensure required media directories exist.
    
    Args:
        project_dir: Project root directory
        python_exe: Python executable to use
    
    Returns:
        True if directories were created/verified, False otherwise
    """
    try:
        if python_exe is None:
            python_exe = get_python_executable(project_dir)
        
        # Use Python to ensure media directories
        # Clear sys.path to avoid conflicts with old installations
        ensure_script = f"""
import os
import sys
from pathlib import Path
# Clear sys.path and only keep the current project directory
# This prevents conflicts with old installations at /data/games/mcc/mcc-web
project_dir = Path('{project_dir}').resolve()
sys.path = [str(project_dir)] + [p for p in sys.path if '/data/games/mcc' not in p and str(project_dir) not in p]
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.conf import settings
media_root = Path(settings.MEDIA_ROOT)
required_dirs = ['firmware', 'group_logos', 'player_avatars', 'tracks']
created_dirs = []
for subdir in required_dirs:
    dir_path = media_root / subdir
    if not dir_path.exists():
        dir_path.mkdir(parents=True, exist_ok=True)
        created_dirs.append(subdir)
if created_dirs:
    print('CREATED:' + ','.join(created_dirs))
else:
    print('EXISTS')
"""
        exit_code, stdout, stderr = run_command(
            [python_exe, '-c', ensure_script],
            cwd=project_dir,
            check=False,
            capture_output=True
        )
        
        if exit_code == 0:
            if 'CREATED:' in stdout:
                created = stdout.split('CREATED:')[1].strip()
                print_success(f"Created media directories: {created}")
            else:
                print_info("Media directories already exist")
            return True
        else:
            print_warning(f"Could not ensure media directories: {stderr}")
            return True  # Non-critical, continue anyway
    except Exception as e:
        print_warning(f"Could not ensure media directories: {e}")
        return True  # Non-critical, continue anyway


def validate_deployment(project_dir: Path, python_exe: Optional[str] = None) -> bool:
    """
    Run basic validation checks after deployment.
    
    Args:
        project_dir: Project root directory
        python_exe: Python executable to use
    
    Returns:
        True if validation passed, False otherwise
    """
    print_info("Validating deployment...")
    
    try:
        if python_exe is None:
            python_exe = get_python_executable(project_dir)
        
        # Use Python to validate deployment
        # Clear sys.path to avoid conflicts with old installations
        validate_script = f"""
import os
import sys
from pathlib import Path
# Clear sys.path and only keep the current project directory
# This prevents conflicts with old installations at /data/games/mcc/mcc-web
project_dir = Path('{project_dir}').resolve()
sys.path = [str(project_dir)] + [p for p in sys.path if '/data/games/mcc' not in p and str(project_dir) not in p]
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.conf import settings
from django.db import connection
with connection.cursor() as cursor:
    cursor.execute("SELECT 1")
static_root = Path(settings.STATIC_ROOT)
if static_root.exists():
    print('STATIC_OK:' + str(static_root))
else:
    print('STATIC_MISSING:' + str(static_root))
print('DB_OK')
"""
        exit_code, stdout, stderr = run_command(
            [python_exe, '-c', validate_script],
            cwd=project_dir,
            check=False,
            capture_output=True
        )
        
        if exit_code == 0:
            if 'DB_OK' in stdout:
                print_success("Database connection validated")
            
            if 'STATIC_OK:' in stdout:
                static_path = stdout.split('STATIC_OK:')[1].strip()
                print_success(f"Static files directory exists: {static_path}")
            elif 'STATIC_MISSING:' in stdout:
                static_path = stdout.split('STATIC_MISSING:')[1].strip()
                print_warning(f"Static files directory not found: {static_path}")
            
            return True
        else:
            print_error(f"Deployment validation failed: {stderr}")
            return False
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
    
    # Find Python executable early
    print_info("Searching for Python executable...")
    try:
        python_exe = get_python_executable(project_dir, verbose=True)
        print_info(f"✓ Using Python executable: {python_exe}")
        
        # Verify it's actually executable
        if not Path(python_exe).exists() and python_exe not in ['python', 'python3']:
            print_error(f"Python executable not found: {python_exe}")
            return False
    except RuntimeError as e:
        print_error(str(e))
        return False
    
    # Step 1: Check Django environment
    print_step(1, 6, "Checking Django environment")
    if not check_django_environment(project_dir, python_exe=python_exe):
        print_error("\n" + "="*60)
        print_error("Django environment check failed!")
        print_error("="*60)
        print_info(f"Python executable used: {python_exe}")
        print_info(f"Project directory: {project_dir}")
        venv_path = project_dir / 'venv'
        if venv_path.exists():
            print_warning(f"Virtual environment directory exists: {venv_path}")
            print_warning("But Django is not installed in it.")
            print_info("To fix this, run:")
            print_info(f"  cd {project_dir}")
            print_info(f"  source venv/bin/activate")
            print_info(f"  pip install -r requirements.txt")
        else:
            print_warning(f"Virtual environment not found at: {venv_path}")
            print_info("To create it, run:")
            print_info(f"  cd {project_dir}")
            print_info(f"  python3 -m venv venv")
            print_info(f"  source venv/bin/activate")
            print_info(f"  pip install -r requirements.txt")
        return False
    
    # Step 2: Database backup
    print_step(2, 6, "Database backup")
    db_exists = check_database_exists(project_dir, python_exe=python_exe)
    
    if db_exists and not skip_backup:
        try:
            # Get database path using Python
            # Clear sys.path to avoid conflicts with old installations
            get_db_path_script = f"""
import os
import sys
from pathlib import Path
# Clear sys.path and only keep the current project directory
# This prevents conflicts with old installations at /data/games/mcc/mcc-web
project_dir = Path('{project_dir}').resolve()
sys.path = [str(project_dir)] + [p for p in sys.path if '/data/games/mcc' not in p and str(project_dir) not in p]
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.conf import settings
print(settings.DATABASES['default']['NAME'])
"""
            exit_code, stdout, stderr = run_command(
                [python_exe, '-c', get_db_path_script],
                cwd=project_dir,
                check=False,
                capture_output=True
            )
            
            if exit_code == 0:
                db_path = Path(stdout.strip())
                backup_path = backup_database(project_dir, db_path)
                if backup_path is None and db_exists:
                    print_warning("Backup failed, but continuing...")
            else:
                print_warning(f"Could not determine database path: {stderr}")
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
    if not run_migrations(project_dir, fake_initial=fake_initial, python_exe=python_exe):
        print_error("Migration failed - deployment aborted")
        return False
    
    # Step 4: Collect static files
    print_step(4, 6, "Collecting static files")
    if not skip_static:
        if not collect_static_files(project_dir, clear=clear_static, python_exe=python_exe):
            print_error("Static file collection failed - deployment aborted")
            return False
    else:
        print_info("Skipping static file collection (--skip-static flag)")
    
    # Step 5: Ensure media directories
    print_step(5, 7, "Ensuring media directories")
    ensure_media_directories(project_dir, python_exe=python_exe)  # Non-critical, don't fail on error
    
    # Step 6: Compile messages
    print_step(6, 7, "Compiling translation messages")
    if not skip_compilemessages:
        compile_messages(project_dir, python_exe=python_exe)  # Non-critical, don't fail on error
    else:
        print_info("Skipping message compilation (--skip-compilemessages flag)")
    
    # Step 7: Validate deployment
    print_step(7, 7, "Validating deployment")
    if not validate_deployment(project_dir, python_exe=python_exe):
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
    
    # Default to project root
    if args.project_dir:
        project_dir = Path(args.project_dir).resolve()
    else:
        # Try to use current working directory first (for production deployments)
        # If we're in a project directory with manage.py, use it
        cwd = Path.cwd().resolve()
        if (cwd / 'manage.py').exists():
            project_dir = cwd
            print_info(f"Using current working directory as project directory: {project_dir}")
        else:
            # Fallback to parent of script location (for development)
            # But resolve symlinks to get actual location
            script_path = Path(__file__).resolve()
            project_dir = script_path.parent.parent
            print_info(f"Using script location as project directory: {project_dir}")
    
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

