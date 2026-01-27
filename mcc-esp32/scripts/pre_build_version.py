#!/usr/bin/env python3
"""
Pre-build script to set FIRMWARE_VERSION build flag.
Reads version from environment variable or VERSION file.
"""

import os
import re
from pathlib import Path

Import("env")

def get_version():
    """Get version from environment variable or VERSION file."""
    # Try environment variable first
    version = os.getenv("FIRMWARE_VERSION")
    if version:
        return version
    
    # Try VERSION file - use PROJECT_DIR from PlatformIO env
    project_dir = Path(env["PROJECT_DIR"])
    version_file = project_dir / 'VERSION'
    if version_file.exists():
        try:
            version = version_file.read_text().strip()
            if re.match(r'^\d+\.\d+\.\d+', version):
                return version
        except (IOError, ValueError):
            pass
    
    # Default version
    return "1.0.0"

version = get_version()
print(f"Setting FIRMWARE_VERSION to: {version}")

# Add version as build flag
env.Append(CPPDEFINES=[
    ("FIRMWARE_VERSION", f'\\"{version}\\"')
])
