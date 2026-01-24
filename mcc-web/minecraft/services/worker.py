from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone

from api.models import Cyclist
from config.logger_utils import get_logger
from minecraft.models import MinecraftOutboxEvent
from minecraft.services.scoreboard import ensure_scoreboards, update_snapshot
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


def _handle_update_player_coins(event: MinecraftOutboxEvent) -> None:
    payload = event.payload or {}
    player = payload.get("player")
    if not player:
        raise ValueError("Missing player in payload")

    coins_total = int(payload.get("coins_total", 0))
    coins_spendable = int(payload.get("coins_spendable", 0))
    spendable_action = payload.get("spendable_action", "set")
    spendable_delta = payload.get("spendable_delta")
    reason = payload.get("reason", "unknown")
    
    logger.debug(
        f"[minecraft_worker] processing UPDATE_PLAYER_COINS event_id={event.id} "
        f"player={player} coins_total={coins_total} coins_spendable={coins_spendable} "
        f"spendable_action={spendable_action} spendable_delta={spendable_delta} reason={reason}"
    )
    
    if spendable_action == "set" and payload.get("reason") == "db_update" and spendable_delta is not None:
        spendable_action = "add"
        logger.debug(f"[minecraft_worker] converted spendable_action from 'set' to 'add' (db_update with delta)")
    
    ensure_scoreboards()
    logger.debug(f"[minecraft_worker] setting player={player} objective={settings.MCC_MINECRAFT_SCOREBOARD_COINS_TOTAL} value={coins_total}")
    rcon_client.set_player_score(player, settings.MCC_MINECRAFT_SCOREBOARD_COINS_TOTAL, coins_total)
    
    if spendable_action == "add" and spendable_delta is not None:
        logger.debug(f"[minecraft_worker] adding player={player} objective={settings.MCC_MINECRAFT_SCOREBOARD_COINS_SPENDABLE} delta={spendable_delta}")
        rcon_client.add_player_score(
            player,
            settings.MCC_MINECRAFT_SCOREBOARD_COINS_SPENDABLE,
            int(spendable_delta),
        )
    else:
        logger.debug(f"[minecraft_worker] setting player={player} objective={settings.MCC_MINECRAFT_SCOREBOARD_COINS_SPENDABLE} value={coins_spendable}")
        rcon_client.set_player_score(
            player,
            settings.MCC_MINECRAFT_SCOREBOARD_COINS_SPENDABLE,
            coins_spendable,
        )

    cyclist = Cyclist.objects.filter(mc_username__iexact=player).only("id").first()
    update_snapshot(player, coins_total, coins_spendable, cyclist.id if cyclist else None)
    logger.debug(f"[minecraft_worker] snapshot updated for player={player} cyclist_id={cyclist.id if cyclist else None}")


def _handle_sync_all(event: MinecraftOutboxEvent) -> None:
    ensure_scoreboards()
    players = Cyclist.objects.filter(mc_username__isnull=False)
    for cyclist in players:
        if not cyclist.mc_username:
            continue
        rcon_client.set_player_score(
            cyclist.mc_username,
            settings.MCC_MINECRAFT_SCOREBOARD_COINS_TOTAL,
            int(cyclist.coins_total),
        )
        rcon_client.set_player_score(
            cyclist.mc_username,
            settings.MCC_MINECRAFT_SCOREBOARD_COINS_SPENDABLE,
            int(cyclist.coins_spendable),
        )
        update_snapshot(cyclist.mc_username, int(cyclist.coins_total), int(cyclist.coins_spendable), cyclist.id)


def process_next_event() -> bool:
    event = _get_pending_event()
    if not event:
        return False

    logger.debug(f"[minecraft_worker] processing event_id={event.id} type={event.event_type} status={event.status}")
    try:
        if event.event_type == MinecraftOutboxEvent.EVENT_UPDATE_PLAYER_COINS:
            _handle_update_player_coins(event)
        elif event.event_type == MinecraftOutboxEvent.EVENT_SYNC_ALL:
            logger.debug(f"[minecraft_worker] processing SYNC_ALL event_id={event.id}")
            _handle_sync_all(event)
        else:
            raise ValueError(f"Unsupported event_type: {event.event_type}")
        event.mark_done()
        logger.info(f"[minecraft_worker] processed event_id={event.id} type={event.event_type}")
        return True
    except Exception as exc:
        logger.error(f"[minecraft_worker] event failed id={event.id} type={event.event_type}: {exc}", exc_info=True)
        event.mark_failed(str(exc))
        return True
