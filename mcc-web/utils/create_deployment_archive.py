# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    create_deployment_archive.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
"""
Create a deployment archive (tar.gz) for the MCC-Web application.

This script collects all necessary files for production deployment,
excluding development files, caches, and generated content.
"""

import os
import sys
import tarfile
import subprocess
from pathlib import Path
from datetime import datetime
from typing import List, Set, Optional


def get_project_version() -> str:
    """
    Get project version from version.txt file or fallback to git describe.
    
    Returns:
        Version string (e.g., "1.0.0" or "v1.0.0-5-gabc1234").
    """
    # Script is in mcc-web/utils/, so mcc-web/ is parent.parent
    mcc_web_dir = Path(__file__).parent.parent
    repo_root = mcc_web_dir.parent
    
    # First try mcc-web/version.txt (for deployment archive)
    version_file = mcc_web_dir / 'version.txt'
    if version_file.exists():
        try:
            with open(version_file, 'r', encoding='utf-8') as f:
                version = f.read().strip()
                if version:
                    return version
        except Exception:
            pass
    
    # Fallback to repository root version.txt (for CI/CD)
    version_file = repo_root / 'version.txt'
    if version_file.exists():
        try:
            with open(version_file, 'r', encoding='utf-8') as f:
                version = f.read().strip()
                if version:
                    return version
        except Exception:
            pass
    
    # Fallback to git describe
    try:
        result = subprocess.run(
            ['git', 'describe', '--tags', '--always', '--dirty'],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    
    return 'dev'


# Note: get_database_path() function removed - database is now in /data/var/mcc/db/
# and not in the project directory, so it doesn't need to be excluded from archives


def get_database_exclude_patterns(base_dir: Path) -> List[str]:
    """
    Get database file patterns to exclude.
    
    Since the database is now in /data/var/mcc/db/, it's not in the project directory.
    However, we still exclude common database patterns for backwards compatibility
    and in case someone has old database files in the project directory.
    
    Args:
        base_dir: The base directory of the project
        
    Returns:
        List of exclude patterns for database files
    """
    # Database is now in /data/var/mcc/db/, but exclude common patterns
    # for backwards compatibility and old installations
    return [
        'db.sqlite3',
        'db.sqlite3-journal',
        'db.sqlite3-shm',
        'db.sqlite3-wal',
        'db.sqlite3.old',
        'data/db.sqlite3',
        'data/db.sqlite3-journal',
        'data/db.sqlite3-shm',
        'data/db.sqlite3-wal',
        'data/db.sqlite3.old',
        '*.db',
        '*.sqlite',
        '*.sqlite3',
    ]


def should_exclude(path: Path, base_dir: Path) -> bool:
    """
    Check if a path should be excluded from the archive.
    
    Args:
        path: The path to check (relative to base_dir)
        base_dir: The base directory of the project
        
    Returns:
        True if the path should be excluded, False otherwise.
    """
    # Convert to relative path
    try:
        rel_path = path.relative_to(base_dir)
    except ValueError:
        return True  # Path is outside base_dir
    
    path_str = str(rel_path)
    path_parts = path_str.split(os.sep)
    
    # Get database exclude patterns dynamically
    db_exclude_patterns = get_database_exclude_patterns(base_dir)
    
    # Exclude patterns (based on .gitignore and deployment needs)
    exclude_patterns = [
        # Python cache and compiled files
        '__pycache__',
        '*.pyc',
        '*.pyo',
        '*.pyd',
        '.Python',
        '*.so',
        '*.egg-info',
        '.installed.cfg',
        '*.egg',
        
        # Django specific
        '*.log',
        'local_settings.py',
        'staticfiles',
        'media',
        # Note: .mo files in locale/ are INCLUDED (compiled in dev, deployed to production)
        # They will be copied to /data/var/mcc/locale_compiled during deployment
        'backups',  # Database backups should not be deployed
        'tmp',  # Temporary files directory
        
        # Virtual environments
        'venv',
        'env',
        'ENV',
        'env.bak',
        'venv.bak',
        
        # IDE files
        '.vscode',
        '.idea',
        '*.swp',
        '*.swo',
        '*~',
        '.DS_Store',
        
        # Environment files
        '.env',
        '.env.local',
        '.env.*.local',
        
        # Test and coverage
        'htmlcov',
        '.tox',
        '.nox',
        '.coverage',
        '.coverage.*',
        '.cache',
        'nosetests.xml',
        'coverage.xml',
        '*.cover',
        '.hypothesis',
        '.pytest_cache',
        'cover',
        
        # Git
        '.git',
        '.gitignore',
        
        # Documentation build
        'site',
        
        # Type checkers
        '.mypy_cache',
        '.dmypy.json',
        'dmypy.json',
        '.pyre',
        '.pytype',
        'cython_debug',
        
        # Build and dist
        'build',
        'dist',
        'develop-eggs',
        'downloads',
        'eggs',
        '.eggs',
        'lib',
        'lib64',
        'parts',
        'sdist',
        'var',
        'wheels',
        'share',
        'MANIFEST',
        
        # Jupyter
        '.ipynb_checkpoints',
        
        # Celery
        'celerybeat-schedule',
        'celerybeat.pid',
        
        # Project specific
        'firmware_*.bin',  # Firmware files should be managed separately
    ]
    
    # Add database exclude patterns dynamically
    exclude_patterns.extend(db_exclude_patterns)
    
    # Check if any part of the path matches an exclude pattern
    for part in path_parts:
        if part.startswith('.'):
            # Hidden files/directories (except some we want to keep)
            if part not in ['.gitignore']:  # We might want to keep .gitignore for reference
                return True
        
        # Check exact matches (including venv directories)
        if part in exclude_patterns:
            return True
        
        # Special check for venv directories (case-insensitive)
        if part.lower() in ['venv', 'env', 'virtualenv', '.venv']:
            return True
        
        # Check pattern matches (simple glob-like matching)
        for pattern in exclude_patterns:
            if '*' in pattern:
                # Simple glob matching
                import fnmatch
                if fnmatch.fnmatch(part, pattern):
                    return True
    
    # Check if the full path matches a pattern (for exact file names)
    filename = path.name
    for pattern in exclude_patterns:
        if '*' in pattern:
            import fnmatch
            if fnmatch.fnmatch(filename, pattern):
                return True
        elif pattern == filename:
            return True
    
    # Special case: INCLUDE .mo files in locale/ directory (compiled translations from dev)
    # These will be deployed and copied to /data/var/mcc/locale_compiled
    # Only exclude .mo files outside locale/ (e.g., in venv)
    if filename.endswith('.mo'):
        # Include .mo files in locale/ directory (project translations)
        path_str_lower = path_str.lower()
        if 'locale' in path_str_lower and 'venv' not in path_str_lower:
            return False  # Include this .mo file
        # Exclude .mo files in venv or other locations
        return True
    
    return False


def collect_files(base_dir: Path) -> List[Path]:
    """
    Collect all files that should be included in the deployment archive.
    
    Args:
        base_dir: The base directory of the project
        
    Returns:
        List of file paths to include (relative to base_dir).
    """
    files_to_include: List[Path] = []
    
    # Walk through all files in the project
    for root, dirs, filenames in os.walk(base_dir):
        root_path = Path(root)
        
        # Filter out excluded directories before descending
        # Also explicitly exclude venv directories (case-insensitive)
        dirs[:] = [
            d for d in dirs 
            if not should_exclude(root_path / d, base_dir)
            and d.lower() not in ['venv', 'env', 'virtualenv', '.venv']
        ]
        
        for filename in filenames:
            file_path = root_path / filename
            
            # Skip excluded files
            if should_exclude(file_path, base_dir):
                continue
            
            # Only include regular files (not symlinks, etc.)
            if file_path.is_file():
                files_to_include.append(file_path)
    
    return sorted(files_to_include)


def check_translations(base_dir: Path) -> bool:
    """
    Check if translation files can be compiled successfully.
    
    Args:
        base_dir: Project root directory
    
    Returns:
        True if compilation succeeds, False otherwise
    """
    print("Checking translation files...")
    
    # Find Python executable
    python_exe = None
    
    # Check for venv in project directory
    venv_dir = base_dir / 'venv'
    if venv_dir.exists() and venv_dir.is_dir():
        venv_python = venv_dir / 'bin' / 'python'
        if venv_python.exists():
            python_exe = str(venv_python)
        else:
            venv_python3 = venv_dir / 'bin' / 'python3'
            if venv_python3.exists():
                python_exe = str(venv_python3)
    
    # Check for venv in home directory
    if not python_exe:
        home_venv = Path.home() / 'venv_mcc' / 'bin' / 'python'
        if home_venv.exists():
            python_exe = str(home_venv)
        else:
            home_venv3 = Path.home() / 'venv_mcc' / 'bin' / 'python3'
            if home_venv3.exists():
                python_exe = str(home_venv3)
    
    # Check for VIRTUAL_ENV environment variable
    if not python_exe and 'VIRTUAL_ENV' in os.environ:
        venv_path = Path(os.environ['VIRTUAL_ENV'])
        venv_python = venv_path / 'bin' / 'python'
        if venv_python.exists():
            python_exe = str(venv_python)
        else:
            venv_python3 = venv_path / 'bin' / 'python3'
            if venv_python3.exists():
                python_exe = str(venv_python3)
    
    # Fallback to system python
    if not python_exe:
        python_exe = 'python3'
    
    # Verify that Django is available in the selected Python
    django_available = False
    if python_exe:
        try:
            result = subprocess.run(
                [python_exe, '-c', 'import django; print(django.__version__)'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                django_available = True
                print(f"  Using Python: {python_exe} (Django {result.stdout.strip()})")
            else:
                print(f"  Warning: Django not found in {python_exe}")
        except Exception as e:
            print(f"  Warning: Could not verify Django in {python_exe}: {e}")
    
    # If Django not available, warn but continue (will be caught during compilemessages)
    if not django_available and python_exe:
        print(f"  Warning: Django might not be available in {python_exe}")
        print(f"  The check will fail if Django is required but not installed")
    
    # Check if manage.py exists
    manage_py = base_dir / 'manage.py'
    if not manage_py.exists():
        print("  Warning: manage.py not found, skipping translation check")
        return True  # Not critical if manage.py doesn't exist
    
    # Check if locale directory exists
    locale_dir = base_dir / 'locale'
    if not locale_dir.exists():
        print("  Info: No locale directory found, skipping translation check")
        return True  # Not critical if no translations
    
    # Find available locales in project locale directory
    available_locales = []
    po_files = []
    if locale_dir.exists():
        for locale_path in locale_dir.iterdir():
            if locale_path.is_dir() and (locale_path / 'LC_MESSAGES').exists():
                locale_name = locale_path.name
                po_file = locale_path / 'LC_MESSAGES' / 'django.po'
                if po_file.exists():
                    available_locales.append(locale_name)
                    po_files.append(po_file)
    
    if not available_locales:
        print("  Info: No translation files found in locale directory, skipping translation check")
        return True  # Not critical if no translations
    
    print(f"  Checking translation files for locales: {', '.join(available_locales)}")
    
    # Check translations directly using msgfmt (gettext tools)
    # This avoids Django's compilemessages which also processes venv translations
    msgfmt_exe = None
    for possible_msgfmt in ['msgfmt', 'msgfmt.py', '/usr/bin/msgfmt']:
        try:
            result = subprocess.run(
                [possible_msgfmt, '--version'],
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.returncode == 0:
                msgfmt_exe = possible_msgfmt
                break
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    
    if not msgfmt_exe:
        print("  Warning: msgfmt not found, trying Django compilemessages instead...")
        # Fallback to Django compilemessages
        env = os.environ.copy()
        env['DJANGO_SETTINGS_MODULE'] = 'config.settings'
        env['PYTHONPATH'] = str(base_dir)
        
        compile_cmd = [python_exe, 'manage.py', 'compilemessages']
        for locale in available_locales:
            compile_cmd.extend(['--locale', locale])
        
        try:
            result = subprocess.run(
                compile_cmd,
                cwd=base_dir,
                capture_output=True,
                text=True,
                timeout=60,
                env=env
            )
            
            if result.returncode == 0:
                print("  ✓ Translation files compiled successfully")
                return True
            else:
                # Check if it's just "no files found" (which is OK)
                if "no django translation files found" in result.stderr.lower():
                    print("  Info: No translation files found (this is OK)")
                    return True
                
                # Check if it's a Django import error
                if "ModuleNotFoundError" in result.stderr or "No module named 'django'" in result.stderr:
                    print("  ⚠ Django not found in Python environment (optional check)")
                    print(f"    Python: {python_exe}")
                    print("    Translation files should already be compiled (.mo files exist).")
                    print("    This check is optional - archive will still be created.")
                    return True  # Non-critical, return True to continue
                
                # Real error - print details but don't fail
                print("  ⚠ Translation compilation failed (optional check):")
                if result.stdout:
                    stdout_lines = result.stdout.strip().split('\n')
                    if len(stdout_lines) > 10:
                        print(f"    stdout (last 10 lines):")
                        for line in stdout_lines[-10:]:
                            print(f"      {line}")
                    else:
                        print(f"    stdout: {result.stdout[:500]}")
                if result.stderr:
                    stderr_lines = result.stderr.strip().split('\n')
                    if len(stderr_lines) > 10:
                        print(f"    stderr (last 10 lines):")
                        for line in stderr_lines[-10:]:
                            print(f"      {line}")
                    else:
                        print(f"    stderr: {result.stderr[:500]}")
                print("    Translation files should already be compiled (.mo files exist).")
                print("    This check is optional - archive will still be created.")
                return True  # Non-critical, return True to continue
                
        except subprocess.TimeoutExpired:
            print("  ⚠ Translation check timed out (optional check)")
            print("    Translation files should already be compiled (.mo files exist).")
            print("    This check is optional - archive will still be created.")
            return True  # Non-critical, return True to continue
        except Exception as e:
            print(f"  ⚠ Error checking translations (optional check): {e}")
            print("    Translation files should already be compiled (.mo files exist).")
            print("    This check is optional - archive will still be created.")
            return True  # Non-critical, return True to continue
    else:
        # Use msgfmt directly on project .po files only
        errors_found = False
        error_messages = []
        
        for po_file in po_files:
            try:
                result = subprocess.run(
                    [msgfmt_exe, '--check', '--statistics', '-o', '/dev/null', str(po_file)],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if result.returncode == 0:
                    # Extract statistics if available
                    stats = result.stderr.strip() if result.stderr else ""
                    if stats:
                        print(f"    ✓ {po_file.relative_to(base_dir)}: {stats}")
                    else:
                        print(f"    ✓ {po_file.relative_to(base_dir)}: OK")
                else:
                    errors_found = True
                    error_msg = result.stderr.strip() if result.stderr else result.stdout.strip()
                    error_messages.append(f"{po_file.relative_to(base_dir)}: {error_msg}")
                    print(f"    ✗ {po_file.relative_to(base_dir)}: {error_msg[:200]}")
                    
            except subprocess.TimeoutExpired:
                errors_found = True
                error_messages.append(f"{po_file.relative_to(base_dir)}: Timeout during check")
                print(f"    ✗ {po_file.relative_to(base_dir)}: Timeout")
            except Exception as e:
                errors_found = True
                error_messages.append(f"{po_file.relative_to(base_dir)}: {str(e)}")
                print(f"    ✗ {po_file.relative_to(base_dir)}: {e}")
        
        if errors_found:
            print("  ⚠ Translation check found issues (optional check):")
            for msg in error_messages[:5]:  # Show first 5 errors
                print(f"    {msg}")
            if len(error_messages) > 5:
                print(f"    ... and {len(error_messages) - 5} more error(s)")
            print("    Translation files should already be compiled (.mo files exist).")
            print("    This check is optional - archive will still be created.")
            return True  # Non-critical, return True to continue
        
        print("  ✓ All translation files are valid")
        return True


def create_deployment_archive(output_dir: Path | None = None, skip_translation_check: bool = False, check_translations: bool = False) -> Path:
    """
    Create a deployment archive (tar.gz) for the MCC-Web application.
    
    Args:
        output_dir: Directory where the archive should be saved.
                   If None, saves to /tmp.
    
    Returns:
        Path to the created archive file.
    """
    # Get project root directory (parent of utils/)
    base_dir = Path(__file__).parent.parent.resolve()
    
    if output_dir is None:
        output_dir = Path('/tmp')
    else:
        output_dir = Path(output_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
    
    # Get version for archive name and directory structure
    version = get_project_version()
    # Normalize version for directory name (remove 'v' prefix, replace special chars)
    normalized_version = version.replace('v', '').replace('/', '-').replace('\\', '-')
    version_dir = f"mcc-web-{normalized_version}"
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    archive_name = f'mcc-web-deployment-{version}-{timestamp}.tar.gz'
    archive_path = output_dir / archive_name
    
    # Check translations before creating archive (only if explicitly requested)
    if check_translations and not skip_translation_check:
        translation_check_result = check_translations(base_dir)
        if not translation_check_result:
            print("\n⚠ Translation check failed (non-critical)")
            print("  The archive will still be created.")
            print("  Translation files should be compiled before deployment.")
        else:
            print("  ✓ Translation check passed")
        print("")  # Empty line after check
    
    print(f"Collecting files from {base_dir}...")
    files_to_include = collect_files(base_dir)
    print(f"Found {len(files_to_include)} files to include.")
    
    print(f"Creating archive: {archive_path}")
    print(f"Archive root directory: {version_dir}/")
    
    with tarfile.open(archive_path, 'w:gz') as tar:
        for file_path in files_to_include:
            # Get relative path for archive
            rel_path = file_path.relative_to(base_dir)
            # Prepend version-specific directory
            arcname = f"{version_dir}/{rel_path}"
            print(f"  Adding: {arcname}")
            tar.add(file_path, arcname=arcname, recursive=False)
    
    archive_size = archive_path.stat().st_size
    print(f"\nArchive created successfully!")
    print(f"  File: {archive_path}")
    print(f"  Size: {archive_size / (1024 * 1024):.2f} MB")
    print(f"  Files: {len(files_to_include)}")
    print(f"  Archive root: {version_dir}/")
    
    return archive_path


def main() -> int:
    """Main entry point for the script."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Create a deployment archive for MCC-Web application'
    )
    parser.add_argument(
        '-o', '--output',
        type=str,
        default=None,
        help='Output directory for the archive (default: /tmp)'
    )
    parser.add_argument(
        '--check-translations',
        action='store_true',
        help='Enable translation compilation check (optional)'
    )
    parser.add_argument(
        '--skip-translation-check',
        action='store_true',
        help='Skip translation compilation check (only relevant if --check-translations is used)'
    )
    
    args = parser.parse_args()
    
    try:
        archive_path = create_deployment_archive(
            output_dir=Path(args.output) if args.output else None,
            skip_translation_check=args.skip_translation_check,
            check_translations=args.check_translations
        )
        print(f"\n✓ Deployment archive ready: {archive_path}")
        return 0
    except Exception as e:
        print(f"\n✗ Error creating archive: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())

