# Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    passwords.py
# @note    Generate and provision Luanti account passwords (Django + server).

from __future__ import annotations

import secrets

from django.utils import timezone

from luanti.consumers import LuantiEventConsumer
from luanti.models import LuantiAccount

# Avoid ambiguous characters (0/O, 1/l/I) for kiosk operators.
_PASSWORD_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789abcdefghijkmnopqrstuvwxyz"


def generate_login_password(*, length: int = 8) -> str:
    length = max(6, min(32, int(length)))
    return "".join(secrets.choice(_PASSWORD_ALPHABET) for _ in range(length))


def provision_account_password(
    account: LuantiAccount,
    password: str | None = None,
    *,
    mark_pending: bool = True,
) -> str:
    """
    Store plaintext password on the account and enqueue SET_PASSWORD for the bridge.
    Returns the password that was stored.

    password_provisioned becomes True only after the bridge ACK (see ack_password_provisioned).
    """
    raw = (password or "").strip() or generate_login_password()
    now = timezone.now()
    account.login_password = raw
    account.password_last_set_at = now
    if mark_pending:
        account.password_provisioned = False
    account.save(
        update_fields=[
            "login_password",
            "password_last_set_at",
            "password_provisioned",
            "updated_at",
        ]
    )

    LuantiEventConsumer.push_to_all_sync(
        {
            "type": "SET_PASSWORD",
            "player": account.login_name,
            "password": raw,
            "account_id": account.pk,
        }
    )
    return raw


def ack_password_provisioned(
    *,
    account_id: int | None = None,
    login_name: str = "",
    ok: bool = True,
) -> LuantiAccount | None:
    """Mark account password as applied on the Luanti server (bridge ACK)."""
    account = None
    if account_id:
        account = LuantiAccount.objects.filter(pk=account_id).first()
    if account is None and login_name.strip():
        account = LuantiAccount.objects.filter(login_name__iexact=login_name.strip()).first()
    if account is None:
        return None
    if ok:
        account.password_provisioned = True
        account.save(update_fields=["password_provisioned", "updated_at"])
    return account
