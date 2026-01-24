from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from minecraft.models import MinecraftOutboxEvent


def cleanup_outbox() -> dict:
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
        "deleted_overflow": deleted_overflow,
    }
