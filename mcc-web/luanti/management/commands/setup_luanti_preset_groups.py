from django.core.management.base import BaseCommand

from luanti.services.preset_groups import sync_luanti_preset_groups


class Command(BaseCommand):
    help = "Create/update Django auth groups for Luanti admin (luanti_admin, luanti_moderator)."

    def handle(self, *args, **options):
        for group_name, created, missing in sync_luanti_preset_groups():
            state = "created" if created else "updated"
            self.stdout.write(f"{group_name}: {state}")
            if missing:
                self.stdout.write(self.style.WARNING(f"  missing perms: {', '.join(missing)}"))
        self.stdout.write(self.style.SUCCESS("Done."))
