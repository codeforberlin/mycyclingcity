from django.conf import settings
from django.utils import timezone

from api.models import Group
from config.logger_utils import get_logger
from minecraft.models import MinecraftPlayerScoreboardSnapshot
from minecraft.services import rcon_client


logger = get_logger("minecraft")


def ensure_group_velos_scoreboards():
    rcon_client.ensure_objective(
        settings.MCC_MINECRAFT_SCOREBOARD_GROUP_VELOS_TOTAL,
        "Gruppen-Velos gesamt",
    )
    rcon_client.ensure_objective(
        settings.MCC_MINECRAFT_SCOREBOARD_GROUP_VELOS_SPENDABLE,
        "Gruppen-Velos ausgebbar",
    )


def update_snapshot(
    player: str,
    velos_total: int,
    velos_spendable: int,
    *,
    group_id: int | None = None,
    cyclist_id: int | None = None,
) -> None:
    original_total = int(velos_total)
    original_spendable = int(velos_spendable)
    safe_total = max(0, original_total)
    safe_spendable = max(0, original_spendable)

    if original_total < 0 or original_spendable < 0:
        logger.warning(
            "[minecraft_snapshot] negative values detected for player=%s "
            "total=%s spendable=%s, clamped to total=%s spendable=%s",
            player,
            original_total,
            original_spendable,
            safe_total,
            safe_spendable,
        )

    snapshot, _created = MinecraftPlayerScoreboardSnapshot.objects.update_or_create(
        player_name=player,
        defaults={
            "velos_total": safe_total,
            "velos_spendable": safe_spendable,
            "group_id": group_id,
            "cyclist_id": cyclist_id,
            "source": "rcon",
            "captured_at": timezone.now(),
        },
    )
    logger.debug("[minecraft_snapshot] updated for player=%s", snapshot.player_name)


def refresh_scoreboard_snapshot() -> int:
    """Read group Velos scoreboards from Minecraft and optionally sync spendable to DB."""
    ensure_group_velos_scoreboards()
    groups = Group.objects.filter(mc_username__isnull=False).exclude(mc_username='')
    updated = 0
    logger.info("[minecraft_snapshot] refreshing snapshot for %s groups", groups.count())

    for group in groups:
        mc_username = group.mc_username
        total = rcon_client.get_player_score(
            mc_username,
            settings.MCC_MINECRAFT_SCOREBOARD_GROUP_VELOS_TOTAL,
        )
        spendable = rcon_client.get_player_score(
            mc_username,
            settings.MCC_MINECRAFT_SCOREBOARD_GROUP_VELOS_SPENDABLE,
        )
        if total is None and spendable is None:
            logger.info("[minecraft_snapshot] skipping group=%s (no scores found)", mc_username)
            continue

        db_updated = False
        if settings.MCC_MINECRAFT_SNAPSHOT_UPDATE_DB_SPENDABLE and spendable is not None:
            old_spendable = int(group.velos_spendable or 0)
            new_spendable = max(0, int(spendable))
            if new_spendable != old_spendable:
                Group.objects.filter(pk=group.pk).update(velos_spendable=new_spendable)
                db_updated = True
                logger.info(
                    "[minecraft_snapshot] updated DB velos_spendable for group=%s "
                    "mc=%s old=%s new=%s",
                    group.name,
                    mc_username,
                    old_spendable,
                    new_spendable,
                )

        safe_total = max(0, int(total)) if total is not None else int(group.velos_total or 0)
        safe_spendable = max(0, int(spendable)) if spendable is not None else int(group.velos_spendable or 0)

        update_snapshot(
            mc_username,
            safe_total,
            safe_spendable,
            group_id=group.id,
        )
        logger.info(
            "[minecraft_snapshot] snapshot updated group=%s total=%s spendable=%s db_updated=%s",
            mc_username,
            safe_total,
            safe_spendable,
            db_updated,
        )
        updated += 1

    logger.info("[minecraft_snapshot] refreshed: %s groups", updated)
    return updated
