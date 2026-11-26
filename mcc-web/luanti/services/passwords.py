# Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    passwords.py
# @note    Generate and provision Luanti account passwords (Django + server).

from __future__ import annotations

import secrets
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

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


@dataclass
class BulkPasswordProvisionResult:
    queued: int = 0
    skipped_no_password: int = 0
    skipped_permission: int = 0
    skipped_already_provisioned: int = 0
    queued_login_names: list[str] = field(default_factory=list)


def bulk_provision_account_passwords(
    accounts: Iterable[LuantiAccount],
    *,
    only_unprovisioned: bool = False,
    can_provision: Callable[[LuantiAccount], bool] | None = None,
) -> BulkPasswordProvisionResult:
    """
    Re-send SET_PASSWORD for existing login_password values (world restore / recovery).
    """
    result = BulkPasswordProvisionResult()
    for account in accounts:
        if can_provision is not None and not can_provision(account):
            result.skipped_permission += 1
            continue
        if not (account.login_password or "").strip():
            result.skipped_no_password += 1
            continue
        if only_unprovisioned and account.password_provisioned:
            result.skipped_already_provisioned += 1
            continue
        provision_account_password(account, account.login_password)
        result.queued += 1
        result.queued_login_names.append(account.login_name)
    return result


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
