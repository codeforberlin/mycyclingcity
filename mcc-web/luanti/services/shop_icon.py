# Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Heuristics for Luanti shop formspec item_image_button visibility in Admin.

from __future__ import annotations

from luanti.models import LuantiRegisteredItem

ICON_OK = "ok"
ICON_UNCERTAIN = "uncertain"
ICON_MISSING = "missing"

ICON_LABELS_DE: dict[str, str] = {
    ICON_OK: "Shop-Icon: wahrscheinlich OK",
    ICON_UNCERTAIN: "Shop-Icon: unsicher (Mesh/ohne Inventarbild)",
    ICON_MISSING: "Shop-Icon: fehlt (nicht in Registry)",
}

# drawtypes that often render blank in item_image_button without inventory_image
_UNCERTAIN_DRAWTYPES = frozenset(
    {
        "mesh",
        "plantlike",
        "plantlike_rooted",
        "airlike",
    }
)


def _known_good_shop_icon_without_inventory_image(item_name: str) -> bool:
    """
    Mineclonia items that render in item_image_button without inventory_image.

    mcl_stairs uses drawtype=mesh + stairs_stair.obj; Luanti still shows an icon in /mccshop.
    """
    name = (item_name or "").strip()
    if name.startswith("mcl_stairs:stair_"):
        return True
    return False


def classify_registry_icon(reg: LuantiRegisteredItem | None) -> str:
    if reg is None:
        return ICON_MISSING
    inv = (reg.inventory_image or "").strip()
    wield = (reg.wield_image or "").strip()
    if inv:
        return ICON_OK
    if wield:
        return ICON_OK
    if _known_good_shop_icon_without_inventory_image(reg.item_name):
        return ICON_OK
    if reg.not_in_creative_inventory:
        return ICON_UNCERTAIN
    draw = (reg.drawtype or "normal").strip().lower()
    if draw in _UNCERTAIN_DRAWTYPES:
        return ICON_UNCERTAIN
    if draw == "nodebox" and not inv:
        return ICON_UNCERTAIN
    return ICON_OK


def icon_detail_text(reg: LuantiRegisteredItem | None) -> str:
    if reg is None:
        return "Kein Registry-Eintrag — Registry aktualisieren oder Itemstring prüfen."
    parts: list[str] = []
    if reg.drawtype:
        parts.append(f"drawtype={reg.drawtype}")
    if reg.inventory_image:
        parts.append(f"inventory_image={reg.inventory_image}")
    elif reg.wield_image:
        parts.append(f"wield_image={reg.wield_image}")
    else:
        parts.append("inventory_image=(leer)")
    if reg.not_in_creative_inventory:
        parts.append("not_in_creative_inventory=1")
    parts.append(f"kind={reg.kind or 'item'}")
    return " · ".join(parts)


def icon_hint_for_item_name(
    item_name: str,
    reg_map: dict[str, LuantiRegisteredItem],
) -> dict[str, str]:
    reg = reg_map.get(item_name)
    status = classify_registry_icon(reg)
    return {
        "icon_status": status,
        "icon_label": ICON_LABELS_DE[status],
        "icon_detail": icon_detail_text(reg),
    }


def registry_item_map(
    item_names: list[str] | None = None,
) -> dict[str, LuantiRegisteredItem]:
    qs = LuantiRegisteredItem.objects.all()
    if item_names:
        qs = qs.filter(item_name__in=item_names)
    return {row.item_name: row for row in qs}


def registry_item_map_full() -> dict[str, LuantiRegisteredItem]:
    return registry_item_map(None)
