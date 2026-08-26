# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    region_ops.py
# @note    Helpers for Luanti protected-region admin (IDs, defaults, coords).

from __future__ import annotations

import re

from django.conf import settings
from django.utils.translation import gettext as _

_REGION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-]{0,62}$")
_PLAYER_RE = re.compile(r"^[A-Za-z0-9_]{1,32}$")


def default_world() -> str:
    return (getattr(settings, "MCC_LUANTI_WORLD", None) or "world").strip() or "world"


def default_region_min_y() -> int:
    return int(getattr(settings, "MCC_LUANTI_WORLD_MIN_Y", -64))


def default_region_max_y() -> int:
    return int(getattr(settings, "MCC_LUANTI_WORLD_MAX_Y", 320))


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
        raise ValueError(_("Ungültiger Spielername (1–32 Zeichen, A–Z, 0–9, _)."))
    return name


def parse_int_coord(raw, field: str) -> int:
    text = str(raw if raw is not None else "").strip()
    if text == "":
        raise ValueError(_("Feld %(field)s fehlt.") % {"field": field})
    try:
        return int(float(text))
    except (TypeError, ValueError) as exc:
        raise ValueError(_("Feld %(field)s ist keine ganze Zahl.") % {"field": field}) from exc


def suggest_subregion_id(parent_region_id: str, sub_slug: str) -> str:
    parent = normalize_region_id(parent_region_id)
    slug = (sub_slug or "").strip().lower().replace(" ", "_")
    if not slug:
        raise ValueError(_("Sub-Slug fehlt."))
    if not re.match(r"^[a-z0-9][a-z0-9_\-]{0,40}$", slug):
        raise ValueError(_("Ungültiger Sub-Slug."))
    return normalize_region_id(f"{parent}_{slug}")
