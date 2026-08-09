from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from minecraft.models import MinecraftOutboxEvent
from minecraft.services.worker import is_transient_minecraft_error


def cleanup_outbox() -> dict:
    """
    Prune old done/failed outbox rows and drop stale RCON-outage failures.

    Failed events from Paper/Velocity downtime stay forever under the TTL alone
    (default 30 days) and are not auto-requeued when the German
    ``…-RCON nicht erreichbar`` message does not match English errno markers.
    Admin „Postausgang bereinigen“ therefore also deletes those transient
    failures immediately — current team scores are restored via a follow-up sync.
    """
    now = timezone.now()
    done_cutoff = now - timedelta(days=settings.MCC_MINECRAFT_OUTBOX_DONE_TTL_DAYS)
    failed_cutoff = now - timedelta(days=settings.MCC_MINECRAFT_OUTBOX_FAILED_TTL_DAYS)

    deleted_done, _ = MinecraftOutboxEvent.objects.filter(
        status=MinecraftOutboxEvent.STATUS_DONE,
        created_at__lt=done_cutoff,
    ).delete()

    deleted_failed, _ = MinecraftOutboxEvent.objects.filter(
        status=MinecraftOutboxEvent.STATUS_FAILED,
        created_at__lt=failed_cutoff,
    ).delete()

    # Drop remaining failed rows caused by RCON/Minecraft outages (any age).
    deleted_transient = 0
    transient_ids: list[int] = []
    for event_id, last_error in (
        MinecraftOutboxEvent.objects.filter(status=MinecraftOutboxEvent.STATUS_FAILED)
        .values_list("id", "last_error")
        .iterator(chunk_size=500)
    ):
        if is_transient_minecraft_error(last_error):
            transient_ids.append(event_id)
    if transient_ids:
        deleted_transient, _ = MinecraftOutboxEvent.objects.filter(
            id__in=transient_ids
        ).delete()

    max_events = settings.MCC_MINECRAFT_OUTBOX_MAX_EVENTS
    deleted_overflow = 0
    if max_events and max_events > 0:
        total = MinecraftOutboxEvent.objects.count()
        if total > max_events:
            overflow = total - max_events
            overflow_ids = list(
                MinecraftOutboxEvent.objects.filter(
                    status=MinecraftOutboxEvent.STATUS_DONE
                ).order_by("created_at").values_list("id", flat=True)[:overflow]
            )
            if overflow_ids:
                deleted_overflow, _ = MinecraftOutboxEvent.objects.filter(id__in=overflow_ids).delete()

    return {
        "deleted_done": deleted_done,
        "deleted_failed": deleted_failed,
        "deleted_transient_failed": deleted_transient,
        "deleted_overflow": deleted_overflow,
    }
