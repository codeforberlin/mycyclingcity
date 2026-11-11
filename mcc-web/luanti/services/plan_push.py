# Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    plan_push.py
# @note    Push hologram materialization commands to mcc_bridge.

from __future__ import annotations

from django.conf import settings

from luanti.services.command_queue import enqueue_command


def push_plan_materialize(blocks: list[dict], *, live: bool = False) -> tuple[bool, str]:
    if not blocks:
        return False, "empty"
    if live:
        layer_delay = float(
            getattr(settings, "LUANTI_PLAN_LIVE_CONVERT_LAYER_DELAY", 0.1)
        )
        block_delay = float(
            getattr(settings, "LUANTI_PLAN_LIVE_CONVERT_BLOCK_DELAY", 0.0)
        )
        fx_stagger = bool(getattr(settings, "LUANTI_PLAN_LIVE_CONVERT_FX_STAGGER", True))
    else:
        layer_delay = float(getattr(settings, "LUANTI_PLAN_CONVERT_LAYER_DELAY", 0.35))
        block_delay = float(getattr(settings, "LUANTI_PLAN_CONVERT_BLOCK_DELAY", 0.0))
        fx_stagger = bool(getattr(settings, "LUANTI_PLAN_FX_ENABLED", True))
    message = {
        "type": "PLAN_MATERIALIZE",
        "blocks": blocks,
        "layer_delay": layer_delay,
        "block_delay": block_delay,
        "fx_stagger": fx_stagger,
    }
    from luanti.consumers import LuantiEventConsumer

    sent = LuantiEventConsumer.push_to_all_sync(message)
    if sent <= 0:
        enqueue_command(message)
        return False, "queued"
    return True, f"sent={sent}"


def push_plan_clear(blocks: list[dict]) -> tuple[bool, str]:
    if not blocks:
        return False, "empty"
    message = {
        "type": "PLAN_CLEAR",
        "blocks": blocks,
    }
    from luanti.consumers import LuantiEventConsumer

    sent = LuantiEventConsumer.push_to_all_sync(message)
    if sent <= 0:
        enqueue_command(message)
        return False, "queued"
    return True, f"sent={sent}"
