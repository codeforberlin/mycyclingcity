from django.conf import settings
from django.db import connection, transaction

from api.models import Group
from config.logger_utils import get_logger
from minecraft.models import MinecraftOutboxEvent
from minecraft.services.scoreboard import ensure_group_velos_scoreboards
from minecraft.services import rcon_client


logger = get_logger("minecraft")


def _get_pending_event():
    qs = MinecraftOutboxEvent.objects.filter(status=MinecraftOutboxEvent.STATUS_PENDING).order_by("created_at")
    if connection.vendor != "sqlite":
        qs = qs.select_for_update(skip_locked=True)
    with transaction.atomic():
        event = qs.first()
        if not event:
            return None
        event.mark_processing()
        return event


def _handle_update_group_velos(event: MinecraftOutboxEvent) -> None:
    payload = event.payload or {}
    player = payload.get("player")
    if not player:
        raise ValueError("Missing player in payload")

    velos_total = int(payload.get("velos_total", 0))
    velos_spendable = int(payload.get("velos_spendable", 0))
    spendable_action = payload.get("spendable_action", "set")
    spendable_delta = payload.get("spendable_delta")
    reason = payload.get("reason", "unknown")

    logger.debug(
        f"[minecraft_worker] processing UPDATE_GROUP_VELOS event_id={event.id} "
        f"player={player} velos_total={velos_total} velos_spendable={velos_spendable} "
        f"spendable_action={spendable_action} spendable_delta={spendable_delta} reason={reason}"
    )

    if spendable_action == "set" and payload.get("reason") == "db_update" and spendable_delta is not None:
        spendable_action = "add"
        logger.debug("[minecraft_worker] converted group spendable_action from 'set' to 'add' (db_update with delta)")

    ensure_group_velos_scoreboards()
    rcon_client.set_player_score(
        player,
        settings.MCC_MINECRAFT_SCOREBOARD_GROUP_VELOS_TOTAL,
        velos_total,
    )

    if spendable_action == "add" and spendable_delta is not None:
        rcon_client.add_player_score(
            player,
            settings.MCC_MINECRAFT_SCOREBOARD_GROUP_VELOS_SPENDABLE,
            int(spendable_delta),
        )
    else:
        rcon_client.set_player_score(
            player,
            settings.MCC_MINECRAFT_SCOREBOARD_GROUP_VELOS_SPENDABLE,
            velos_spendable,
        )


def _handle_sync_all(event: MinecraftOutboxEvent) -> None:
    ensure_group_velos_scoreboards()
    groups = Group.objects.filter(mc_username__isnull=False).exclude(mc_username='')
    for group in groups:
        rcon_client.set_player_score(
            group.mc_username,
            settings.MCC_MINECRAFT_SCOREBOARD_GROUP_VELOS_TOTAL,
            int(group.velos_total),
        )
        rcon_client.set_player_score(
            group.mc_username,
            settings.MCC_MINECRAFT_SCOREBOARD_GROUP_VELOS_SPENDABLE,
            int(group.velos_spendable),
        )


def process_next_event() -> bool:
    event = _get_pending_event()
    if not event:
        return False

    logger.debug(f"[minecraft_worker] processing event_id={event.id} type={event.event_type} status={event.status}")
    try:
        if event.event_type == MinecraftOutboxEvent.EVENT_UPDATE_GROUP_VELOS:
            _handle_update_group_velos(event)
        elif event.event_type == MinecraftOutboxEvent.EVENT_SYNC_ALL:
            logger.debug(f"[minecraft_worker] processing SYNC_ALL event_id={event.id}")
            _handle_sync_all(event)
        elif event.event_type == MinecraftOutboxEvent.EVENT_UPDATE_PLAYER_COINS:
            logger.warning(f"[minecraft_worker] skipping deprecated UPDATE_PLAYER_COINS event_id={event.id}")
        else:
            raise ValueError(f"Unsupported event_type: {event.event_type}")
        event.mark_done()
        logger.info(f"[minecraft_worker] processed event_id={event.id} type={event.event_type}")
        return True
    except Exception as exc:
        logger.error(f"[minecraft_worker] event failed id={event.id} type={event.event_type}: {exc}", exc_info=True)
        event.mark_failed(str(exc))
        return True
