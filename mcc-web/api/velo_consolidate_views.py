# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods

from api.models import Group, GroupVeloTransfer
from api.services.velo_consolidate import (
    ConsolidateError,
    consolidate_spendable,
    consolidate_top_leaves_to_top,
    preview_transfers,
)
from luanti.services.wallet import candidate_wallet_groups

TRANSFER_PERM = "api.transfer_group_velos"


def user_can_transfer_group_velos(user) -> bool:
    if not user or not user.is_authenticated or not user.is_active or not user.is_staff:
        return False
    if user.is_superuser:
        return True
    return user.has_perm(TRANSFER_PERM)


def allowed_group_ids_for_consolidate(user) -> set[int] | None:
    """
    Group PKs the user may see/transfer in Velo consolidation.

    None = unrestricted (full admin / superuser).
    Empty set = no managed groups.

    Includes all descendants under managed TOPs (also is_visible=False),
    because event teams are often hidden but still hold spendable Velos.
    """
    if not user or not user.is_authenticated:
        return set()
    if user.is_superuser:
        return None

    managed = list(user.managed_groups.all())
    if not managed:
        return set()

    allowed: set[int] = set()

    def walk(group_id: int, visited: set[int]) -> None:
        if group_id in visited:
            return
        visited.add(group_id)
        allowed.add(group_id)
        for child_id in Group.objects.filter(parent_id=group_id).values_list("id", flat=True):
            walk(int(child_id), visited)

    for group in managed:
        walk(int(group.pk), set())
    return allowed


def assert_groups_in_scope(user, group_ids: list[int]) -> None:
    """Raise ConsolidateError if any group is outside the user's scope."""
    allowed = allowed_group_ids_for_consolidate(user)
    if allowed is None:
        return
    missing = [int(x) for x in group_ids if int(x) not in allowed]
    if missing:
        raise ConsolidateError("group_out_of_scope")


def _scoped_top_groups(user):
    allowed = allowed_group_ids_for_consolidate(user)
    qs = Group.objects.filter(parent__isnull=True).order_by("name")
    if allowed is None:
        return list(qs)
    if not allowed:
        return []
    return list(qs.filter(pk__in=allowed))


def _scoped_leaf_groups(top_groups):
    leaf_groups = []
    for top in top_groups:
        for leaf in candidate_wallet_groups(top):
            leaf_groups.append({"top": top, "leaf": leaf})
    return leaf_groups


def _scoped_spendable_groups(user):
    allowed = allowed_group_ids_for_consolidate(user)
    qs = Group.objects.filter(velos_spendable__gt=0).order_by("name")
    if allowed is not None:
        if not allowed:
            return []
        qs = qs.filter(pk__in=allowed)
    return list(qs[:500])


def _scoped_recent_transfers(user):
    qs = GroupVeloTransfer.objects.select_related(
        "source_group", "target_group", "created_by"
    ).order_by("-created_at")
    allowed = allowed_group_ids_for_consolidate(user)
    if allowed is not None:
        if not allowed:
            return []
        qs = qs.filter(
            Q(source_group_id__in=allowed) | Q(target_group_id__in=allowed)
        )
    return list(qs[:30])


def _parse_amount(raw) -> int | None:
    """Parse optional transfer amount from POST; empty → None (full spendable)."""
    text = (raw or "").strip().replace(" ", "")
    if not text:
        return None
    # HTML number inputs send "25"; some locales may send "25,0".
    if "," in text and "." not in text:
        text = text.replace(",", ".")
    value = int(float(text))
    if value <= 0:
        raise ConsolidateError("invalid_amount")
    return value


def _page_context(user, *, preview=None, cons_form=None):
    top_groups = _scoped_top_groups(user)
    return {
        "title": _("Velo-Konsolidierung"),
        "top_groups": top_groups,
        "leaf_groups": _scoped_leaf_groups(top_groups),
        "spendable_groups": _scoped_spendable_groups(user),
        "recent": _scoped_recent_transfers(user),
        "preview": preview,
        "cons_form": cons_form,
        "is_full_admin": user.is_superuser,
    }


@staff_member_required
@require_http_methods(["GET", "POST"])
def group_velo_consolidate_view(request):
    if not user_can_transfer_group_velos(request.user):
        raise PermissionDenied

    if request.method == "POST":
        action = request.POST.get("action") or "consolidate"
        reason = (request.POST.get("reason") or "").strip()
        try:
            if action == "top_leaves_to_top":
                top_id = int(request.POST.get("top_id") or 0)
                assert_groups_in_scope(request.user, [top_id])
                result = consolidate_top_leaves_to_top(
                    top_id=top_id, reason=reason, user=request.user
                )
                messages.success(
                    request,
                    _(
                        "TOP-Leaves konsolidiert: %(n)s Velos in %(lines)s Buchung(en). Batch %(batch)s"
                    )
                    % {
                        "n": result["transferred"],
                        "lines": result["lines"],
                        "batch": result["batch_id"][:8],
                    },
                )
            elif action == "zero":
                source_ids = [int(x) for x in request.POST.getlist("source_ids") if x]
                assert_groups_in_scope(request.user, source_ids)
                result = consolidate_spendable(
                    source_ids=source_ids,
                    target_id=None,
                    reason=reason,
                    user=request.user,
                    action=GroupVeloTransfer.ACTION_ZERO,
                )
                messages.success(
                    request,
                    _("Spendable genullt: %(n)s Velos in %(lines)s Gruppe(n).")
                    % {"n": result["transferred"], "lines": result["lines"]},
                )
            else:
                source_ids = [int(x) for x in request.POST.getlist("source_ids") if x]
                target_id = int(request.POST.get("target_id") or 0)
                amount_raw = (request.POST.get("amount") or "").strip()
                amount = _parse_amount(amount_raw)
                assert_groups_in_scope(request.user, [*source_ids, target_id])
                # Preview confirm step
                if request.POST.get("confirm") != "1":
                    preview = preview_transfers(source_ids, target_id, amount=amount)
                    return render(
                        request,
                        "admin/api/group_velo_consolidate.html",
                        _page_context(
                            request.user,
                            preview=preview,
                            cons_form={
                                "source_ids": source_ids,
                                "target_id": target_id,
                                "reason": reason,
                                "amount": "" if amount is None else str(amount),
                                "action": "consolidate",
                            },
                        ),
                    )
                result = consolidate_spendable(
                    source_ids=source_ids,
                    target_id=target_id,
                    reason=reason,
                    user=request.user,
                    action=GroupVeloTransfer.ACTION_CONSOLIDATE,
                    amount=amount,
                )
                messages.success(
                    request,
                    _(
                        "Umbuchung OK: %(n)s Velos → Ziel. Batch %(batch)s. "
                        "Tipp: Luanti-Accounts ggf. auf Wallet-Modus „Pool“ stellen."
                    )
                    % {"n": result["transferred"], "batch": result["batch_id"][:8]},
                )
        except (TypeError, ValueError):
            messages.error(request, _("Ungültige Eingabe."))
        except ConsolidateError as exc:
            messages.error(request, _("Fehler: %(code)s") % {"code": exc.code})
        return redirect("admin:api_group_velo_consolidate")

    return render(
        request,
        "admin/api/group_velo_consolidate.html",
        _page_context(request.user),
    )
