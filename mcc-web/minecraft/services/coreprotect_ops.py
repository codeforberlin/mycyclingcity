# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    coreprotect_ops.py
# @note    CoreProtect rollback/restore via Paper RCON for Stadtsteuerung.

from __future__ import annotations

import re
from typing import Any, Literal

from django.conf import settings
from django.utils.translation import gettext as _

from config.logger_utils import get_logger
from minecraft.services import rcon_client

logger = get_logger("minecraft")

CoAction = Literal["rollback", "restore"]

TIME_PRESETS = (
    ("15m", "15 Minuten"),
    ("30m", "30 Minuten"),
    ("1h", "1 Stunde"),
    ("2h", "2 Stunden"),
    ("6h", "6 Stunden"),
)

# CoreProtect time tokens: digits, units w/d/h/m/s, commas, dots, hyphens
_TIME_RE = re.compile(r"^[0-9wdhms.,\-]+$", re.IGNORECASE)
_USER_RE = re.compile(r"^[A-Za-z0-9_]{1,16}$")


def paper_world_radius() -> str:
    world = (getattr(settings, "MCC_MINECRAFT_PAPER_WORLD", None) or "MyCyclingCity").strip()
    return f"#{world}" if world else "#global"


def allowed_radii() -> tuple[str, ...]:
    return ("#global", paper_world_radius())


def normalize_time_spec(value: str) -> str:
    raw = (value or "").strip().lower().replace(" ", "")
    if raw.startswith("t:"):
        raw = raw[2:]
    if not raw or not _TIME_RE.match(raw):
        raise ValueError(_("Ungültige Zeitangabe (z. B. 30m, 2h, 1d2h)."))
    return raw


def normalize_user(value: str) -> str:
    name = (value or "").strip()
    if not name or not _USER_RE.match(name):
        raise ValueError(_("Ungültiger Spielername (1–16 Zeichen, A–Z, 0–9, _)."))
    return name


def normalize_radius(value: str | None) -> str:
    radius = (value or "#global").strip()
    if not radius.startswith("#"):
        radius = f"#{radius}"
    allowed = set(allowed_radii())
    if radius not in allowed:
        raise ValueError(
            _("Radius nicht erlaubt. Erlaubt: %(opts)s")
            % {"opts": ", ".join(sorted(allowed))}
        )
    return radius


def build_co_command(
    action: CoAction,
    user: str,
    time_spec: str,
    *,
    radius: str = "#global",
    preview: bool = False,
    blocks_only: bool = True,
    silent: bool = False,
) -> str:
    """Build a single CoreProtect console command (always includes explicit radius)."""
    if action not in ("rollback", "restore"):
        raise ValueError(_("Ungültige Aktion."))
    u = normalize_user(user)
    t = normalize_time_spec(time_spec)
    r = normalize_radius(radius)
    parts = [f"co {action}", f"u:{u}", f"t:{t}", f"r:{r}"]
    if blocks_only:
        parts.append("a:block")
    if preview:
        parts.append("#preview")
    elif silent:
        parts.append("#silent")
    return " ".join(parts)


def build_co_lookup_count_command(
    user: str,
    time_spec: str,
    *,
    radius: str = "#global",
    blocks_only: bool = True,
) -> str:
    u = normalize_user(user)
    t = normalize_time_spec(time_spec)
    r = normalize_radius(radius)
    parts = ["co lookup", f"u:{u}", f"t:{t}", f"r:{r}"]
    if blocks_only:
        parts.append("a:block")
    parts.append("#count")
    return " ".join(parts)


def run_co_command(command: str, *, admin_user: str = "") -> tuple[bool, str]:
    logger.info(
        "[coreprotect] admin=%s command=%r",
        admin_user or "-",
        command,
    )
    try:
        output = rcon_client.run_command(command)
        return True, (output or "").strip()
    except Exception as exc:
        logger.error("[coreprotect] failed command=%r error=%s", command, exc)
        return False, str(exc)


def run_co_preview(
    action: CoAction,
    user: str,
    time_spec: str,
    *,
    radius: str = "#global",
    blocks_only: bool = True,
    admin_user: str = "",
) -> tuple[bool, str, str]:
    """Lookup count + preview rollback/restore. Returns (ok, output, command)."""
    lookup = build_co_lookup_count_command(
        user, time_spec, radius=radius, blocks_only=blocks_only
    )
    preview_cmd = build_co_command(
        action, user, time_spec, radius=radius, preview=True, blocks_only=blocks_only
    )
    ok1, out1 = run_co_command(lookup, admin_user=admin_user)
    ok2, out2 = run_co_command(preview_cmd, admin_user=admin_user)
    combined = "\n".join(x for x in (out1, out2) if x)
    return ok1 and ok2, combined, preview_cmd


def run_co_apply(
    action: CoAction,
    user: str,
    time_spec: str,
    *,
    radius: str = "#global",
    blocks_only: bool = True,
    admin_user: str = "",
) -> tuple[bool, str, str]:
    command = build_co_command(
        action, user, time_spec, radius=radius, preview=False, blocks_only=blocks_only
    )
    ok, output = run_co_command(command, admin_user=admin_user)
    return ok, output, command


def run_co_undo(*, admin_user: str = "") -> tuple[bool, str]:
    return run_co_command("co undo", admin_user=admin_user)


def list_known_ms_logins(limit: int = 80) -> list[str]:
    """MS usernames from play + builder accounts for GUI datalist."""
    from minecraft.models import MinecraftPlayAccount, MinecraftTeamRegistration

    names: list[str] = []
    seen: set[str] = set()
    for qs in (
        MinecraftPlayAccount.objects.exclude(ms_username="")
        .order_by("ms_username")
        .values_list("ms_username", flat=True)[:limit],
        MinecraftTeamRegistration.objects.filter(is_active=True)
        .exclude(ms_username="")
        .order_by("ms_username")
        .values_list("ms_username", flat=True)[:limit],
    ):
        for name in qs:
            key = (name or "").strip()
            if key and key.lower() not in seen:
                seen.add(key.lower())
                names.append(key)
    names.sort(key=str.lower)
    return names[:limit]
