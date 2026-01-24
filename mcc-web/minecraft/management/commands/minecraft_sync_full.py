from django.core.management.base import BaseCommand

from minecraft.services.outbox import queue_full_sync


class Command(BaseCommand):
    help = "Queue a full Minecraft scoreboard sync (manual)."

    def handle(self, *args, **options):
        queue_full_sync(reason="manual_full_sync")
        self.stdout.write(self.style.SUCCESS("Queued full Minecraft sync"))
