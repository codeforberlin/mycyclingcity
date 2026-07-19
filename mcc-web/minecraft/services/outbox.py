from django.utils import timezone

from config.logger_utils import get_logger
from minecraft.models import MinecraftOutboxEvent


logger = get_logger("minecraft")


def queue_team_velos_update(
    player: str,
    velos_spendable: int,
    reason: str,
    spendable_action: str = "set",
    spendable_delta: int | None = None,
) -> MinecraftOutboxEvent:
    payload = {
        "player": player,
        "velos_spendable": int(velos_spendable),
        "reason": reason,
        "spendable_action": spendable_action,
        "spendable_delta": int(spendable_delta) if spendable_delta is not None else None,
        "queued_at": timezone.now().isoformat(),
    }
    event = MinecraftOutboxEvent.objects.create(
        event_type=MinecraftOutboxEvent.EVENT_UPDATE_TEAM_VELOS,
        payload=payload,
    )
    logger.info(f"[minecraft_outbox] queued team velos for player={player} reason={reason}")
    return event


def queue_register_team(
    registration_id: int,
    reason: str = "manual_register",
) -> MinecraftOutboxEvent:
    payload = {
        "registration_id": registration_id,
        "reason": reason,
        "queued_at": timezone.now().isoformat(),
    }
    event = MinecraftOutboxEvent.objects.create(
        event_type=MinecraftOutboxEvent.EVENT_REGISTER_TEAM,
        payload=payload,
    )
    logger.info(f"[minecraft_outbox] queued register_team registration_id={registration_id}")
    return event


def queue_unregister_team(
    mc_username: str,
    reason: str = "unregister",
) -> MinecraftOutboxEvent:
    payload = {
        "player": mc_username,
        "reason": reason,
        "queued_at": timezone.now().isoformat(),
    }
    event = MinecraftOutboxEvent.objects.create(
        event_type=MinecraftOutboxEvent.EVENT_UNREGISTER_TEAM,
        payload=payload,
    )
    logger.info(f"[minecraft_outbox] queued unregister_team player={mc_username}")
    return event


def queue_sync_registered_teams(reason: str) -> MinecraftOutboxEvent:
    payload = {
        "reason": reason,
        "queued_at": timezone.now().isoformat(),
    }
    event = MinecraftOutboxEvent.objects.create(
        event_type=MinecraftOutboxEvent.EVENT_SYNC_REGISTERED_TEAMS,
        payload=payload,
    )
    logger.info("[minecraft_outbox] queued sync registered teams")
    return event


def queue_ensure_objectives(reason: str = "ensure_objectives") -> MinecraftOutboxEvent:
    payload = {
        "reason": reason,
        "queued_at": timezone.now().isoformat(),
    }
    event = MinecraftOutboxEvent.objects.create(
        event_type=MinecraftOutboxEvent.EVENT_ENSURE_OBJECTIVES,
        payload=payload,
    )
    logger.info("[minecraft_outbox] queued ensure objectives")
    return event


# --- Legacy wrappers (map to new event types) ---


def queue_group_velos_update(
    player: str,
    velos_total: int,
    velos_spendable: int,
    reason: str,
    spendable_action: str = "set",
    spendable_delta: int | None = None,
) -> MinecraftOutboxEvent:
    """Legacy alias — only spendable is synced to Minecraft."""
    return queue_team_velos_update(
        player=player,
        velos_spendable=velos_spendable,
        reason=reason,
        spendable_action=spendable_action,
        spendable_delta=spendable_delta,
    )


def queue_full_sync(reason: str) -> MinecraftOutboxEvent:
    """Legacy alias for syncing all registered teams."""
    return queue_sync_registered_teams(reason=reason)
