#!/usr/bin/env python3
"""
Pre-build script to set FIRMWARE_VERSION build flag.
Reads version from version.txt file in project root.
"""

import re
from pathlib import Path

Import("env")

def get_version():
    """Get version from version.txt file."""
    # Read version.txt from project directory
    project_dir = Path(env["PROJECT_DIR"])
    version_file = project_dir / 'version.txt'
    if version_file.exists():
        try:
            version = version_file.read_text().strip()
            # Validate version format (semantic versioning: x.y.z)
            if re.match(r'^\d+\.\d+\.\d+', version):
                return version
            else:
                print(f"Warning: Invalid version format in version.txt: {version}")
        except (IOError, ValueError) as e:
            print(f"Warning: Error reading version.txt: {e}")
    
    # Default version if file not found or invalid
    print("Warning: version.txt not found or invalid, using default version 1.0.0")
    return "1.0.0"

version = get_version()
print(f"Setting FIRMWARE_VERSION to: {version}")

# Add version as build flag
env.Append(CPPDEFINES=[
    ("FIRMWARE_VERSION", f'\\"{version}\\"')
])
