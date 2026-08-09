# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Grant shop sell credits from a live Minecraft inventory (RCON + playerdata).

from __future__ import annotations

import gzip
import json
import re
import struct
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.db.models import F

from config.logger_utils import get_logger
from minecraft.models import (
    MinecraftBuilderAccount,
    MinecraftPlayAccount,
    MinecraftShopItem,
    MinecraftShopPurchaseCredit,
)
from minecraft.services.playerdata_uuid import (
    detect_playerdata_layout,
    parse_ms_uuid,
    playerdata_relative_files,
)
from minecraft.services.rcon_client import run_command
from minecraft.services.team_registration import get_active_registration_by_mc_username


logger = get_logger("minecraft")

_ID_COUNT_RE = re.compile(
    r'id:\s*"minecraft:([a-z0-9_/]+)"\s*,\s*count:\s*(\d+)',
    re.IGNORECASE,
)
_ID_COUNT_LEGACY_RE = re.compile(
    r'id:\s*"minecraft:([a-z0-9_/]+)"[^}]*?Count:\s*(\d+)b?',
    re.IGNORECASE | re.DOTALL,
)
_LIST_PLAYER_RE = re.compile(r"\[([^\]]+)\]\s+(\S+)")
_LIST_PLAYER_PLAIN_RE = re.compile(r":\s*(.+)$")


@dataclass(frozen=True)
class InventoryCreditResult:
    player: str
    team_mc_username: str
    credited_stacks: int
    credited_items: int
    skipped_non_shop: int
    materials: dict[str, int]
    error: str = ""


def shop_catalog_materials() -> set[str]:
    return {
        str(m).strip().upper().replace("-", "_")
        for m in MinecraftShopItem.objects.filter(enabled=True, category__enabled=True).values_list(
            "material", flat=True
        )
        if m
    }


def parse_inventory_counts_from_snbt(text: str) -> Counter[str]:
    """Parse material counts from RCON ``data get entity … Inventory`` SNBT."""
    counts: Counter[str] = Counter()
    if not text:
        return counts
    for match in _ID_COUNT_RE.finditer(text):
        counts[match.group(1).upper().replace("-", "_")] += int(match.group(2))
    if not counts:
        for match in _ID_COUNT_LEGACY_RE.finditer(text):
            counts[match.group(1).upper().replace("-", "_")] += int(match.group(2))
    return counts


def parse_online_players_from_list(list_response: str) -> list[tuple[str, str | None]]:
    """
    Parse ``list`` RCON output.

    Returns list of (player_name, team_hint_or_None).
    LuckPerms/prefix style: ``[Kette] mccpc02``.
    """
    text = list_response or ""
    players: list[tuple[str, str | None]] = []
    for match in _LIST_PLAYER_RE.finditer(text):
        players.append((match.group(2).strip(), match.group(1).strip()))
    if players:
        return players
    # Fallback: "There are N … online: name1, name2"
    tail = _LIST_PLAYER_PLAIN_RE.search(text)
    if not tail:
        return []
    raw = tail.group(1).strip()
    if not raw or raw.lower().startswith("no players"):
        return []
    for part in raw.split(","):
        name = part.strip()
        if name:
            players.append((name, None))
    return players


def resolve_team_mc_username(player_name: str, team_hint: str | None = None) -> str | None:
    """Map an online MS/login name to the leaf team scoreboard username."""
    name = (player_name or "").strip()
    if not name:
        return None

    builder = (
        MinecraftBuilderAccount.objects.filter(ms_username__iexact=name, is_active=True)
        .select_related("group")
        .first()
    )
    if builder and builder.mc_username:
        return builder.mc_username

    # Active registration that uses this name as scoreboard name
    reg = get_active_registration_by_mc_username(name)
    if reg:
        return reg.mc_username

    if team_hint:
        hint_reg = get_active_registration_by_mc_username(team_hint)
        if hint_reg:
            return hint_reg.mc_username

    return None


def _world_root() -> Path:
    return Path(getattr(settings, "MCC_MINECRAFT_WORLD_DIR", "/data/games/mcc/mc-srv/MyCyclingCity"))


def _usercache_uuid(player_name: str) -> str | None:
    cache_path = _world_root().parent / "usercache.json"
    if not cache_path.is_file():
        # Paper often keeps usercache next to server root
        cache_path = Path("/data/games/mcc/mc-srv/usercache.json")
    if not cache_path.is_file():
        return None
    try:
        entries = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    needle = player_name.lower()
    for entry in entries:
        if str(entry.get("name", "")).lower() == needle:
            return str(entry.get("uuid") or "").strip() or None
    return None


def _resolve_player_uuid(player_name: str) -> str | None:
    play = MinecraftPlayAccount.objects.filter(ms_username__iexact=player_name).first()
    if play and play.ms_uuid:
        return play.ms_uuid.strip()
    builder = MinecraftBuilderAccount.objects.filter(ms_username__iexact=player_name).first()
    if builder and builder.ms_uuid:
        return builder.ms_uuid.strip()
    return _usercache_uuid(player_name)


def _playerdata_path(player_uuid: str) -> Path | None:
    try:
        uid = parse_ms_uuid(player_uuid)
    except ValueError:
        return None
    world = _world_root()
    layout = detect_playerdata_layout(world)
    rel = playerdata_relative_files(uid, layout=layout)["playerdata"]
    path = world / rel
    return path if path.is_file() else None


def _read_nbt_inventory_counts(path: Path) -> Counter[str]:
    """Read Inventory (+ optional EnderItems skipped) from gzip playerdata."""
    raw = gzip.decompress(path.read_bytes())
    root = _nbt_parse_named(raw, 0)[0]
    inventory = root.get("Inventory") or []
    counts: Counter[str] = Counter()
    for stack in inventory:
        if not isinstance(stack, dict):
            continue
        item_id = stack.get("id")
        if not item_id:
            continue
        material = str(item_id).removeprefix("minecraft:").upper().replace("-", "_")
        count = stack.get("count", stack.get("Count", 0))
        try:
            qty = int(count)
        except (TypeError, ValueError):
            continue
        if qty > 0 and material:
            counts[material] += qty
    return counts


# --- Minimal NBT reader (named root compound) ---------------------------------

def _nbt_parse_named(data: bytes, offset: int):
    tag_type = data[offset]
    offset += 1
    if tag_type == 0:
        return None, offset
    name_len = struct.unpack(">H", data[offset : offset + 2])[0]
    offset += 2 + name_len
    value, offset = _nbt_parse_payload(data, offset, tag_type)
    return value, offset


def _nbt_parse_payload(data: bytes, offset: int, tag_type: int):
    if tag_type == 1:  # byte
        return data[offset], offset + 1
    if tag_type == 2:  # short
        return struct.unpack(">h", data[offset : offset + 2])[0], offset + 2
    if tag_type == 3:  # int
        return struct.unpack(">i", data[offset : offset + 4])[0], offset + 4
    if tag_type == 4:  # long
        return struct.unpack(">q", data[offset : offset + 8])[0], offset + 8
    if tag_type == 5:  # float
        return struct.unpack(">f", data[offset : offset + 4])[0], offset + 4
    if tag_type == 6:  # double
        return struct.unpack(">d", data[offset : offset + 8])[0], offset + 8
    if tag_type == 7:  # byte array
        length = struct.unpack(">i", data[offset : offset + 4])[0]
        offset += 4
        return data[offset : offset + length], offset + length
    if tag_type == 8:  # string
        length = struct.unpack(">H", data[offset : offset + 2])[0]
        offset += 2
        return data[offset : offset + length].decode("utf-8", errors="replace"), offset + length
    if tag_type == 9:  # list
        elem_type = data[offset]
        length = struct.unpack(">i", data[offset + 1 : offset + 5])[0]
        offset += 5
        items = []
        for _ in range(max(0, length)):
            item, offset = _nbt_parse_payload(data, offset, elem_type)
            items.append(item)
        return items, offset
    if tag_type == 10:  # compound
        compound = {}
        while True:
            child_type = data[offset]
            offset += 1
            if child_type == 0:
                break
            name_len = struct.unpack(">H", data[offset : offset + 2])[0]
            offset += 2
            name = data[offset : offset + name_len].decode("utf-8", errors="replace")
            offset += name_len
            value, offset = _nbt_parse_payload(data, offset, child_type)
            compound[name] = value
        return compound, offset
    if tag_type == 11:  # int array
        length = struct.unpack(">i", data[offset : offset + 4])[0]
        offset += 4
        values = list(struct.unpack(f">{length}i", data[offset : offset + 4 * length]))
        return values, offset + 4 * length
    if tag_type == 12:  # long array
        length = struct.unpack(">i", data[offset : offset + 4])[0]
        offset += 4
        values = list(struct.unpack(f">{length}q", data[offset : offset + 8 * length]))
        return values, offset + 8 * length
    raise ValueError(f"Unsupported NBT tag type {tag_type}")


def fetch_inventory_counts(player_name: str) -> Counter[str]:
    """
    Load inventory counts for a player.

    Prefer flushed playerdata on disk (complete). RCON ``data get`` is only a
    fallback because large inventories are truncated mid-SNBT.
    """
    name = (player_name or "").strip()
    if not name:
        return Counter()

    try:
        run_command("save-all flush")
    except Exception as exc:
        logger.warning("[shop_inventory_credit] save-all failed: %s", exc)

    uuid_str = _resolve_player_uuid(name)
    if uuid_str:
        path = _playerdata_path(uuid_str)
        if path:
            try:
                counts = _read_nbt_inventory_counts(path)
                if counts:
                    logger.info(
                        "[shop_inventory_credit] playerdata %s materials=%s items=%s",
                        name,
                        len(counts),
                        sum(counts.values()),
                    )
                    return counts
            except Exception as exc:
                logger.warning(
                    "[shop_inventory_credit] NBT parse failed for %s (%s): %s",
                    name,
                    path,
                    exc,
                )

    try:
        snbt = run_command(f"data get entity {name} Inventory") or ""
    except Exception as exc:
        logger.warning("[shop_inventory_credit] RCON inventory failed for %s: %s", name, exc)
        return Counter()

    if "..." in snbt:
        logger.warning(
            "[shop_inventory_credit] RCON inventory for %s looks truncated; results may be incomplete",
            name,
        )
    return parse_inventory_counts_from_snbt(snbt)

@transaction.atomic
def add_material_credits_for_team(mc_username: str, material_counts: dict[str, int]) -> dict[str, int]:
    """
    Add (not replace) sell credits for a team. Only positive counts are applied.
    Returns the applied material→qty map.
    """
    registration = get_active_registration_by_mc_username(mc_username)
    if not registration:
        raise ValueError(f"group_not_found:{mc_username}")

    applied: dict[str, int] = {}
    for material, qty in material_counts.items():
        normalized = str(material).strip().upper().replace("-", "_")
        try:
            amount = int(qty)
        except (TypeError, ValueError):
            continue
        if not normalized or amount <= 0:
            continue
        credit, created = MinecraftShopPurchaseCredit.objects.select_for_update().get_or_create(
            group_id=registration.group_id,
            material=normalized,
            defaults={"quantity": 0},
        )
        if created:
            credit.quantity = amount
            credit.save(update_fields=["quantity"])
        else:
            MinecraftShopPurchaseCredit.objects.filter(pk=credit.pk).update(
                quantity=F("quantity") + amount
            )
        applied[normalized] = amount
    return applied


def grant_player_inventory_to_ledger(
    player_name: str,
    *,
    team_hint: str | None = None,
) -> InventoryCreditResult:
    """Credit shop-catalog materials from one online player's inventory to their team ledger."""
    player = (player_name or "").strip()
    team = resolve_team_mc_username(player, team_hint)
    if not team:
        return InventoryCreditResult(
            player=player,
            team_mc_username="",
            credited_stacks=0,
            credited_items=0,
            skipped_non_shop=0,
            materials={},
            error="team_not_found",
        )

    catalog = shop_catalog_materials()
    raw_counts = fetch_inventory_counts(player)
    if not raw_counts:
        return InventoryCreditResult(
            player=player,
            team_mc_username=team,
            credited_stacks=0,
            credited_items=0,
            skipped_non_shop=0,
            materials={},
            error="inventory_empty_or_unreadable",
        )

    shop_counts: dict[str, int] = {}
    skipped = 0
    for material, qty in raw_counts.items():
        if material in catalog:
            shop_counts[material] = int(qty)
        else:
            skipped += int(qty)

    if not shop_counts:
        return InventoryCreditResult(
            player=player,
            team_mc_username=team,
            credited_stacks=0,
            credited_items=0,
            skipped_non_shop=skipped,
            materials={},
            error="no_shop_materials",
        )

    applied = add_material_credits_for_team(team, shop_counts)
    return InventoryCreditResult(
        player=player,
        team_mc_username=team,
        credited_stacks=len(applied),
        credited_items=sum(applied.values()),
        skipped_non_shop=skipped,
        materials=applied,
    )


def grant_all_online_inventories_to_ledger() -> list[InventoryCreditResult]:
    """Grant credits for every currently online player (shop materials only)."""
    list_response = run_command("list")
    players = parse_online_players_from_list(list_response)
    results: list[InventoryCreditResult] = []
    for player_name, team_hint in players:
        results.append(grant_player_inventory_to_ledger(player_name, team_hint=team_hint))
    return results
