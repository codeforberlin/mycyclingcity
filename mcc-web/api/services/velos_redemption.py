# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Redeem cyclist Velos balance (full or partial; FEZitty / Wuhlis workflow).
# Does not modify HourlyMetric or group ledger.

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from django.contrib.auth.models import User
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from api.models import Cyclist, CyclistDeviceCurrentMileage, CyclistVelosRedemption
from api.services.hourly_metric_flush import persist_session_to_hourly_metric
from api.velos import is_true_leaf_group


@dataclass
class RedemptionResult:
    success: bool
    message: str
    velos_redeemed: int = 0
    redemption: Optional[CyclistVelosRedemption] = None


def _flush_active_session_to_hourly_metric(cyclist: Cyclist) -> None:
    """Persist open session distance to HourlyMetric before ending the session."""
    try:
        session = cyclist.cyclistdevicecurrentmileage
    except CyclistDeviceCurrentMileage.DoesNotExist:
        return

    persist_session_to_hourly_metric(session)


def _end_active_session(cyclist: Cyclist) -> None:
    _flush_active_session_to_hourly_metric(cyclist)
    CyclistDeviceCurrentMileage.objects.filter(cyclist=cyclist).delete()


@transaction.atomic
def redeem_cyclist_velos(
    cyclist: Cyclist,
    redeemed_by: Optional[User] = None,
    note: str = "",
    external_currency: str = "",
    amount: Optional[int] = None,
) -> RedemptionResult:
    """
    Redeem Velos from velos_balance.

    amount=None redeems the full balance and ends the active device session.
    Partial redemption keeps the session open unless the balance reaches zero.
    """
    cyclist = Cyclist.objects.select_for_update().get(pk=cyclist.pk)
    balance = cyclist.velos_balance or 0

    if balance <= 0:
        return RedemptionResult(
            success=False,
            message=str(_("Kein Velos-Guthaben zum Einlösen vorhanden.")),
        )

    redeem_amount = balance if amount is None else int(amount)
    if redeem_amount <= 0:
        return RedemptionResult(
            success=False,
            message=str(_("Der Einlösungsbetrag muss größer als 0 sein.")),
        )
    if redeem_amount > balance:
        return RedemptionResult(
            success=False,
            message=str(
                _("Nur %(available)s Velos verfügbar, %(requested)s angefordert.")
                % {'available': balance, 'requested': redeem_amount}
            ),
        )

    leaf_group = cyclist.groups.first()
    if leaf_group and not is_true_leaf_group(leaf_group):
        return RedemptionResult(
            success=False,
            message=str(_("Radler ist keiner Leaf-Gruppe zugeordnet.")),
        )

    redemption = CyclistVelosRedemption.objects.create(
        cyclist=cyclist,
        leaf_group=leaf_group,
        velos_redeemed=redeem_amount,
        redeemed_by=redeemed_by,
        note=note or "",
        external_currency=external_currency or "",
    )

    new_balance = balance - redeem_amount
    cyclist.velos_balance = new_balance
    cyclist.save(update_fields=['velos_balance'])

    if new_balance == 0:
        _end_active_session(cyclist)

    return RedemptionResult(
        success=True,
        message=str(_("%(amount)s Velos eingelöst.") % {'amount': redeem_amount}),
        velos_redeemed=redeem_amount,
        redemption=redemption,
    )


def redeem_cyclist_by_identifier(
    identifier: str,
    redeemed_by: Optional[User] = None,
    note: str = "",
    external_currency: str = "",
    amount: Optional[int] = None,
) -> RedemptionResult:
    """Lookup cyclist by user_id or id_tag and redeem."""
    from django.db.models import Q

    try:
        cyclist = Cyclist.objects.get(
            Q(user_id__iexact=identifier) | Q(id_tag__iexact=identifier)
        )
    except Cyclist.DoesNotExist:
        return RedemptionResult(
            success=False,
            message=str(_("Radler nicht gefunden.")),
        )
    return redeem_cyclist_velos(
        cyclist,
        redeemed_by=redeemed_by,
        note=note,
        external_currency=external_currency,
        amount=amount,
    )
