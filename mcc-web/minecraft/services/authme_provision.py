# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    authme_provision.py
# @note    Shared AuthMe register helpers for play and builder accounts.

from __future__ import annotations

from django.conf import settings

from minecraft.services.rcon_client import run_commands
from minecraft.services.session_control import RconSequenceError, SessionControlError

PLAY_PASSWORD_SETTING = "MCC_MINECRAFT_PLAY_ACCOUNT_PASSWORD"
BUILDER_PASSWORD_SETTING = "MCC_MINECRAFT_BUILDER_ACCOUNT_PASSWORD"


def resolve_authme_password(
    *,
    override: str | None = None,
    primary_setting: str,
    fallback_setting: str | None = None,
) -> str:
    if override is not None:
        return override.strip()
    pwd = (getattr(settings, primary_setting, "") or "").strip()
    if not pwd and fallback_setting:
        pwd = (getattr(settings, fallback_setting, "") or "").strip()
    return pwd


def response_looks_already_registered(log: str) -> bool:
    text = (log or "").lower()
    markers = (
        "already registered",
        "already exists",
        "ist bereits registriert",
        "bereits registriert",
        "name already used",
    )
    return any(m in text for m in markers)


def register_authme_login(
    login: str,
    *,
    password: str | None = None,
    primary_setting: str,
    fallback_setting: str | None = None,
    password_label: str = "AuthMe password",
) -> tuple[str, bool]:
    """
    Register a Minecraft login via AuthMe RCON.

    Returns (safe_log, was_already_registered).
    Raises SessionControlError or RconSequenceError on failure.
    """
    name = (login or "").strip()
    if not name:
        raise SessionControlError("Account login empty", code="invalid_account")

    pwd = resolve_authme_password(
        override=password,
        primary_setting=primary_setting,
        fallback_setting=fallback_setting,
    )
    if not pwd:
        raise SessionControlError(
            f"{password_label} is not set ({primary_setting})",
            code="password_not_configured",
        )
    if " " in pwd:
        raise SessionControlError(
            "AuthMe password must not contain spaces",
            code="invalid_password",
        )

    command = f"authme register {name} {pwd}"
    ok, log = run_commands([command], stop_on_error=True)
    safe_log = log.replace(pwd, "***") if pwd in log else log

    if not ok and not response_looks_already_registered(safe_log):
        raise RconSequenceError(safe_log)

    return safe_log, (not ok) and response_looks_already_registered(safe_log)
