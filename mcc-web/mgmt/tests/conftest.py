# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    conftest.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

"""
Shared pytest fixtures for mgmt tests.

This module provides shared fixtures for mgmt tests.
"""

import pytest
import sys
import os

# Ensure we're using the correct project path
# This prevents issues when the project exists in multiple locations
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Remove any conflicting paths from sys.path before Django setup
# This must happen before any Django imports
_conflicting_paths = [
    '/nas/public/dev/mycyclingcity/mcc-web',
    '/data/games/mcc/mcc-web',
]

# Remove conflicting paths, keeping only the current project root
_paths_to_remove = []
for path in _conflicting_paths:
    normalized_path = os.path.normpath(path)
    normalized_project = os.path.normpath(_project_root)
    if normalized_path in sys.path and normalized_path != normalized_project:
        _paths_to_remove.append(normalized_path)

for path in _paths_to_remove:
    while path in sys.path:
        sys.path.remove(path)

# Add the current project root if not already present
normalized_project = os.path.normpath(_project_root)
if normalized_project not in sys.path:
    sys.path.insert(0, normalized_project)
