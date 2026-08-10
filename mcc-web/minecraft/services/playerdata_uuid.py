# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    playerdata_uuid.py
# @note    Minecraft online vs offline player UUIDs for playerdata paths.

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path


def offline_player_uuid(player_name: str) -> uuid.UUID:
    """
    Vanilla offline-mode UUID for a player name.

    Equivalent to Java ``UUID.nameUUIDFromBytes(("OfflinePlayer:" + name).getBytes(UTF_8))``.
    """
    name = (player_name or "").strip()
    if not name:
        raise ValueError("player name is empty")
    digest = hashlib.md5(f"OfflinePlayer:{name}".encode("utf-8")).digest()
    data = bytearray(digest)
    data[6] = (data[6] & 0x0F) | 0x30  # version 3
    data[8] = (data[8] & 0x3F) | 0x80  # RFC 4122 variant
    return uuid.UUID(bytes=bytes(data))


def parse_ms_uuid(value: str) -> uuid.UUID:
    """Parse a Mojang/Microsoft UUID string (with or without hyphens)."""
    raw = (value or "").strip()
    if not raw:
        raise ValueError("ms_uuid is empty")
    if len(raw) == 32 and "-" not in raw:
        raw = f"{raw[0:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:32]}"
    return uuid.UUID(raw)


def uuid_dashed(value: uuid.UUID) -> str:
    return str(value)


def playerdata_relative_files(player_uuid: uuid.UUID, *, layout: str = "auto") -> dict[str, str]:
    """
    Relative paths under a world root for vanilla player persistence.

    layout:
      - ``players``: Paper/modern ``players/data|stats|advancements``
      - ``classic``: vanilla ``playerdata|stats|advancements``
      - ``auto``: resolved by caller via ``detect_playerdata_layout``
    """
    key = uuid_dashed(player_uuid)
    if layout == "classic":
        return {
            "playerdata": f"playerdata/{key}.dat",
            "stats": f"stats/{key}.json",
            "advancements": f"advancements/{key}.json",
        }
    # Default / players layout (MCC Paper world)
    return {
        "playerdata": f"players/data/{key}.dat",
        "stats": f"players/stats/{key}.json",
        "advancements": f"players/advancements/{key}.json",
    }


def detect_playerdata_layout(world_root: Path) -> str:
    """Prefer ``players/data`` when present (Paper), else classic ``playerdata``."""
    root = Path(world_root)
    if (root / "players" / "data").is_dir():
        return "players"
    if (root / "playerdata").is_dir():
        return "classic"
    # Default to players for new MCC worlds
    return "players"


def usercache_candidate_paths() -> list[Path]:
    """Likely usercache.json locations (Paper / Velocity / Limbo)."""
    from django.conf import settings

    paths: list[Path] = []
    paper = Path(getattr(settings, "MCC_MINECRAFT_PAPER_DIR", "") or "")
    if paper.parts:
        paths.append(paper / "usercache.json")
    world = Path(
        getattr(settings, "MCC_MINECRAFT_WORLD_DIR", "")
        or "/data/games/mcc/mc-srv/MyCyclingCity"
    )
    paths.append(world.parent / "usercache.json")
    for key in ("MCC_MINECRAFT_VELOCITY_DIR", "MCC_MINECRAFT_LIMBO_DIR"):
        root = Path(getattr(settings, key, "") or "")
        if root.parts:
            paths.append(root / "usercache.json")
    # De-dupe while preserving order
    seen: set[str] = set()
    out: list[Path] = []
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        out.append(path)
    return out


def lookup_ms_uuid_from_usercache(player_name: str) -> str | None:
    """
    Resolve Microsoft/online UUID for a login via usercache.json.

    Returns a dashed UUID string, or None if not found.
    """
    import json

    needle = (player_name or "").strip().lower()
    if not needle:
        return None
    for cache_path in usercache_candidate_paths():
        if not cache_path.is_file():
            continue
        try:
            entries = json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if str(entry.get("name", "")).lower() != needle:
                continue
            raw = str(entry.get("uuid") or "").strip()
            if not raw:
                continue
            try:
                return uuid_dashed(parse_ms_uuid(raw))
            except ValueError:
                continue
    return None


def lookup_ms_uuid_via_mojang(player_name: str, *, timeout: float = 3.0) -> str | None:
    """Best-effort Mojang profile lookup for Java online UUID."""
    import json
    import urllib.error
    import urllib.parse
    import urllib.request

    name = (player_name or "").strip()
    if not name:
        return None
    url = f"https://api.mojang.com/users/profiles/minecraft/{urllib.parse.quote(name)}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 — public Mojang API
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, OSError):
        return None
    raw = str((payload or {}).get("id") or "").strip()
    if not raw:
        return None
    try:
        return uuid_dashed(parse_ms_uuid(raw))
    except ValueError:
        return None


def resolve_ms_uuid_for_login(player_name: str, *, allow_mojang: bool = True) -> str | None:
    """Usercache first, optional Mojang fallback — for Limbo adopt / account create."""
    found = lookup_ms_uuid_from_usercache(player_name)
    if found:
        return found
    if allow_mojang:
        return lookup_ms_uuid_via_mojang(player_name)
    return None


def resolve_source_player_file(
    world_root: Path,
    relative: str,
    *,
    allow_data_backup: bool = True,
) -> Path:
    """
    Resolve a source file path; for ``players/data/*.dat`` also try ``players/data_backup``.
    """
    primary = resolve_world_file(world_root, relative)
    if primary.is_file():
        return primary
    if allow_data_backup and relative.startswith("players/data/"):
        backup_rel = "players/data_backup/" + relative.split("/", 2)[-1]
        backup = resolve_world_file(world_root, backup_rel)
        if backup.is_file():
            return backup
    return primary


def resolve_world_file(world_root: Path, relative: str) -> Path:
    return Path(world_root) / relative
