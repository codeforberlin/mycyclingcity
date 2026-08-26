# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Resolve which api.Group.velos_spendable a Luanti player may spend.

from __future__ import annotations

from django.db import transaction
from django.db.models import F

from api.models import Group
from api.velos import is_true_leaf_group
from luanti.models import LuantiAccount, LuantiSession


class WalletError(Exception):
    def __init__(self, code: str, message: str = ""):
        self.code = code
        super().__init__(message or code)


def _team_key(group: Group | None) -> str:
    if group is None:
        return ""
    return (getattr(group, "luanti_username", None) or group.mc_username or "") or ""


def pick_auto_leaf_wallet(home: Group | None) -> Group | None:
    """Among direct children of home (true leaves), pick highest velos_spendable."""
    if home is None:
        return None
    best: Group | None = None
    best_bal = -1
    for child in home.children.all():
        if not is_true_leaf_group(child):
            continue
        bal = int(child.velos_spendable or 0)
        if bal > best_bal:
            best = child
            best_bal = bal
    return best


def resolve_wallet_group(
    account: LuantiAccount | None,
    *,
    session: LuantiSession | None = None,
    login_name: str | None = None,
) -> Group | None:
    """
    Resolve spendable wallet for a Luanti player.

    Priority:
      1. session.wallet_group (per-session override)
      2. wallet_mode fixed → active_wallet
      3. wallet_mode pool → assigned_to_group (home)
      4. wallet_mode auto_leaf → richest leaf under home
      5. fallbacks: active_wallet, assigned_to_group, Group.luanti_username match
    """
    if account is None and login_name:
        account = (
            LuantiAccount.objects.filter(login_name__iexact=login_name.strip())
            .select_related("assigned_to_group", "active_wallet")
            .first()
        )

    if session is not None and session.wallet_group_id:
        return session.wallet_group

    if account is None:
        if login_name:
            return Group.objects.filter(luanti_username__iexact=login_name.strip()).first()
        return None

    mode = account.wallet_mode or LuantiAccount.WALLET_FIXED
    home = account.assigned_to_group

    if mode == LuantiAccount.WALLET_FIXED and account.active_wallet_id:
        return account.active_wallet
    if mode == LuantiAccount.WALLET_POOL and home is not None:
        return home
    if mode == LuantiAccount.WALLET_AUTO_LEAF:
        leaf = pick_auto_leaf_wallet(home)
        if leaf is not None:
            return leaf

    if account.active_wallet_id:
        return account.active_wallet
    if home is not None:
        return home
    return Group.objects.filter(luanti_username__iexact=account.login_name).first()


def wallet_payload(account: LuantiAccount | None, *, session: LuantiSession | None = None) -> dict:
    group = resolve_wallet_group(account, session=session)
    return {
        "wallet_group_id": group.pk if group else None,
        "wallet_group_name": group.name if group else "",
        "team_key": _team_key(group),
        "velos_spendable": int(group.velos_spendable or 0) if group else 0,
    }


@transaction.atomic
def withdraw_velos(*, login_name: str, amount: int) -> dict:
    """Deduct spendable Velos from the player's resolved wallet."""
    amount = int(amount)
    if amount <= 0:
        raise WalletError("invalid_amount")
    account = (
        LuantiAccount.objects.filter(login_name__iexact=login_name.strip(), is_active=True)
        .select_related("assigned_to_group", "active_wallet")
        .first()
    )
    if account is None:
        raise WalletError("account_not_found")
    from luanti.services.session_control import get_active_session

    session = get_active_session(account.login_name)
    group = resolve_wallet_group(account, session=session)
    if group is None:
        raise WalletError("no_wallet")
    group = Group.objects.select_for_update().get(pk=group.pk)
    if int(group.velos_spendable or 0) < amount:
        raise WalletError("insufficient_velos")
    group.velos_spendable = F("velos_spendable") - amount
    group.save(update_fields=["velos_spendable"])
    group.refresh_from_db(fields=["velos_spendable"])
    return {
        "ok": True,
        "withdrawn": amount,
        "velos_spendable": int(group.velos_spendable),
        "wallet_group_id": group.pk,
        "wallet_group_name": group.name,
    }


def candidate_wallet_groups(home: Group | None) -> list[Group]:
    """True leaf groups under a TOP/home group (for wallet dropdowns)."""
    if home is None:
        return []
    leaves: list[Group] = []

    def walk(node: Group) -> None:
        children = list(node.children.all())
        if not children:
            if node.pk != home.pk:
                leaves.append(node)
            return
        for child in children:
            walk(child)

    walk(home)
    leaves.sort(key=lambda g: (g.name or "").lower())
    return leaves


def leaves_by_home_payload(top_groups) -> dict[str, list[dict]]:
    """JSON-friendly map home_id -> [{id, name, velos_spendable}, ...] for Admin UI."""
    payload: dict[str, list[dict]] = {}
    for top in top_groups:
        payload[str(top.pk)] = [
            {
                "id": g.pk,
                "name": g.name,
                "velos_spendable": int(g.velos_spendable or 0),
            }
            for g in candidate_wallet_groups(top)
        ]
    return payload
