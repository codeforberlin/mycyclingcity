# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    builder_account_provision.py
# @note    Create AuthMe accounts for active builder registrations via RCON.

from __future__ import annotations

from django.utils import timezone

from config.logger_utils import get_logger
from minecraft.models import MinecraftTeamRegistration
from minecraft.services.authme_provision import (
    BUILDER_PASSWORD_SETTING,
    PLAY_PASSWORD_SETTING,
    register_authme_login,
)
from minecraft.services.session_control import RconSequenceError

logger = get_logger("minecraft")


def register_builder_account_on_minecraft(
    registration: MinecraftTeamRegistration,
    *,
    password: str | None = None,
) -> str:
    """
    Register the builder MC username on the Minecraft server via AuthMe.

    Password: MCC_MINECRAFT_BUILDER_ACCOUNT_PASSWORD, else play-account password.
    """
    login = (registration.mc_username or "").strip()
    try:
        safe_log, already = register_authme_login(
            login,
            password=password,
            primary_setting=BUILDER_PASSWORD_SETTING,
            fallback_setting=PLAY_PASSWORD_SETTING,
            password_label="Builder account password",
        )
    except RconSequenceError as exc:
        registration.authme_last_error = str(exc)[:5000]
        registration.save(update_fields=["authme_last_error"])
        logger.error(
            "[builder_account_provision] AuthMe register failed login=%s detail=%s",
            login,
            registration.authme_last_error,
        )
        raise

    registration.authme_is_registered = True
    registration.authme_registered_at = timezone.now()
    registration.authme_last_error = ""
    registration.save(
        update_fields=[
            "authme_is_registered",
            "authme_registered_at",
            "authme_last_error",
        ]
    )
    logger.info(
        "[builder_account_provision] AuthMe register ok login=%s already=%s",
        login,
        already,
    )
    return safe_log
