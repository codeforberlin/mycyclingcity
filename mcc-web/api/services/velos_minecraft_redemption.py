# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Atomic Velos redemption + Minecraft waitlist entry (player/builder sessions).

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from django.contrib.auth.models import User
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from api.models import Cyclist, CyclistVelosRedemption
from api.services.velos_redemption import redeem_cyclist_velos
from minecraft.models import MinecraftSessionWaitlistEntry
from minecraft.services.waitlist_service import (
    WaitlistError,
    add_waitlist_entry,
    duration_from_velos,
    validate_player_velos,
)


@dataclass
class MinecraftSessionRedemptionResult:
    success: bool
    message: str
    velos_redeemed: int = 0
    redemption: Optional[CyclistVelosRedemption] = None
    waitlist_entry: Optional[MinecraftSessionWaitlistEntry] = None


def _internal_note_from_redemption(note: str, redemption: CyclistVelosRedemption | None) -> str:
    internal_note = note or ""
    if redemption:
        prefix = _("Velos-Einlösung #%(id)s") % {"id": redemption.pk}
        internal_note = f"{prefix}. {internal_note}".strip()
    return internal_note


def _redeem_and_add_waitlist(
    cyclist: Cyclist,
    amount: int,
    *,
    queue_type: str,
    duration_minutes: int | None,
    velos_cost: int,
    redeemed_by: Optional[User] = None,
    note: str = "",
    external_currency: str = "",
) -> MinecraftSessionRedemptionResult:
    redeem_amount = int(amount)
    if redeem_amount <= 0:
        return MinecraftSessionRedemptionResult(
            success=False,
            message=str(_("Der Einlösungsbetrag muss größer als 0 sein.")),
        )

    redemption_result = redeem_cyclist_velos(
        cyclist,
        redeemed_by=redeemed_by,
        note=note or "",
        external_currency=external_currency or "",
        amount=redeem_amount,
    )
    if not redemption_result.success:
        return MinecraftSessionRedemptionResult(
            success=False,
            message=redemption_result.message,
        )

    cyclist = Cyclist.objects.get(pk=cyclist.pk)
    internal_note = _internal_note_from_redemption(note, redemption_result.redemption)

    try:
        waitlist_entry = add_waitlist_entry(
            queue_type=queue_type,
            guest_label=cyclist.user_id,
            velos_cost=velos_cost,
            duration_minutes=duration_minutes,
            internal_note=internal_note,
            user=redeemed_by,
            source=MinecraftSessionWaitlistEntry.SOURCE_VELOS_REDEEM,
            cyclist=cyclist,
            velos_redemption=redemption_result.redemption,
        )
    except WaitlistError as exc:
        transaction.set_rollback(True)
        return MinecraftSessionRedemptionResult(success=False, message=str(exc))

    return MinecraftSessionRedemptionResult(
        success=True,
        message="",
        velos_redeemed=redemption_result.velos_redeemed,
        redemption=redemption_result.redemption,
        waitlist_entry=waitlist_entry,
    )


def _redeem_session_from_velos(
    cyclist: Cyclist,
    amount: int,
    *,
    queue_type: str,
    success_message_template: str,
    redeemed_by: Optional[User] = None,
    note: str = "",
    external_currency: str = "",
) -> MinecraftSessionRedemptionResult:
    """Redeem Velos; session duration follows player_velos_per_minute (same for play/build)."""
    redeem_amount = int(amount)
    try:
        validate_player_velos(redeem_amount)
    except WaitlistError as exc:
        return MinecraftSessionRedemptionResult(success=False, message=str(exc))

    minutes = duration_from_velos(redeem_amount)
    result = _redeem_and_add_waitlist(
        cyclist,
        redeem_amount,
        queue_type=queue_type,
        duration_minutes=minutes,
        velos_cost=redeem_amount,
        redeemed_by=redeemed_by,
        note=note,
        external_currency=external_currency,
    )
    if not result.success:
        return result

    entry = result.waitlist_entry
    assert entry is not None
    result.message = str(
        success_message_template
        % {
            "amount": result.velos_redeemed,
            "ticket": entry.ticket_number,
            "minutes": entry.duration_minutes,
        }
    )
    return result


@transaction.atomic
def redeem_velos_for_player_session(
    cyclist: Cyclist,
    amount: int,
    *,
    redeemed_by: Optional[User] = None,
    note: str = "",
    external_currency: str = "",
) -> MinecraftSessionRedemptionResult:
    """
    Redeem RFID Velos and create a player waitlist entry in one transaction.

    Duration = velos ÷ player_velos_per_minute (e.g. 300 → 15 Min.).
    """
    return _redeem_session_from_velos(
        cyclist,
        amount,
        queue_type=MinecraftSessionWaitlistEntry.QUEUE_PLAYER,
        success_message_template=_(
            "%(amount)s Velos eingelöst — Spiel-Session in Warteliste "
            "(Ticket #%(ticket)s, %(minutes)s Min.)."
        ),
        redeemed_by=redeemed_by,
        note=note,
        external_currency=external_currency,
    )


@transaction.atomic
def redeem_velos_for_builder_session(
    cyclist: Cyclist,
    amount: int,
    *,
    redeemed_by: Optional[User] = None,
    note: str = "",
    external_currency: str = "",
) -> MinecraftSessionRedemptionResult:
    """
    Redeem RFID Velos and create a builder waitlist entry in one transaction.

    Same duration rule as Spiel-Session: velos ÷ player_velos_per_minute.
    """
    return _redeem_session_from_velos(
        cyclist,
        amount,
        queue_type=MinecraftSessionWaitlistEntry.QUEUE_BUILDER,
        success_message_template=_(
            "%(amount)s Velos eingelöst — Bau-Session in Warteliste "
            "(Ticket #%(ticket)s, %(minutes)s Min.)."
        ),
        redeemed_by=redeemed_by,
        note=note,
        external_currency=external_currency,
    )


# Backward-compatible alias for Phase A imports/tests.
PlayerSessionRedemptionResult = MinecraftSessionRedemptionResult
