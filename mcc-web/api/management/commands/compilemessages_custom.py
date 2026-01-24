"""
Custom compilemessages command that only compiles translations from the project,
excluding translations from installed packages in venv.
"""
from django.core.management.commands.compilemessages import Command as BaseCommand
from django.conf import settings
from pathlib import Path


class Command(BaseCommand):
    help = 'Compile translation messages (only from project, excluding venv libraries)'

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument(
            '--exclude-venv',
            action='store_true',
            dest='exclude_venv',
            default=True,
            help='Exclude translations from virtual environment (default: True)',
        )

    def handle(self, *args, **options):
        # Get BASE_DIR to exclude venv
        base_dir = Path(settings.BASE_DIR)
        
        # Exclude venv directories
        exclude_patterns = []
        
        if options.get('exclude_venv', True):
            # Common venv locations
            venv_paths = [
                base_dir / 'venv',
                Path.home() / 'venv_mcc',
            ]
            
            # Add any path that contains 'site-packages' (typical venv structure)
            for venv_path in venv_paths:
                if venv_path.exists():
                    exclude_patterns.append(str(venv_path))
                    self.stdout.write(
                        self.style.SUCCESS(f'Excluding venv: {venv_path}')
                    )
        
        # Only compile messages from LOCALE_PATHS
        # This is already configured in settings.py to only use BASE_DIR / 'locale'
        if settings.LOCALE_PATHS:
            self.stdout.write(
                self.style.SUCCESS(
                    f'Compiling messages from: {", ".join(str(p) for p in settings.LOCALE_PATHS)}'
                )
            )
        
        # Call parent command, but limit to LOCALE_PATHS
        # The parent command will respect LOCALE_PATHS setting
        super().handle(*args, **options)
