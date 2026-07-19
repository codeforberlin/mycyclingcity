# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

from django.conf import settings
from django.utils import timezone

from api.models import Group
from config.logger_utils import get_logger
from minecraft.models import MinecraftIntegrationConfig, MinecraftPlayerScoreboardSnapshot, MinecraftTeamRegistration
from minecraft.services import rcon_client
from minecraft.services.team_registration import (
    active_registrations,
    get_display_name,
    get_objective_spendable,
)


logger = get_logger("minecraft")


def ensure_team_scoreboard_objective() -> str:
    objective = get_objective_spendable()
    display_name = get_display_name()
    rcon_client.ensure_objective(objective, display_name)
    config = MinecraftIntegrationConfig.get_config()
    if config.sidebar_enabled:
        slot = getattr(settings, "MCC_MINECRAFT_SCOREBOARD_DISPLAY_SLOT", "sidebar") or "sidebar"
        rcon_client.set_objective_display(objective, slot)
    return objective


def set_team_spendable_score(mc_username: str, value: int) -> None:
    objective = ensure_team_scoreboard_objective()
    rcon_client.set_player_score(mc_username, objective, int(value))


def add_team_spendable_score(mc_username: str, delta: int) -> None:
    objective = ensure_team_scoreboard_objective()
    rcon_client.add_player_score(mc_username, objective, int(delta))


def reset_team_scoreboard_entry(mc_username: str) -> None:
    objective = get_objective_spendable()
    rcon_client.reset_player_score(mc_username, objective)


def sync_registration_spendable(registration: MinecraftTeamRegistration) -> None:
    group = registration.group
    set_team_spendable_score(registration.mc_username, int(group.velos_spendable or 0))
    registration.last_synced_at = timezone.now()
    registration.last_sync_error = ""
    registration.save(update_fields=["last_synced_at", "last_sync_error"])


def sync_all_registered_teams() -> int:
    ensure_team_scoreboard_objective()
    count = 0
    for registration in active_registrations():
        sync_registration_spendable(registration)
        count += 1
    logger.info("[minecraft_team_scoreboard] synced %s registered teams", count)
    return count


def register_team_on_server(registration: MinecraftTeamRegistration) -> None:
    from minecraft.services.bridge_team_mapping import push_team_mapping_to_bridge
    from minecraft.services.luckperms_sync import apply_luckperms_for_registration

    sync_registration_spendable(registration)
    lp_ok, lp_log = apply_luckperms_for_registration(registration)
    if not lp_ok:
        registration.last_sync_error = (lp_log or "")[:5000]
        registration.save(update_fields=["last_sync_error"])
        raise RuntimeError(f"LuckPerms sync failed: {lp_log}")
    registration.last_sync_error = ""
    registration.save(update_fields=["last_sync_error"])
    push_team_mapping_to_bridge(registration.mc_username)


def unregister_team_on_server(mc_username: str) -> None:
    from minecraft.models import MinecraftTeamRegistration
    from minecraft.services.bridge_team_mapping import remove_team_mapping_from_bridge
    from minecraft.services.luckperms_sync import remove_luckperms_for_registration

    registration = (
        MinecraftTeamRegistration.objects.filter(mc_username__iexact=mc_username)
        .select_related("group")
        .first()
    )
    if registration:
        remove_luckperms_for_registration(registration)
        remove_team_mapping_from_bridge(mc_username)
    reset_team_scoreboard_entry(mc_username)


def update_snapshot(
    player: str,
    velos_spendable: int,
    *,
    group_id: int | None = None,
    db_velos_total: int | None = None,
) -> None:
    safe_spendable = max(0, int(velos_spendable))
    defaults = {
        "velos_spendable": safe_spendable,
        "group_id": group_id,
        "source": "rcon",
        "captured_at": timezone.now(),
    }
    if db_velos_total is not None:
        defaults["velos_total"] = max(0, int(db_velos_total))

    snapshot, _created = MinecraftPlayerScoreboardSnapshot.objects.update_or_create(
        player_name=player,
        defaults=defaults,
    )
    logger.debug("[minecraft_snapshot] updated for team=%s", snapshot.player_name)


def refresh_team_scoreboard_snapshot() -> int:
    """Read spendable scores for all registered teams from Minecraft."""
    ensure_team_scoreboard_objective()
    objective = get_objective_spendable()
    updated = 0

    for registration in active_registrations():
        mc_username = registration.mc_username
        spendable = rcon_client.get_player_score(mc_username, objective)
        if spendable is None:
            logger.info("[minecraft_snapshot] skipping team=%s (no score found)", mc_username)
            continue

        group = registration.group
        db_updated = False
        if settings.MCC_MINECRAFT_SNAPSHOT_UPDATE_DB_SPENDABLE:
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

        update_snapshot(
            mc_username,
            max(0, int(spendable)),
            group_id=group.id,
            db_velos_total=int(group.velos_total or 0),
        )
        logger.info(
            "[minecraft_snapshot] snapshot updated team=%s spendable=%s db_updated=%s",
            mc_username,
            spendable,
            db_updated,
        )
        updated += 1

    logger.info("[minecraft_snapshot] refreshed: %s teams", updated)
    return updated
