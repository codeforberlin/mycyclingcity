# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    play_account_provision.py
# @note    Create AuthMe accounts for MCC play slots via RCON.

from __future__ import annotations

from django.utils import timezone

from config.logger_utils import get_logger
from minecraft.models import MinecraftPlayAccount
from minecraft.services.authme_provision import PLAY_PASSWORD_SETTING, register_authme_login
from minecraft.services.session_control import RconSequenceError, SessionControlError

logger = get_logger("minecraft")


def register_play_account_on_minecraft(
    account: MinecraftPlayAccount,
    *,
    password: str | None = None,
) -> str:
    """
    Register the play account login on the Minecraft server via AuthMe.

    RCON: ``authme register <short_name> <password>``
    Password comes from argument or MCC_MINECRAFT_PLAY_ACCOUNT_PASSWORD.
    """
    login = (account.short_name or "").strip()
    try:
        safe_log, already = register_authme_login(
            login,
            password=password,
            primary_setting=PLAY_PASSWORD_SETTING,
            password_label="Play account password",
        )
    except RconSequenceError as exc:
        account.authme_last_error = str(exc)[:5000]
        account.save(update_fields=["authme_last_error", "updated_at"])
        logger.error(
            "[play_account_provision] AuthMe register failed login=%s detail=%s",
            login,
            account.authme_last_error,
        )
        raise

    account.authme_is_registered = True
    account.authme_registered_at = timezone.now()
    account.authme_last_error = ""
    account.save(
        update_fields=[
            "authme_is_registered",
            "authme_registered_at",
            "authme_last_error",
            "updated_at",
        ]
    )
    logger.info(
        "[play_account_provision] AuthMe register ok login=%s already=%s",
        login,
        already,
    )
    return safe_log
