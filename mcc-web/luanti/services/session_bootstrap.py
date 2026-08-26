# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Auto-run a DB city preset when a Luanti session starts (analog Minecraft bootstrap).

from __future__ import annotations

from django.conf import settings

from config.logger_utils import get_logger
from luanti.city_preset_defaults import SESSION_BOOTSTRAP_STEPS
from luanti.consumers import LuantiEventConsumer
from luanti.models import LuantiCityPreset
from luanti.services.city import mark_preset_run, preset_event_payload

logger = get_logger("luanti")

DEFAULT_BOOTSTRAP_SLUG = "session-bootstrap"


def session_bootstrap_enabled() -> bool:
    return bool(getattr(settings, "MCC_LUANTI_SESSION_BOOTSTRAP_ENABLED", True))


def session_bootstrap_preset_slug() -> str:
    slug = getattr(settings, "MCC_LUANTI_SESSION_BOOTSTRAP_PRESET_SLUG", "") or ""
    return slug or DEFAULT_BOOTSTRAP_SLUG


def get_bootstrap_preset() -> LuantiCityPreset | None:
    slug = session_bootstrap_preset_slug()
    return LuantiCityPreset.objects.filter(slug=slug, enabled=True).first()


def get_bootstrap_steps() -> list[dict]:
    preset = get_bootstrap_preset()
    if preset is not None:
        return list(preset.steps or [])
    logger.warning(
        "[session_bootstrap] preset slug=%s missing, using code defaults",
        session_bootstrap_preset_slug(),
    )
    return list(SESSION_BOOTSTRAP_STEPS)


def push_session_bootstrap(*, user=None) -> tuple[bool, str]:
    """Push bootstrap steps to the bridge (HTTP queue / WS)."""
    if not session_bootstrap_enabled():
        return False, "disabled"
    preset = get_bootstrap_preset()
    if preset is not None:
        payload = preset_event_payload(preset)
        sent = LuantiEventConsumer.push_to_all_sync(payload)
        msg = f"bootstrap slug={preset.slug} sent={sent}"
        mark_preset_run(preset, user=user, success=sent > 0, output=msg)
        return sent > 0, msg
    # Fallback without DB row: synthesize payload
    payload = {
        "type": "RUN_CITY_PRESET",
        "slug": session_bootstrap_preset_slug(),
        "name": "Session-Start",
        "steps": get_bootstrap_steps(),
    }
    sent = LuantiEventConsumer.push_to_all_sync(payload)
    return sent > 0, f"bootstrap fallback sent={sent}"
