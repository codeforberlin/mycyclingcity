# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Redeem 100% of a cyclist's Velos balance (FEZitty / Wuhlis workflow).
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


@transaction.atomic
def redeem_cyclist_velos(
    cyclist: Cyclist,
    redeemed_by: Optional[User] = None,
    note: str = "",
    external_currency: str = "",
) -> RedemptionResult:
    """
    Redeem 100% of velos_balance. Ends active session so RFID tag can be reused immediately.
    """
    cyclist = Cyclist.objects.select_for_update().get(pk=cyclist.pk)
    balance = cyclist.velos_balance or 0

    if balance <= 0:
        return RedemptionResult(
            success=False,
            message=str(_("Kein Velos-Guthaben zum Einlösen vorhanden.")),
        )

    leaf_group = cyclist.groups.first()
    if leaf_group and not is_true_leaf_group(leaf_group):
        return RedemptionResult(
            success=False,
            message=str(_("Radler ist keiner Leaf-Gruppe zugeordnet.")),
        )

    _flush_active_session_to_hourly_metric(cyclist)
    CyclistDeviceCurrentMileage.objects.filter(cyclist=cyclist).delete()

    redemption = CyclistVelosRedemption.objects.create(
        cyclist=cyclist,
        leaf_group=leaf_group,
        velos_redeemed=balance,
        redeemed_by=redeemed_by,
        note=note or "",
        external_currency=external_currency or "",
    )

    cyclist.velos_balance = 0
    cyclist.save(update_fields=['velos_balance'])

    return RedemptionResult(
        success=True,
        message=str(_("%(amount)s Velos eingelöst.") % {'amount': balance}),
        velos_redeemed=balance,
        redemption=redemption,
    )


def redeem_cyclist_by_identifier(
    identifier: str,
    redeemed_by: Optional[User] = None,
    note: str = "",
    external_currency: str = "",
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
    )
