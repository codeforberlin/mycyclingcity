from django.utils import timezone

from config.logger_utils import get_logger
from minecraft.models import MinecraftOutboxEvent


logger = get_logger("minecraft")


def queue_group_velos_update(
    player: str,
    velos_total: int,
    velos_spendable: int,
    reason: str,
    spendable_action: str = "set",
    spendable_delta: int | None = None,
) -> MinecraftOutboxEvent:
    payload = {
        "player": player,
        "velos_total": int(velos_total),
        "velos_spendable": int(velos_spendable),
        "reason": reason,
        "spendable_action": spendable_action,
        "spendable_delta": int(spendable_delta) if spendable_delta is not None else None,
        "queued_at": timezone.now().isoformat(),
    }
    event = MinecraftOutboxEvent.objects.create(
        event_type=MinecraftOutboxEvent.EVENT_UPDATE_GROUP_VELOS,
        payload=payload,
    )
    logger.info(f"[minecraft_outbox] queued group velos for player={player} reason={reason}")
    return event


def queue_full_sync(reason: str) -> MinecraftOutboxEvent:
    payload = {
        "reason": reason,
        "queued_at": timezone.now().isoformat(),
    }
    event = MinecraftOutboxEvent.objects.create(
        event_type=MinecraftOutboxEvent.EVENT_SYNC_ALL,
        payload=payload,
    )
    logger.info("[minecraft_outbox] queued full sync")
    return event
