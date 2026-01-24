# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    manage.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

import os
import sys

def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    
    # Get the correct project directory (where this manage.py file is located)
    project_dir = os.path.dirname(os.path.abspath(__file__))
    
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

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        # ... (error handling) ...
        raise exc
        
    execute_from_command_line(sys.argv)

if __name__ == '__main__':
    main()