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
