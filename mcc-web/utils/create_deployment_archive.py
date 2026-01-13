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
from typing import List, Set


def get_project_version() -> str:
    """
    Get project version from version.txt file or fallback to git describe.
    
    Returns:
        Version string (e.g., "1.0.0" or "v1.0.0-5-gabc1234").
    """
    # Get project root directory (parent of utils/)
    base_dir = Path(__file__).parent.parent
    version_file = base_dir / 'version.txt'
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
            cwd=base_dir,
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    
    return 'dev'


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
        'db.sqlite3',
        'db.sqlite3-journal',
        'db.sqlite3-shm',
        'db.sqlite3-wal',
        'db.sqlite3.old',
        'staticfiles',
        'media',
        'messages.mo',  # Compiled translation files (will be generated)
        
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
    
    # Check if any part of the path matches an exclude pattern
    for part in path_parts:
        if part.startswith('.'):
            # Hidden files/directories (except some we want to keep)
            if part not in ['.gitignore']:  # We might want to keep .gitignore for reference
                return True
        
        # Check exact matches
        if part in exclude_patterns:
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
    
    # Special case: exclude .mo files (compiled translations) but keep .po files
    if filename.endswith('.mo'):
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
        dirs[:] = [d for d in dirs if not should_exclude(root_path / d, base_dir)]
        
        for filename in filenames:
            file_path = root_path / filename
            
            # Skip excluded files
            if should_exclude(file_path, base_dir):
                continue
            
            # Only include regular files (not symlinks, etc.)
            if file_path.is_file():
                files_to_include.append(file_path)
    
    return sorted(files_to_include)


def create_deployment_archive(output_dir: Path | None = None) -> Path:
    """
    Create a deployment archive (tar.gz) for the MCC-Web application.
    
    Args:
        output_dir: Directory where the archive should be saved.
                   If None, saves to the project root.
    
    Returns:
        Path to the created archive file.
    """
    # Get project root directory (parent of utils/)
    base_dir = Path(__file__).parent.parent.resolve()
    
    if output_dir is None:
        output_dir = base_dir
    else:
        output_dir = Path(output_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
    
    # Get version for archive name
    version = get_project_version()
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    archive_name = f'mcc-web-deployment-{version}-{timestamp}.tar.gz'
    archive_path = output_dir / archive_name
    
    print(f"Collecting files from {base_dir}...")
    files_to_include = collect_files(base_dir)
    print(f"Found {len(files_to_include)} files to include.")
    
    print(f"Creating archive: {archive_path}")
    
    with tarfile.open(archive_path, 'w:gz') as tar:
        for file_path in files_to_include:
            # Get relative path for archive
            arcname = file_path.relative_to(base_dir)
            print(f"  Adding: {arcname}")
            tar.add(file_path, arcname=arcname, recursive=False)
    
    archive_size = archive_path.stat().st_size
    print(f"\nArchive created successfully!")
    print(f"  File: {archive_path}")
    print(f"  Size: {archive_size / (1024 * 1024):.2f} MB")
    print(f"  Files: {len(files_to_include)}")
    
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
        help='Output directory for the archive (default: project root)'
    )
    
    args = parser.parse_args()
    
    try:
        archive_path = create_deployment_archive(
            output_dir=Path(args.output) if args.output else None
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

