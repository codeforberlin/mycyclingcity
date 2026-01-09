# /data/dev/mcc/manage.py

import os
import sys

def main():
    """Run administrative tasks."""
    # The settings module path is 'mcc.config.settings', since 'mcc' is the namespace
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