from django.core.management.base import BaseCommand

from minecraft.services.outbox_cleanup import cleanup_outbox


class Command(BaseCommand):
    help = "Cleanup Minecraft outbox events based on retention policy."

    def handle(self, *args, **options):
        result = cleanup_outbox()
        sync_note = ""
        if result.get("deleted_transient_failed"):
            from minecraft.services.outbox import queue_sync_registered_teams

            queue_sync_registered_teams(reason="outbox_cleanup_after_rcon_outage")
            sync_note = " sync_queued=1"
        self.stdout.write(
            self.style.SUCCESS(
                "Outbox cleanup done: "
                f"deleted_done={result['deleted_done']} "
                f"deleted_failed={result['deleted_failed']} "
                f"deleted_transient_failed={result.get('deleted_transient_failed', 0)} "
                f"deleted_overflow={result['deleted_overflow']}"
                f"{sync_note}"
            )
        )
