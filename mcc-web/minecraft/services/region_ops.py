# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    region_ops.py
# @note    WorldGuard/WorldEdit protected regions via Paper RCON for Stadtsteuerung.

from __future__ import annotations

import math
import re
from typing import Any

from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext as _

from config.logger_utils import get_logger
from minecraft.services import rcon_client

logger = get_logger("minecraft")

_REGION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-]{0,62}$")
_PLAYER_RE = re.compile(r"^[A-Za-z0-9_]{1,16}$")
_POS_RE = re.compile(
    r"\[\s*([-+]?\d+(?:\.\d+)?)[dDfF]?\s*,\s*"
    r"([-+]?\d+(?:\.\d+)?)[dDfF]?\s*,\s*"
    r"([-+]?\d+(?:\.\d+)?)[dDfF]?\s*\]"
)


def paper_world() -> str:
    return (getattr(settings, "MCC_MINECRAFT_PAPER_WORLD", None) or "MyCyclingCity").strip()


def default_region_min_y() -> int:
    """Inclusive world floor Y used as default Min Y for new protected regions."""
    return int(getattr(settings, "MCC_MINECRAFT_WORLD_MIN_Y", -64))


def default_region_max_y() -> int:
    """Inclusive world ceiling Y used as default Max Y for new protected regions."""
    return int(getattr(settings, "MCC_MINECRAFT_WORLD_MAX_Y", 320))


def worldedit_world_arg(world: str | None = None) -> str:
    """
    WorldEdit ``//world`` on this Paper install matches the lowercase world token
    (e.g. ``mycyclingcity``), while WorldGuard ``-w`` needs the Bukkit name
    (``MyCyclingCity``).
    """
    return (world or paper_world()).strip().lower()


def normalize_region_id(value: str) -> str:
    region_id = (value or "").strip()
    if not region_id or not _REGION_ID_RE.match(region_id):
        raise ValueError(
            _(
                "Ungültige Region-ID (1–63 Zeichen, beginnt mit Buchstabe/Ziffer; "
                "erlaubt: A–Z, 0–9, _, -)."
            )
        )
    return region_id


def normalize_player(value: str) -> str:
    name = (value or "").strip()
    if not name or not _PLAYER_RE.match(name):
        raise ValueError(_("Ungültiger Spielername (1–16 Zeichen, A–Z, 0–9, _)."))
    return name


def parse_entity_pos(response: str) -> tuple[int, int, int]:
    """Parse ``data get entity … Pos`` into floored block coordinates."""
    match = _POS_RE.search(response or "")
    if not match:
        raise ValueError(
            _("Spielerposition nicht lesbar (Spieler offline oder ungültige Antwort).")
        )
    x = int(math.floor(float(match.group(1))))
    y = int(math.floor(float(match.group(2))))
    z = int(math.floor(float(match.group(3))))
    return x, y, z


def fetch_player_block_pos(player: str) -> tuple[int, int, int]:
    name = normalize_player(player)
    response = rcon_client.run_command(f"data get entity {name} Pos")
    return parse_entity_pos(response)


def desired_member_logins(region) -> list[str]:
    """MS logins from linked Bau-Accounts (active, with ms_username)."""
    names: set[str] = set()
    for reg in region.builders.filter(is_active=True):
        login = (reg.ms_username or "").strip()
        if login and _PLAYER_RE.match(login):
            names.add(login)
    return sorted(names, key=str.lower)


def build_selection_commands(
    world: str,
    min_x: int,
    min_y: int,
    min_z: int,
    max_x: int,
    max_y: int,
    max_z: int,
) -> list[str]:
    """WorldEdit cuboid selection for console (absolute coordinates).

    Clear any previous console selection first — without ``//desel``, WorldEdit
    may answer ``Position bereits gesetzt`` and keep the old bounds, so
    ``rg redefine`` would silently keep the previous cuboid.
    """
    we_world = worldedit_world_arg(world)
    return [
        "//desel",
        "//sel cuboid",
        f"//world {we_world}",
        f"//pos1 {min_x},{min_y},{min_z}",
        f"//pos2 {max_x},{max_y},{max_z}",
    ]


def _region_already_exists_response(response: str | None) -> bool:
    text = (response or "").lower()
    return (
        "already exists" in text
        or "existiert bereits" in text
        or "already defined" in text
    )


def build_define_commands(region_id: str, world: str, *, redefine: bool = False) -> list[str]:
    action = "redefine" if redefine else "define"
    return [f"rg {action} -w {world} {region_id}"]


def build_flag_commands(region_id: str, world: str, *, protect_build: bool = True) -> list[str]:
    """
    WorldGuard protects non-members by default — do **not** set ``build deny``
    (that overrides default protection and can block members too).

    ``protect_build=True``: clear passthrough so normal region protection applies.
    ``protect_build=False``: ``passthrough allow`` (region does not block building).
    """
    if protect_build:
        return [
            f"rg flag -w {world} {region_id} passthrough",
            f"rg flag -w {world} {region_id} build",
        ]
    return [f"rg flag -w {world} {region_id} passthrough allow"]


def build_member_sync_commands(
    region_id: str,
    world: str,
    *,
    desired: list[str],
    previously_synced: list[str] | None = None,
) -> list[str]:
    """Add desired members; remove previously synced names that are no longer desired."""
    desired_set = {n for n in desired if n}
    previous = {n for n in (previously_synced or []) if n}
    commands: list[str] = []
    for name in sorted(previous - desired_set, key=str.lower):
        commands.append(f"rg removemember -w {world} {region_id} -n {name}")
    # Always (re-)add desired members; WorldGuard addmember is idempotent.
    for name in sorted(desired_set, key=str.lower):
        commands.append(f"rg addmember -w {world} {region_id} -n {name}")
    return commands


def build_remove_commands(region_id: str, world: str) -> list[str]:
    return [f"rg remove -w {world} {region_id}"]


def apply_region_geometry(region, *, redefine: bool | None = None) -> tuple[bool, str]:
    """
    Set WorldEdit selection from region bounds and define/redefine the WG region.

    If ``redefine`` is None, try define first, then redefine on failure.
    """
    region_id = normalize_region_id(region.region_id)
    world = (region.world or paper_world()).strip() or paper_world()
    min_x, min_y, min_z, max_x, max_y, max_z = region.normalized_bounds()

    selection = build_selection_commands(world, min_x, min_y, min_z, max_x, max_y, max_z)
    logs: list[str] = []

    ok, log = rcon_client.run_commands(selection, stop_on_error=True)
    logs.append(log)
    if not ok:
        return False, "\n".join(logs)

    if redefine is True:
        ok, log = rcon_client.run_commands(
            build_define_commands(region_id, world, redefine=True),
            stop_on_error=True,
        )
        logs.append(log)
        return ok, "\n".join(logs)

    if redefine is False:
        ok, log = rcon_client.run_commands(
            build_define_commands(region_id, world, redefine=False),
            stop_on_error=True,
        )
        logs.append(log)
        return ok, "\n".join(logs)

    ok, log = rcon_client.run_commands(
        build_define_commands(region_id, world, redefine=False),
        stop_on_error=True,
    )
    logs.append(log)
    # RCON may treat "already exists" as a non-error response; still redefine.
    if ok and not _region_already_exists_response(log):
        return True, "\n".join(logs)
    if not ok and not _region_already_exists_response(log):
        return False, "\n".join(logs)

    # Region may already exist — redefine with the fresh selection above
    ok2, log2 = rcon_client.run_commands(
        build_define_commands(region_id, world, redefine=True),
        stop_on_error=True,
    )
    logs.append(log2)
    return ok2, "\n".join(logs)


def apply_region_flags(region) -> tuple[bool, str]:
    region_id = normalize_region_id(region.region_id)
    world = (region.world or paper_world()).strip() or paper_world()
    return rcon_client.run_commands(
        build_flag_commands(region_id, world, protect_build=bool(region.protect_build)),
        stop_on_error=True,
    )


def sync_region_members(region) -> tuple[bool, str]:
    """Sync WorldGuard members from linked Bau-Accounts; update synced_members on success."""
    region_id = normalize_region_id(region.region_id)
    world = (region.world or paper_world()).strip() or paper_world()
    desired = desired_member_logins(region)
    previous = list(region.synced_members or [])
    commands = build_member_sync_commands(
        region_id, world, desired=desired, previously_synced=previous
    )
    if not commands:
        region.synced_members = desired
        region.last_synced_at = timezone.now()
        region.last_sync_error = ""
        region.save(
            update_fields=["synced_members", "last_synced_at", "last_sync_error", "updated_at"]
        )
        return True, _("Keine Member-Änderungen.")

    ok, log = rcon_client.run_commands(commands, stop_on_error=False)
    if ok:
        region.synced_members = desired
        region.last_synced_at = timezone.now()
        region.last_sync_error = ""
        region.save(
            update_fields=["synced_members", "last_synced_at", "last_sync_error", "updated_at"]
        )
        logger.info(
            "[region_ops] members synced region=%s members=%s",
            region_id,
            desired,
        )
    else:
        region.last_sync_error = log[:5000]
        region.save(update_fields=["last_sync_error", "updated_at"])
        logger.warning("[region_ops] member sync failed region=%s log=%s", region_id, log)
    return ok, log


def apply_region_full(region, *, admin_user: str = "") -> tuple[bool, str]:
    """Define/redefine geometry, flags, and members."""
    parts: list[str] = []
    ok, log = apply_region_geometry(region)
    parts.append(log)
    if not ok:
        region.last_sync_error = log[:5000]
        region.save(update_fields=["last_sync_error", "updated_at"])
        return False, "\n".join(parts)

    ok_f, log_f = apply_region_flags(region)
    parts.append(log_f)
    if not ok_f:
        region.last_sync_error = log_f[:5000]
        region.save(update_fields=["last_sync_error", "updated_at"])
        return False, "\n".join(parts)

    ok_m, log_m = sync_region_members(region)
    parts.append(log_m)
    logger.info(
        "[region_ops] apply_full admin=%s region=%s ok=%s",
        admin_user or "?",
        region.region_id,
        ok_m,
    )
    return ok_m, "\n".join(parts)


def remove_region_from_server(region) -> tuple[bool, str]:
    region_id = normalize_region_id(region.region_id)
    world = (region.world or paper_world()).strip() or paper_world()
    return rcon_client.run_commands(
        build_remove_commands(region_id, world),
        stop_on_error=True,
    )


def parse_int_coord(value: Any, field: str) -> int:
    raw = str(value if value is not None else "").strip()
    if raw == "":
        raise ValueError(_("Feld %(field)s fehlt.") % {"field": field})
    try:
        return int(float(raw))
    except (TypeError, ValueError) as exc:
        raise ValueError(
            _("Ungültige Koordinate %(field)s: %(val)s") % {"field": field, "val": raw}
        ) from exc
