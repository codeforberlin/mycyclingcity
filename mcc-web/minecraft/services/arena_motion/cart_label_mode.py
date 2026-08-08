# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    cart_label_mode.py
# @note    Floating cart label display mode (name-only vs full status).

from __future__ import annotations

from typing import Any

from django.conf import settings

CART_LABEL_MODE_NAME_ONLY = "name_only"
CART_LABEL_MODE_FULL = "full"

VALID_CART_LABEL_MODES = frozenset({CART_LABEL_MODE_NAME_ONLY, CART_LABEL_MODE_FULL})


def default_cart_label_mode() -> str:
    raw = str(
        getattr(settings, "MCC_MINECRAFT_ARENA_CART_LABEL_MODE", CART_LABEL_MODE_NAME_ONLY)
        or CART_LABEL_MODE_NAME_ONLY
    )
    return normalize_cart_label_mode(raw)


def normalize_cart_label_mode(raw: Any) -> str:
    mode = str(raw or "").strip().lower()
    if mode in VALID_CART_LABEL_MODES:
        return mode
    return default_cart_label_mode()


def is_name_only_label_mode(mode: str) -> bool:
    return normalize_cart_label_mode(mode) == CART_LABEL_MODE_NAME_ONLY
