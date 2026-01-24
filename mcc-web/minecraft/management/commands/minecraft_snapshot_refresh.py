from django.core.management.base import BaseCommand

from minecraft.services.scoreboard import refresh_scoreboard_snapshot


class Command(BaseCommand):
    help = "Refresh Minecraft scoreboard snapshots from the server."

    def handle(self, *args, **options):
        updated = refresh_scoreboard_snapshot()
        self.stdout.write(self.style.SUCCESS(f"Updated {updated} scoreboard snapshots"))
