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
    
    # CORRECTION: Adds the project directory to the path
    # This allows Python to find the 'mcc' package
    if os.path.dirname(__file__) not in sys.path:
        sys.path.append(os.path.dirname(__file__))

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        # ... (error handling) ...
        raise exc
        
    execute_from_command_line(sys.argv)

if __name__ == '__main__':
    main()