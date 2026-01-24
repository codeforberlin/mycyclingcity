from django.core.management.base import BaseCommand

from minecraft.services.outbox_cleanup import cleanup_outbox


class Command(BaseCommand):
    help = "Cleanup Minecraft outbox events based on retention policy."

    def handle(self, *args, **options):
        result = cleanup_outbox()
        self.stdout.write(
            self.style.SUCCESS(
                "Outbox cleanup done: "
                f"deleted_done={result['deleted_done']} "
                f"deleted_failed={result['deleted_failed']} "
                f"deleted_overflow={result['deleted_overflow']}"
            )
        )
