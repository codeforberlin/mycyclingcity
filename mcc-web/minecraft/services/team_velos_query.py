# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

from minecraft.services.team_registration import get_active_registration_by_mc_username


def get_team_velos_by_mc_username(mc_username: str) -> dict | None:
    """Return spendable/total Velos for a registered team scoreboard name."""
    registration = get_active_registration_by_mc_username(mc_username)
    if not registration:
        return None

    group = registration.group
    return {
        "player": registration.mc_username,
        "team_name": group.name,
        "velos_spendable": int(group.velos_spendable or 0),
        "velos_total": int(group.velos_total or 0),
    }
