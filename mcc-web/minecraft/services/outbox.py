from django.utils import timezone

from config.logger_utils import get_logger
from minecraft.models import MinecraftOutboxEvent


logger = get_logger("minecraft")


def queue_player_coins_update(
    player: str,
    coins_total: int,
    coins_spendable: int,
    reason: str,
    spendable_action: str = "set",
    spendable_delta: int | None = None,
) -> MinecraftOutboxEvent:
    payload = {
        "player": player,
        "coins_total": int(coins_total),
        "coins_spendable": int(coins_spendable),
        "reason": reason,
        "spendable_action": spendable_action,
        "spendable_delta": int(spendable_delta) if spendable_delta is not None else None,
        "queued_at": timezone.now().isoformat(),
    }
    event = MinecraftOutboxEvent.objects.create(
        event_type=MinecraftOutboxEvent.EVENT_UPDATE_PLAYER_COINS,
        payload=payload,
    )
    logger.info(f"[minecraft_outbox] queued update for player={player} reason={reason}")
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
