#!/usr/bin/env python3
"""
Extract version from Git tag or version.txt file.
Priority: Git tag > version.txt > default

Usage:
    python3 extract_version.py [--output-format=env|version]

Output formats:
    - env: Outputs as shell variable (VERSION=1.0.0)
    - version: Outputs only version number (1.0.0)
"""

import os
import re
import subprocess
import sys
from pathlib import Path


def get_version_from_git_tag():
    """Extract version from current Git tag."""
    try:
        # Check if we're on a tag
        result = subprocess.run(
            ['git', 'describe', '--exact-match', '--tags', 'HEAD'],
            capture_output=True,
            text=True,
            check=False
        )
        if result.returncode == 0:
            tag = result.stdout.strip()
            # Remove 'v' prefix if present (e.g., v1.0.0 -> 1.0.0)
            version = re.sub(r'^v', '', tag)
            if re.match(r'^\d+\.\d+\.\d+', version):
                return version
        
        # Check if we're on a branch that matches a tag pattern
        result = subprocess.run(
            ['git', 'describe', '--tags', '--abbrev=0'],
            capture_output=True,
            text=True,
            check=False
        )
        if result.returncode == 0:
            tag = result.stdout.strip()
            version = re.sub(r'^v', '', tag)
            if re.match(r'^\d+\.\d+\.\d+', version):
                return version
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    
    return None


def get_version_from_file():
    """Read version from version.txt file."""
    script_dir = Path(__file__).parent
    version_file = script_dir.parent / 'version.txt'
    
    if version_file.exists():
        try:
            version = version_file.read_text().strip()
            # Validate version format (semantic versioning)
            if re.match(r'^\d+\.\d+\.\d+', version):
                return version
        except (IOError, ValueError):
            pass
    
    return None


def get_default_version():
    """Return default version if nothing else is available."""
    return "1.0.0"


def main():
    """Main function to extract and output version."""
    output_format = 'version'
    
    # Parse command line arguments
    if len(sys.argv) > 1:
        for arg in sys.argv[1:]:
            if arg.startswith('--output-format='):
                output_format = arg.split('=', 1)[1]
    
    # Try to get version (priority: Git tag > version.txt > default)
    version = get_version_from_git_tag()
    if not version:
        version = get_version_from_file()
    if not version:
        version = get_default_version()
    
    # Output version in requested format
    if output_format == 'env':
        print(f"VERSION={version}")
    else:
        print(version)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
