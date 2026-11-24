# Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Apply a host-local mcc_migrator_map.json plus resolve_name() to Django rows.

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings
from django.db import transaction

from luanti.models import (
    LuantiPlanBlock,
    LuantiPlayerInventory,
    LuantiRegisteredItem,
    LuantiShopItem,
    LuantiShopPurchaseCredit,
    LuantiShopTransaction,
)
from luanti.services.mcl_map import resolve_name


@dataclass
class ConvertReport:
    file_path: str
    file_found: bool
    unknown: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    applied: bool = False

    @property
    def blocked(self) -> bool:
        return bool(self.unknown or self.conflicts) or not self.file_found


def mapping_file_path(world: str) -> Path:
    server = Path(getattr(settings, "MCC_LUANTI_SERVER_DIR", "/data/games/luanti"))
    return server / "worlds" / world / "mcc_migrator_map.json"


def load_mapping_file(path: Path) -> tuple[dict[str, str], list[str], bool]:
    if not path.is_file():
        return {}, [], False
    payload = json.loads(path.read_text(encoding="utf-8"))
    mapping: dict[str, str] = {}
    unknown = [str(name) for name in (payload.get("unknown") or []) if str(name).strip()]
    for row in payload.get("entries") or []:
        old = str(row.get("old") or "").strip()
        new = str(row.get("new") or "").strip()
        if not old:
            continue
        if not new or resolve_name(old) != new:
            unknown.append(old)
            continue
        mapping[old] = new
    return mapping, unknown, True


def target_for(name: str, mapping: dict[str, str]) -> str | None:
    raw = (name or "").strip()
    if not raw.startswith("mcl_"):
        return None
    if raw in mapping:
        return mapping[raw]
    return resolve_name(raw)


def build_report(world: str) -> ConvertReport:
    path = mapping_file_path(world)
    mapping, unknown, found = load_mapping_file(path)
    report = ConvertReport(file_path=str(path), file_found=found, unknown=list(unknown))
    report.counts = {
        "shop": _count_model(LuantiShopItem, mapping, report, "item_name"),
        "credit": _count_model(LuantiShopPurchaseCredit, mapping, report, "item_name"),
        "transaction": _count_model(LuantiShopTransaction, mapping, report, "item_name"),
        "registry": _count_model(LuantiRegisteredItem, mapping, report, "item_name"),
        "plan": _count_model(LuantiPlanBlock, mapping, report, "target_name"),
        "inventory": _count_inventory(mapping, report),
    }
    report.conflicts.extend(_shop_conflicts(mapping))
    report.conflicts.extend(_credit_conflicts(mapping))
    report.conflicts.extend(_registry_conflicts(mapping))
    report.conflicts = sorted(set(report.conflicts))
    report.unknown = sorted(set(report.unknown))
    return report


def apply_conversion(world: str) -> ConvertReport:
    report = build_report(world)
    if report.blocked:
        return report
    mapping, _, _ = load_mapping_file(Path(report.file_path))
    with transaction.atomic():
        _rename_model(LuantiShopItem, mapping, "item_name")
        _rename_model(LuantiShopPurchaseCredit, mapping, "item_name")
        _rename_model(LuantiShopTransaction, mapping, "item_name")
        _rename_registry(mapping)
        _rename_model(LuantiPlanBlock, mapping, "target_name")
        _rename_inventory(mapping)
    report.applied = True
    return report


def _note_unknown(name: str, mapping: dict[str, str], report: ConvertReport) -> str | None:
    raw = (name or "").strip()
    if not raw.startswith("mcl_"):
        return None
    new = target_for(raw, mapping)
    if not new:
        report.unknown.append(raw)
        return None
    return new


def _count_model(model, mapping, report, field_name: str) -> int:
    count = 0
    names = model.objects.values_list(field_name, flat=True).distinct()
    for name in names:
        if _note_unknown(name, mapping, report):
            count += model.objects.filter(**{field_name: name}).count()
    return count


def _count_inventory(mapping, report) -> int:
    count = 0
    for payload in LuantiPlayerInventory.objects.values_list("payload", flat=True):
        if not isinstance(payload, list):
            continue
        for stack in payload:
            if isinstance(stack, dict) and _note_unknown(str(stack.get("name") or ""), mapping, report):
                count += 1
    return count


def _shop_conflicts(mapping: dict[str, str]) -> list[str]:
    found = []
    rows = list(LuantiShopItem.objects.values_list("id", "category_id", "item_name"))
    by_cat: dict[int, dict[str, int]] = {}
    for pk, category_id, item_name in rows:
        by_cat.setdefault(category_id, {})[item_name] = pk
    for pk, category_id, item_name in rows:
        new = target_for(item_name, mapping)
        if not new or new == item_name:
            continue
        other = by_cat.get(category_id, {}).get(new)
        if other and other != pk:
            found.append(f"shop category={category_id} {item_name} -> {new}")
    return found


def _credit_conflicts(mapping: dict[str, str]) -> list[str]:
    found = []
    rows = list(LuantiShopPurchaseCredit.objects.values_list("id", "group_id", "item_name"))
    by_group: dict[int, dict[str, int]] = {}
    for pk, group_id, item_name in rows:
        by_group.setdefault(group_id, {})[item_name] = pk
    for pk, group_id, item_name in rows:
        new = target_for(item_name, mapping)
        if not new or new == item_name:
            continue
        other = by_group.get(group_id, {}).get(new)
        if other and other != pk:
            found.append(f"credit group={group_id} {item_name} -> {new}")
    return found


def _registry_conflicts(mapping: dict[str, str]) -> list[str]:
    found = []
    existing = set(LuantiRegisteredItem.objects.values_list("item_name", flat=True))
    for name in existing:
        new = target_for(name, mapping)
        if new and new != name and new in existing:
            found.append(f"registry {name} -> {new}")
    return found


def _rename_model(model, mapping: dict[str, str], field_name: str) -> None:
    for obj in list(model.objects.all()):
        current = getattr(obj, field_name)
        new = target_for(current, mapping)
        if new and new != current:
            setattr(obj, field_name, new)
            obj.save(update_fields=[field_name])


def _rename_registry(mapping: dict[str, str]) -> None:
    for name in list(LuantiRegisteredItem.objects.values_list("item_name", flat=True)):
        new = target_for(name, mapping)
        if not new or new == name:
            continue
        old = LuantiRegisteredItem.objects.get(pk=name)
        LuantiRegisteredItem.objects.create(
            item_name=new,
            description=old.description,
            kind=old.kind,
            drawtype=old.drawtype,
            inventory_image=old.inventory_image,
            wield_image=old.wield_image,
            not_in_creative_inventory=old.not_in_creative_inventory,
        )
        old.delete()


def _rename_inventory(mapping: dict[str, str]) -> None:
    for inv in LuantiPlayerInventory.objects.all():
        payload = inv.payload
        if not isinstance(payload, list):
            continue
        changed = False
        for stack in payload:
            if not isinstance(stack, dict):
                continue
            new = target_for(str(stack.get("name") or ""), mapping)
            if new and new != stack.get("name"):
                stack["name"] = new
                changed = True
        if changed:
            inv.payload = payload
            inv.save(update_fields=["payload"])
