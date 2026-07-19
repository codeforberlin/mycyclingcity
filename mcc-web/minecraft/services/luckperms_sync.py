# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import re

from django.conf import settings

from api.models import Group
from config.logger_utils import get_logger
from minecraft.models import MinecraftTeamRegistration
from minecraft.services import rcon_client


logger = get_logger("minecraft")

_LP_GROUP_PREFIX = "team_"


def luckperms_group_name(mc_username: str) -> str:
    """LuckPerms group name for MCC-Bridge team_groups (e.g. Kette -> team_kette)."""
    prefix = getattr(settings, "MCC_MINECRAFT_LP_GROUP_PREFIX", _LP_GROUP_PREFIX) or _LP_GROUP_PREFIX
    slug = re.sub(r"[^a-z0-9]+", "_", (mc_username or "").lower()).strip("_")
    if not slug:
        raise ValueError("mc_username is empty")
    return f"{prefix}{slug}"


def collect_minecraft_player_names(
    group: Group,
    *,
    team_mc_username: str | None = None,
) -> list[str]:
    """Minecraft account names that should receive the team LuckPerms group."""
    names: set[str] = set()
    team_name = (team_mc_username or group.mc_username or "").strip()
    if team_name:
        names.add(team_name)
    for cyclist in group.members.exclude(mc_username__isnull=True).exclude(mc_username=""):
        player_name = (cyclist.mc_username or "").strip()
        if player_name:
            names.add(player_name)
    return sorted(names, key=str.lower)


def _lp_sync_enabled() -> bool:
    return bool(getattr(settings, "MCC_MINECRAFT_LP_SYNC_ENABLED", True))


def apply_luckperms_for_registration(registration: MinecraftTeamRegistration) -> tuple[bool, str]:
    """
    Create LuckPerms team group and assign all group members on the MC server via RCON.
    """
    if not _lp_sync_enabled():
        return True, "LuckPerms sync disabled"

    mc_username = registration.mc_username
    lp_group = luckperms_group_name(mc_username)
    players = collect_minecraft_player_names(
        registration.group,
        team_mc_username=mc_username,
    )
    if not players:
        return False, "No Minecraft player names found for this group"

    commands = [
        f"lp creategroup {lp_group}",
        f"lp group {lp_group} permission set group.{lp_group} true",
    ]
    for player in players:
        commands.append(f"lp user {player} parent add {lp_group}")

    success, log = rcon_client.run_commands(commands, stop_on_error=False)
    logger.info(
        "[minecraft_lp] applied registration group=%s mc=%s lp_group=%s players=%s success=%s",
        registration.group.name,
        mc_username,
        lp_group,
        players,
        success,
    )
    if not success:
        return False, log
    return True, log


def remove_luckperms_for_registration(registration: MinecraftTeamRegistration) -> tuple[bool, str]:
    """Remove LuckPerms parent group from team members (group itself is kept)."""
    if not _lp_sync_enabled():
        return True, "LuckPerms sync disabled"

    lp_group = luckperms_group_name(registration.mc_username)
    players = collect_minecraft_player_names(
        registration.group,
        team_mc_username=registration.mc_username,
    )
    if not players:
        return True, "No Minecraft player names to update"

    commands = [f"lp user {player} parent remove {lp_group}" for player in players]
    success, log = rcon_client.run_commands(commands, stop_on_error=False)
    logger.info(
        "[minecraft_lp] removed registration group=%s mc=%s lp_group=%s players=%s",
        registration.group.name,
        registration.mc_username,
        lp_group,
        players,
    )
    return success, log
