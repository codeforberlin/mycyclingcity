# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    wsgi.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
import os
import sys
from pathlib import Path

# Get the correct project directory (where this wsgi.py file is located)
project_dir = str(Path(__file__).parent.parent)

# Remove any duplicate paths that might cause conflicts
# Keep only the correct project directory in sys.path
paths_to_remove = []
for path in sys.path:
    if path and path != project_dir:
        # Check if this path contains an 'api' directory that might conflict
        api_path = os.path.join(path, 'api')
        if os.path.isdir(api_path) and path != project_dir:
            paths_to_remove.append(path)

for path in paths_to_remove:
    if path in sys.path:
        sys.path.remove(path)

# Add the project directory to the path if not already present
if project_dir not in sys.path:
    sys.path.insert(0, project_dir)

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

application = get_wsgi_application()

# Import key modules at startup to trigger logger initialization
# This ensures that logger initialization logs are written at startup,
# not just when the first request arrives
try:
    # Import api.views to trigger logger initialization
    import api.views  # noqa: F401
except Exception:
    # Silently fail if import fails (e.g., during migrations)
    pass
