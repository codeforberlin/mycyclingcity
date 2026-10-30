# Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import logging

from luanti.models import LuantiAccount

logger = logging.getLogger("luanti.password")


def log_luanti_password_action(
    *,
    action: str,
    user_id: int | None,
    account: LuantiAccount,
) -> None:
    """Audit Luanti password operations without logging the secret."""
    logger.info(
        "luanti_password_action action=%s user_id=%s account_id=%s login_name=%s top_group_id=%s",
        action,
        user_id,
        account.pk,
        account.login_name,
        account.assigned_to_group_id,
    )
