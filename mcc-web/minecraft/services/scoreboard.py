from django.conf import settings
from django.utils import timezone

from api.models import Cyclist
from config.logger_utils import get_logger
from minecraft.models import MinecraftPlayerScoreboardSnapshot
from minecraft.services import rcon_client


logger = get_logger("minecraft")


def ensure_scoreboards():
    rcon_client.ensure_objective(settings.MCC_MINECRAFT_SCOREBOARD_COINS_TOTAL, "Gesamt-Coins")
    rcon_client.ensure_objective(settings.MCC_MINECRAFT_SCOREBOARD_COINS_SPENDABLE, "Ausgebbare Coins")


def update_player_scores(player: str, coins_total: int, coins_spendable: int) -> None:
    rcon_client.set_player_score(player, settings.MCC_MINECRAFT_SCOREBOARD_COINS_TOTAL, coins_total)
    rcon_client.set_player_score(player, settings.MCC_MINECRAFT_SCOREBOARD_COINS_SPENDABLE, coins_spendable)


def update_snapshot(player: str, coins_total: int, coins_spendable: int, cyclist_id: int | None) -> None:
    # Ensure non-negative values for PositiveIntegerField
    original_total = int(coins_total)
    original_spendable = int(coins_spendable)
    safe_total = max(0, original_total)
    safe_spendable = max(0, original_spendable)
    
    # Log warning if negative values were found
    if original_total < 0 or original_spendable < 0:
        logger.warning(
            f"[minecraft_snapshot] negative values detected for player={player} "
            f"total={original_total} spendable={original_spendable}, "
            f"clamped to total={safe_total} spendable={safe_spendable}"
        )
    
    snapshot, _created = MinecraftPlayerScoreboardSnapshot.objects.update_or_create(
        player_name=player,
        defaults={
            "coins_total": safe_total,
            "coins_spendable": safe_spendable,
            "cyclist_id": cyclist_id,
            "source": "rcon",
            "captured_at": timezone.now(),
        },
    )
    logger.debug(f"[minecraft_snapshot] updated for player={snapshot.player_name}")


def refresh_scoreboard_snapshot() -> int:
    ensure_scoreboards()
    players = Cyclist.objects.filter(mc_username__isnull=False).values("id", "mc_username")
    updated = 0
    logger.info(f"[minecraft_snapshot] refreshing snapshot for {len(players)} players")
    for player in players:
        mc_username = player["mc_username"]
        if not mc_username:
            continue
        total = rcon_client.get_player_score(mc_username, settings.MCC_MINECRAFT_SCOREBOARD_COINS_TOTAL)
        spendable = rcon_client.get_player_score(mc_username, settings.MCC_MINECRAFT_SCOREBOARD_COINS_SPENDABLE)
        if total is None and spendable is None:
            logger.info(f"[minecraft_snapshot] skipping player={mc_username} (no scores found)")
            continue
        
        old_spendable = None
        if settings.MCC_MINECRAFT_SNAPSHOT_UPDATE_DB_SPENDABLE and spendable is not None:
            cyclist = Cyclist.objects.filter(id=player["id"]).only("coins_spendable").first()
            if cyclist:
                old_spendable = cyclist.coins_spendable
                Cyclist.objects.filter(id=player["id"]).update(coins_spendable=int(spendable))
                logger.info(
                    f"[minecraft_snapshot] updated DB spendable for player={mc_username} "
                    f"cyclist_id={player['id']} old={old_spendable} new={spendable}"
                )
        
        # Ensure non-negative values for PositiveIntegerField
        safe_total = max(0, int(total)) if total is not None else 0
        safe_spendable = max(0, int(spendable)) if spendable is not None else 0
        
        update_snapshot(
            mc_username,
            safe_total,
            safe_spendable,
            player["id"],
        )
        logger.info(
            f"[minecraft_snapshot] snapshot updated player={mc_username} "
            f"total={total} spendable={spendable} db_updated={old_spendable is not None}"
        )
        updated += 1
    logger.info(f"[minecraft_snapshot] refreshed: {updated} players")
    return updated
