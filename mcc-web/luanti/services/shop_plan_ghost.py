# Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Plan-mode hologram clone status (from bridge registry dump / shop verify job).

from __future__ import annotations

from luanti.models import LuantiRegisteredItem

PLAN_GHOST_SHAPE = "shape"
PLAN_GHOST_PREVIEW_SHAPE = "preview_shape"
PLAN_GHOST_FALLBACK = "fallback"
PLAN_GHOST_NA = "na"
PLAN_GHOST_UNKNOWN = "unknown"

VALID_PLAN_GHOST_STATUSES = frozenset(
    {
        PLAN_GHOST_SHAPE,
        PLAN_GHOST_PREVIEW_SHAPE,
        PLAN_GHOST_FALLBACK,
        PLAN_GHOST_NA,
        PLAN_GHOST_UNKNOWN,
    }
)

PLAN_GHOST_LABELS_DE: dict[str, str] = {
    PLAN_GHOST_SHAPE: "Plan-Holo: Form-Klon",
    PLAN_GHOST_PREVIEW_SHAPE: "Plan-Holo: Form-Klon (Vorschau)",
    PLAN_GHOST_FALLBACK: "Plan-Holo: Glaswürfel",
    PLAN_GHOST_NA: "Plan-Holo: n/a",
    PLAN_GHOST_UNKNOWN: "Plan-Holo: nicht geprüft",
}

_BAD_HOLO_DRAWTYPES = frozenset({"liquid", "flowingliquid", "airlike"})


def classify_plan_ghost_heuristic(reg: LuantiRegisteredItem | None) -> str:
    """Fallback when bridge has not yet reported plan_ghost_status."""
    if reg is None:
        return PLAN_GHOST_UNKNOWN
    if (reg.kind or "").strip() != "node":
        return PLAN_GHOST_NA
    draw = (reg.drawtype or "normal").strip().lower() or "normal"
    if draw in _BAD_HOLO_DRAWTYPES:
        return PLAN_GHOST_FALLBACK
    return PLAN_GHOST_PREVIEW_SHAPE


def resolve_plan_ghost_status(reg: LuantiRegisteredItem | None) -> str:
    if reg is None:
        return PLAN_GHOST_UNKNOWN
    stored = (reg.plan_ghost_status or "").strip()
    if stored in VALID_PLAN_GHOST_STATUSES:
        # Legacy registry rows said "shape" without a real register check.
        detail = (reg.plan_ghost_detail or "").strip()
        if stored == PLAN_GHOST_SHAPE and detail in ("", "registry_preview"):
            return PLAN_GHOST_PREVIEW_SHAPE
        return stored
    return classify_plan_ghost_heuristic(reg)


def plan_ghost_detail_text(reg: LuantiRegisteredItem | None, status: str) -> str:
    if reg is None:
        return "Kein Registry-Eintrag — Registry vom Server aktualisieren."
    parts: list[str] = []
    if reg.plan_ghost_detail:
        parts.append(reg.plan_ghost_detail)
    if reg.plan_ghost_checked_at:
        parts.append(f"geprüft={reg.plan_ghost_checked_at:%Y-%m-%d %H:%M}")
    elif status == PLAN_GHOST_UNKNOWN:
        parts.append("Registry-Dump oder Shop-Plan-Prüfung ausführen")
    if reg.drawtype:
        parts.append(f"drawtype={reg.drawtype}")
    parts.append(f"kind={reg.kind or '?'}")
    return " · ".join(parts)


def plan_ghost_hint_for_item_name(
    item_name: str,
    reg_map: dict[str, LuantiRegisteredItem],
) -> dict[str, str]:
    reg = reg_map.get(item_name)
    status = resolve_plan_ghost_status(reg)
    return {
        "plan_ghost_status": status,
        "plan_ghost_label": PLAN_GHOST_LABELS_DE[status],
        "plan_ghost_detail": plan_ghost_detail_text(reg, status),
    }


def plan_ghost_hint_html(hint: dict[str, str]):
    """Colored admin label (requires ``admin/css/luanti_shop_plan_ghost.css``)."""
    from django.utils.html import format_html

    return format_html(
        '<span class="shop-plan-{}" title="{}">{}</span>',
        hint.get("plan_ghost_status") or PLAN_GHOST_UNKNOWN,
        hint.get("plan_ghost_detail") or "",
        hint.get("plan_ghost_label") or PLAN_GHOST_LABELS_DE[PLAN_GHOST_UNKNOWN],
    )
