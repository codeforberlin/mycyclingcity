# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    world_tickets.py
# @note    Paper MCC-Tickets (custom_data) issued at session start; optional RFID debit.

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from django.contrib.auth.models import AbstractBaseUser
from django.utils.translation import gettext as _

from api.models import Cyclist
from api.services.velos_redemption import RedemptionResult, redeem_cyclist_velos
from minecraft.models import MinecraftIntegrationConfig, MinecraftSessionWaitlistEntry

# Minecraft 1.21+ item components; hopper/shopkeeper can match custom_data={mcc_ticket:true}.
# item_name is what inventory shows by default — must include color (plain item_name = white).
_PAPER_COMPONENTS = (
    "custom_data={mcc_ticket:true},"
    "item_name={text:\"MCC-Ticket\",color:\"gold\",bold:true},"
    "custom_name={text:\"MCC-Ticket\",color:\"gold\",bold:true,italic:false},"
    "enchantment_glint_override=true,"
    "lore=[{text:\"Einlösbar für: Fahrzeuge, Eintritt & Aktionen\",color:\"gray\",italic:false}]"
)


@dataclass(frozen=True)
class WorldTicketSettings:
    enabled: bool
    velos_per_ticket: int
    max_count: int


def get_world_ticket_settings(
    config: MinecraftIntegrationConfig | None = None,
) -> WorldTicketSettings:
    cfg = config or MinecraftIntegrationConfig.get_config()
    return WorldTicketSettings(
        enabled=bool(getattr(cfg, "world_ticket_enabled", True)),
        velos_per_ticket=max(1, int(getattr(cfg, "world_ticket_velos", 100) or 100)),
        max_count=max(1, int(getattr(cfg, "world_ticket_max", 10) or 10)),
    )


def normalize_ticket_count(
    raw,
    *,
    config: MinecraftIntegrationConfig | None = None,
) -> int:
    """Clamp ticket count to 0..max; returns 0 when feature disabled."""
    settings = get_world_ticket_settings(config)
    if not settings.enabled:
        return 0
    try:
        count = int(raw)
    except (TypeError, ValueError):
        return 0
    if count < 0:
        return 0
    return min(count, settings.max_count)


def build_world_ticket_give_command(login: str, count: int) -> str | None:
    """Return RCON give for Paper MCC-Tickets, or None if count < 1."""
    name = (login or "").strip()
    n = int(count or 0)
    if not name or n < 1:
        return None
    return f"give {name} paper[{_PAPER_COMPONENTS}] {n}"


def resolve_waitlist_cyclist(
    account_name: str,
    *,
    account_type: str,
) -> Optional[Cyclist]:
    """Cyclist linked to an ASSIGNED waitlist entry for this slot, if any."""
    name = (account_name or "").strip()
    if not name:
        return None
    if account_type == MinecraftSessionWaitlistEntry.QUEUE_PLAYER:
        entry = (
            MinecraftSessionWaitlistEntry.objects.filter(
                queue_type=MinecraftSessionWaitlistEntry.QUEUE_PLAYER,
                status=MinecraftSessionWaitlistEntry.STATUS_ASSIGNED,
                assigned_play_account__short_name__iexact=name,
            )
            .select_related("cyclist")
            .order_by("queued_at")
            .first()
        )
    else:
        entry = (
            MinecraftSessionWaitlistEntry.objects.filter(
                queue_type=MinecraftSessionWaitlistEntry.QUEUE_BUILDER,
                status=MinecraftSessionWaitlistEntry.STATUS_ASSIGNED,
                assigned_builder_registration__mc_username__iexact=name,
            )
            .select_related("cyclist")
            .order_by("queued_at")
            .first()
        )
    if entry is None:
        return None
    return entry.cyclist


def debit_world_tickets_for_cyclist(
    cyclist: Cyclist,
    ticket_count: int,
    *,
    user: AbstractBaseUser | None = None,
    config: MinecraftIntegrationConfig | None = None,
) -> RedemptionResult:
    """
    Deduct ticket_count × world_ticket_velos from the cyclist balance.

    Flyer / manual starts (no cyclist) skip this; call only when a Radler is linked.
    """
    settings = get_world_ticket_settings(config)
    count = int(ticket_count or 0)
    if count < 1:
        return RedemptionResult(success=True, message="", velos_redeemed=0)

    amount = count * settings.velos_per_ticket
    note = _("MCC-Welt-Tickets: %(count)s × %(price)s Velos") % {
        "count": count,
        "price": settings.velos_per_ticket,
    }
    return redeem_cyclist_velos(
        cyclist,
        redeemed_by=user if getattr(user, "is_authenticated", False) else None,
        note=str(note),
        amount=amount,
    )


def ticket_cost_velos(
    ticket_count: int,
    *,
    config: MinecraftIntegrationConfig | None = None,
) -> int:
    settings = get_world_ticket_settings(config)
    return max(0, int(ticket_count or 0)) * settings.velos_per_ticket
