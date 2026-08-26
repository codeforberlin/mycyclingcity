# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Consolidate / zero Group.velos_spendable without touching velos_total history.

from __future__ import annotations

import uuid

from django.db import transaction
from django.db.models import F

from api.models import Group, GroupVeloTransfer
from luanti.services.wallet import candidate_wallet_groups


class ConsolidateError(Exception):
    def __init__(self, code: str, message: str = ""):
        self.code = code
        super().__init__(message or code)


def preview_transfers(source_ids: list[int], target_id: int | None) -> dict:
    sources = list(Group.objects.filter(pk__in=source_ids).order_by("name"))
    target = Group.objects.filter(pk=target_id).first() if target_id else None
    lines = []
    total = 0
    for g in sources:
        amount = max(0, int(g.velos_spendable or 0))
        lines.append(
            {
                "id": g.pk,
                "name": g.name,
                "amount": amount,
            }
        )
        total += amount
    return {
        "sources": lines,
        "total": total,
        "target": {"id": target.pk, "name": target.name} if target else None,
    }


def leaf_ids_under_top(top: Group) -> list[int]:
    return [g.pk for g in candidate_wallet_groups(top)]


@transaction.atomic
def consolidate_spendable(
    *,
    source_ids: list[int],
    target_id: int | None,
    reason: str,
    user=None,
    action: str = GroupVeloTransfer.ACTION_CONSOLIDATE,
) -> dict:
    """
    Move or zero velos_spendable on source groups.

    - consolidate: require target; each source spendable → target; source → 0
    - zero: no target; each source spendable → 0 (amount audited)
    velos_total is never modified.
    """
    reason = (reason or "").strip()
    if not reason:
        raise ConsolidateError("missing_reason")
    if not source_ids:
        raise ConsolidateError("no_sources")

    action = action or GroupVeloTransfer.ACTION_CONSOLIDATE
    if action not in dict(GroupVeloTransfer.ACTION_CHOICES):
        raise ConsolidateError("invalid_action")

    # Lock in stable PK order to avoid deadlocks.
    ids = sorted({int(x) for x in source_ids})
    sources = list(Group.objects.select_for_update().filter(pk__in=ids).order_by("pk"))
    if len(sources) != len(ids):
        raise ConsolidateError("source_not_found")

    target: Group | None = None
    if action == GroupVeloTransfer.ACTION_CONSOLIDATE:
        if not target_id:
            raise ConsolidateError("missing_target")
        target = Group.objects.select_for_update().filter(pk=int(target_id)).first()
        if target is None:
            raise ConsolidateError("target_not_found")
        if target.pk in ids:
            raise ConsolidateError("target_in_sources")

    batch_id = uuid.uuid4()
    transferred = 0
    rows: list[GroupVeloTransfer] = []

    for src in sources:
        amount = max(0, int(src.velos_spendable or 0))
        if amount == 0:
            continue
        src.velos_spendable = F("velos_spendable") - amount
        src.save(update_fields=["velos_spendable"])
        if target is not None:
            target.velos_spendable = F("velos_spendable") + amount
            target.save(update_fields=["velos_spendable"])
        rows.append(
            GroupVeloTransfer(
                batch_id=batch_id,
                action=action,
                source_group=src,
                target_group=target,
                amount=amount,
                reason=reason[:255],
                created_by=user if getattr(user, "is_authenticated", False) else None,
            )
        )
        transferred += amount

    if rows:
        GroupVeloTransfer.objects.bulk_create(rows)
        if target is not None:
            target.refresh_from_db(fields=["velos_spendable"])

    _maybe_push_minecraft([*sources, target] if target else sources)

    return {
        "ok": True,
        "batch_id": str(batch_id),
        "action": action,
        "transferred": transferred,
        "lines": len(rows),
        "target_spendable": int(target.velos_spendable) if target else None,
    }


def consolidate_top_leaves_to_top(*, top_id: int, reason: str, user=None) -> dict:
    top = Group.objects.filter(pk=top_id, parent__isnull=True).first()
    if top is None:
        raise ConsolidateError("top_not_found")
    leaf_ids = leaf_ids_under_top(top)
    if not leaf_ids:
        raise ConsolidateError("no_leaves")
    return consolidate_spendable(
        source_ids=leaf_ids,
        target_id=top.pk,
        reason=reason,
        user=user,
        action=GroupVeloTransfer.ACTION_CONSOLIDATE,
    )


def _maybe_push_minecraft(groups: list[Group | None]) -> None:
    """Best-effort scoreboard sync for groups that have mc_username."""
    try:
        from minecraft.services.team_registration import push_team_velos_to_minecraft
    except Exception:
        return
    for g in groups:
        if g is None:
            continue
        try:
            g.refresh_from_db(fields=["velos_spendable", "mc_username"])
            if g.mc_username:
                push_team_velos_to_minecraft(g)
        except Exception:
            continue
