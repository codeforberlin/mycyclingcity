# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    generate_version.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
"""
Generate version.txt file for the MCC-Web application.

This script creates or updates the version.txt file in the project root.
The version is determined from:
1. Git tags (git describe --tags --always --dirty)
2. Manual version string (if provided via command line)
3. Fallback to 'dev' if git is not available

Usage:
    python utils/generate_version.py                    # Auto-detect from git
    python utils/generate_version.py --version 1.2.3     # Set specific version
    python utils/generate_version.py --tag              # Use current git tag
    python utils/generate_version.py --clean            # Remove version.txt
"""

import os
import sys
import subprocess
import argparse
from pathlib import Path


def get_git_version(base_dir: Path) -> str:
    """
    Get version from git describe.
    
    Args:
        base_dir: Project root directory
    
    Returns:
        Version string from git describe, or 'dev' if git is not available
    """
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
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        pass
    
    return 'dev'


def get_current_git_tag(base_dir: Path) -> str | None:
    """
    Get the current git tag if HEAD is on a tag.
    
    Args:
        base_dir: Project root directory
    
    Returns:
        Tag name if HEAD is on a tag, None otherwise
    """
    try:
        # Check if HEAD is on a tag
        result = subprocess.run(
            ['git', 'describe', '--exact-match', '--tags', 'HEAD'],
            cwd=base_dir,
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        pass
    
    return None


def write_version_file(base_dir: Path, version: str) -> bool:
    """
    Write version to version.txt file.
    
    Args:
        base_dir: Project root directory
        version: Version string to write
    
    Returns:
        True if successful, False otherwise
    """
    version_file = base_dir / 'version.txt'
    try:
        with open(version_file, 'w', encoding='utf-8') as f:
            f.write(version + '\n')
        return True
    except Exception as e:
        print(f"Error writing version.txt: {e}", file=sys.stderr)
        return False


def read_version_file(base_dir: Path) -> str | None:
    """
    Read version from version.txt file if it exists.
    
    Args:
        base_dir: Project root directory
    
    Returns:
        Version string if file exists, None otherwise
    """
    version_file = base_dir / 'version.txt'
    if version_file.exists():
        try:
            with open(version_file, 'r', encoding='utf-8') as f:
                version = f.read().strip()
                if version:
                    return version
        except Exception:
            pass
    return None


def remove_version_file(base_dir: Path) -> bool:
    """
    Remove version.txt file.
    
    Args:
        base_dir: Project root directory
    
    Returns:
        True if successful, False otherwise
    """
    version_file = base_dir / 'version.txt'
    try:
        if version_file.exists():
            version_file.unlink()
            return True
        return False
    except Exception as e:
        print(f"Error removing version.txt: {e}", file=sys.stderr)
        return False


def main() -> int:
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description='Generate or update version.txt file for MCC-Web',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python utils/generate_version.py                    # Auto-detect from git
  python utils/generate_version.py --version 1.2.3   # Set specific version
  python utils/generate_version.py --tag              # Use current git tag
  python utils/generate_version.py --clean            # Remove version.txt
  python utils/generate_version.py --force            # Overwrite existing version.txt
        """
    )
    
    parser.add_argument(
        '--version', '-v',
        type=str,
        help='Set specific version string (e.g., "1.2.3" or "v1.0.0")'
    )
    
    parser.add_argument(
        '--tag', '-t',
        action='store_true',
        help='Use current git tag if HEAD is on a tag, otherwise use git describe'
    )
    
    parser.add_argument(
        '--clean', '-c',
        action='store_true',
        help='Remove version.txt file'
    )
    
    parser.add_argument(
        '--force', '-f',
        action='store_true',
        help='Overwrite existing version.txt without prompting'
    )
    
    parser.add_argument(
        '--quiet', '-q',
        action='store_true',
        help='Suppress output messages'
    )
    
    args = parser.parse_args()
    
    # Get project root directory (parent of utils/)
    base_dir = Path(__file__).parent.parent.resolve()
    
    # Handle clean option
    if args.clean:
        if remove_version_file(base_dir):
            if not args.quiet:
                print("✓ Removed version.txt")
            return 0
        else:
            if not args.quiet:
                print("✗ version.txt does not exist or could not be removed", file=sys.stderr)
            return 1
    
    # Determine version
    version = None
    
    if args.version:
        # Use provided version
        version = args.version
    elif args.tag:
        # Try to get current git tag
        version = get_current_git_tag(base_dir)
        if version is None:
            # Fallback to git describe if not on a tag
            version = get_git_version(base_dir)
            if not args.quiet:
                print(f"⚠ Not on a tag, using git describe: {version}")
    else:
        # Auto-detect from git
        version = get_git_version(base_dir)
    
    # Check if version.txt already exists
    existing_version = read_version_file(base_dir)
    if existing_version and not args.force:
        if not args.quiet:
            print(f"⚠ version.txt already exists with version: {existing_version}")
            print(f"  Use --force to overwrite with: {version}")
        return 0
    
    # Write version file
    if write_version_file(base_dir, version):
        if not args.quiet:
            print(f"✓ Created/updated version.txt with version: {version}")
        return 0
    else:
        if not args.quiet:
            print("✗ Failed to write version.txt", file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
