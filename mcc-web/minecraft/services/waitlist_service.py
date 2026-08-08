# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    waitlist_service.py
# @note    Operator waitlist for Minecraft play/builder sessions (Phase 1).

from __future__ import annotations

import secrets
from typing import Any

from django.contrib.auth.models import AbstractBaseUser
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from config.logger_utils import get_logger
from minecraft.models import (
    MCSession,
    MinecraftIntegrationConfig,
    MinecraftPlayAccount,
    MinecraftSessionWaitlistEntry,
    MinecraftTeamRegistration,
)
from minecraft.services.session_control import (
    get_active_session,
)
from minecraft.services.team_registration import active_registrations

logger = get_logger("minecraft")

ACTIVE_WAITLIST_STATUSES = (
    MinecraftSessionWaitlistEntry.STATUS_WAITING,
    MinecraftSessionWaitlistEntry.STATUS_ASSIGNED,
    MinecraftSessionWaitlistEntry.STATUS_ACTIVE,
)


class WaitlistError(Exception):
    code = "waitlist_error"

    def __init__(self, message: str, *, code: str | None = None):
        super().__init__(message)
        if code:
            self.code = code


def ensure_waitlist_public_token(config: MinecraftIntegrationConfig) -> str:
    token = (config.waitlist_public_token or "").strip()
    if token:
        return token
    token = secrets.token_urlsafe(24)
    config.waitlist_public_token = token
    config.save(update_fields=["waitlist_public_token"])
    return token


def get_integration_config() -> MinecraftIntegrationConfig:
    config = MinecraftIntegrationConfig.get_config()
    ensure_waitlist_public_token(config)
    return config


def duration_from_velos(velos: int, *, config: MinecraftIntegrationConfig | None = None) -> int:
    cfg = config or get_integration_config()
    rate = max(1, int(cfg.player_velos_per_minute or 20))
    minutes = int(velos) // rate
    return max(1, minutes)


def validate_player_velos(velos: int, *, config: MinecraftIntegrationConfig | None = None) -> None:
    cfg = config or get_integration_config()
    minimum = int(cfg.player_min_velos or 300)
    if int(velos) < minimum:
        raise WaitlistError(
            _("Mindestens %(min)s Velos erforderlich.") % {"min": minimum},
            code="velos_too_low",
        )


def normalize_ticket_number(value: str) -> str:
    return (value or "").strip().lstrip("#")


def ticket_number_in_use(ticket_number: str, *, exclude_pk: int | None = None) -> bool:
    qs = MinecraftSessionWaitlistEntry.objects.filter(
        ticket_number__iexact=ticket_number,
        status__in=ACTIVE_WAITLIST_STATUSES,
    )
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    return qs.exists()


def generate_ticket_number(*, exclude: set[str] | None = None) -> str:
    """Return a free 4-digit ticket number (1000–9999)."""
    blocked = {normalize_ticket_number(x) for x in (exclude or set()) if x}
    for _ in range(80):
        candidate = f"{secrets.randbelow(9000) + 1000}"
        if candidate in blocked:
            continue
        if not ticket_number_in_use(candidate):
            return candidate
    raise WaitlistError(_("Keine freie Ticket-Nummer gefunden."), code="ticket_exhausted")


def generate_ticket_numbers(count: int = 1) -> list[str]:
    """Generate ``count`` distinct free ticket numbers for flyer prep."""
    n = max(1, min(int(count), 50))
    tickets: list[str] = []
    used: set[str] = set()
    for _ in range(n):
        ticket = generate_ticket_number(exclude=used)
        used.add(ticket)
        tickets.append(ticket)
    return tickets


@transaction.atomic
def add_waitlist_entry(
    *,
    queue_type: str,
    ticket_number: str = "",
    guest_label: str = "",
    velos_cost: int = 0,
    duration_minutes: int | None = None,
    internal_note: str = "",
    user: AbstractBaseUser | None = None,
) -> MinecraftSessionWaitlistEntry:
    ticket = normalize_ticket_number(ticket_number) or generate_ticket_number()
    if ticket_number_in_use(ticket):
        raise WaitlistError(
            _("Ticket-Nummer %(ticket)s ist bereits in der Warteliste aktiv.")
            % {"ticket": ticket},
            code="ticket_duplicate",
        )

    if queue_type == MinecraftSessionWaitlistEntry.QUEUE_PLAYER:
        validate_player_velos(velos_cost)
        minutes = duration_minutes or duration_from_velos(velos_cost)
    else:
        minutes = duration_minutes or int(getattr(settings, "MCC_MINECRAFT_BUILDER_SESSION_MINUTES", 90))

    if minutes < 1:
        raise WaitlistError(_("Session-Dauer muss mindestens 1 Minute sein."), code="invalid_duration")

    entry = MinecraftSessionWaitlistEntry.objects.create(
        queue_type=queue_type,
        ticket_number=ticket,
        guest_label=(guest_label or "").strip(),
        velos_cost=int(velos_cost or 0),
        duration_minutes=int(minutes),
        internal_note=(internal_note or "").strip(),
        queued_by=user if getattr(user, "is_authenticated", False) else None,
    )
    logger.info(
        "[waitlist] added entry id=%s type=%s ticket=%s minutes=%s",
        entry.pk,
        queue_type,
        ticket,
        minutes,
    )
    return entry


def waiting_entries(queue_type: str) -> list[MinecraftSessionWaitlistEntry]:
    return list(
        MinecraftSessionWaitlistEntry.objects.filter(
            queue_type=queue_type,
            status=MinecraftSessionWaitlistEntry.STATUS_WAITING,
        ).order_by("queued_at")
    )


def _play_account_reserved(account: MinecraftPlayAccount) -> bool:
    return MinecraftSessionWaitlistEntry.objects.filter(
        assigned_play_account=account,
        status=MinecraftSessionWaitlistEntry.STATUS_ASSIGNED,
    ).exists()


def _builder_reserved(registration: MinecraftTeamRegistration) -> bool:
    return MinecraftSessionWaitlistEntry.objects.filter(
        assigned_builder_registration=registration,
        status=MinecraftSessionWaitlistEntry.STATUS_ASSIGNED,
    ).exists()


def _play_account_busy(account: MinecraftPlayAccount) -> bool:
    return get_active_session(account.short_name) is not None or _play_account_reserved(account)


def _builder_busy(registration: MinecraftTeamRegistration) -> bool:
    return get_active_session(registration.mc_username) is not None or _builder_reserved(
        registration
    )


def free_play_accounts() -> list[MinecraftPlayAccount]:
    accounts = list(
        MinecraftPlayAccount.objects.filter(is_active=True).order_by("sort_order", "short_name")
    )
    return [a for a in accounts if not _play_account_busy(a)]


def free_builder_registrations() -> list[MinecraftTeamRegistration]:
    registrations = list(active_registrations())
    return [r for r in registrations if not _builder_busy(r)]


def get_assigned_player_entry(account_name: str) -> MinecraftSessionWaitlistEntry | None:
    return (
        MinecraftSessionWaitlistEntry.objects.filter(
            queue_type=MinecraftSessionWaitlistEntry.QUEUE_PLAYER,
            status=MinecraftSessionWaitlistEntry.STATUS_ASSIGNED,
            assigned_play_account__short_name__iexact=account_name,
        )
        .select_related("assigned_play_account")
        .order_by("queued_at")
        .first()
    )


def get_assigned_builder_entry(team_name: str) -> MinecraftSessionWaitlistEntry | None:
    return (
        MinecraftSessionWaitlistEntry.objects.filter(
            queue_type=MinecraftSessionWaitlistEntry.QUEUE_BUILDER,
            status=MinecraftSessionWaitlistEntry.STATUS_ASSIGNED,
            assigned_builder_registration__mc_username__iexact=team_name,
        )
        .select_related("assigned_builder_registration", "assigned_builder_registration__group")
        .order_by("queued_at")
        .first()
    )


def _slot_label_for_play(account: MinecraftPlayAccount, index: int) -> str:
    return account.display_name or account.short_name or f"PC {index + 1}"


def _slot_label_for_builder(registration: MinecraftTeamRegistration) -> str:
    if registration.group_id:
        return registration.group.name
    return registration.mc_username


@transaction.atomic
def cancel_waitlist_entry(entry_id: int) -> MinecraftSessionWaitlistEntry:
    entry = MinecraftSessionWaitlistEntry.objects.select_for_update().get(pk=entry_id)
    if entry.status not in (
        MinecraftSessionWaitlistEntry.STATUS_WAITING,
        MinecraftSessionWaitlistEntry.STATUS_ASSIGNED,
    ):
        raise WaitlistError(
            _("Nur wartende oder zugewiesene Einträge können abgebrochen werden."),
            code="invalid_status",
        )
    entry.status = MinecraftSessionWaitlistEntry.STATUS_CANCELLED
    entry.finished_at = timezone.now()
    entry.assigned_play_account = None
    entry.assigned_builder_registration = None
    entry.save(
        update_fields=[
            "status",
            "finished_at",
            "assigned_play_account",
            "assigned_builder_registration",
        ]
    )
    return entry


@transaction.atomic
def unassign_waitlist_entry(entry_id: int) -> MinecraftSessionWaitlistEntry:
    entry = MinecraftSessionWaitlistEntry.objects.select_for_update().get(pk=entry_id)
    if entry.status != MinecraftSessionWaitlistEntry.STATUS_ASSIGNED:
        raise WaitlistError(_("Nur zugewiesene Einträge können freigegeben werden."), code="invalid_status")
    entry.status = MinecraftSessionWaitlistEntry.STATUS_WAITING
    entry.assigned_play_account = None
    entry.assigned_builder_registration = None
    entry.save(
        update_fields=["status", "assigned_play_account", "assigned_builder_registration"]
    )
    return entry


@transaction.atomic
def assign_player_from_waitlist(
    entry_id: int,
    play_account_name: str,
    *,
    user: AbstractBaseUser | None = None,
) -> MinecraftSessionWaitlistEntry:
    """Reserve a play account for a waiting guest. Does not start RCON/session."""
    entry = MinecraftSessionWaitlistEntry.objects.select_for_update().get(pk=entry_id)
    if entry.queue_type != MinecraftSessionWaitlistEntry.QUEUE_PLAYER:
        raise WaitlistError(_("Falscher Wartelisten-Typ."), code="wrong_queue")
    if entry.status != MinecraftSessionWaitlistEntry.STATUS_WAITING:
        raise WaitlistError(_("Eintrag ist nicht mehr wartend."), code="invalid_status")

    account = (
        MinecraftPlayAccount.objects.filter(is_active=True, short_name__iexact=play_account_name).first()
    )
    if account is None:
        raise WaitlistError(_("Spiel-Account nicht gefunden."), code="account_not_found")
    if _play_account_busy(account):
        raise WaitlistError(_("Spiel-Account ist belegt."), code="account_busy")

    entry.status = MinecraftSessionWaitlistEntry.STATUS_ASSIGNED
    entry.assigned_play_account = account
    entry.save(update_fields=["status", "assigned_play_account"])
    logger.info(
        "[waitlist] assigned player entry id=%s ticket=%s account=%s by=%s",
        entry.pk,
        entry.ticket_number,
        account.short_name,
        getattr(user, "username", None),
    )
    return entry


@transaction.atomic
def assign_builder_from_waitlist(
    entry_id: int,
    team_name: str,
    *,
    user: AbstractBaseUser | None = None,
) -> MinecraftSessionWaitlistEntry:
    """Reserve a builder account for a waiting guest. Does not start RCON/session."""
    entry = MinecraftSessionWaitlistEntry.objects.select_for_update().get(pk=entry_id)
    if entry.queue_type != MinecraftSessionWaitlistEntry.QUEUE_BUILDER:
        raise WaitlistError(_("Falscher Wartelisten-Typ."), code="wrong_queue")
    if entry.status != MinecraftSessionWaitlistEntry.STATUS_WAITING:
        raise WaitlistError(_("Eintrag ist nicht mehr wartend."), code="invalid_status")

    registration = active_registrations().filter(mc_username__iexact=team_name).first()
    if registration is None:
        raise WaitlistError(_("Bau-PC nicht gefunden."), code="account_not_found")
    if _builder_busy(registration):
        raise WaitlistError(_("Bau-PC ist belegt."), code="account_busy")

    entry.status = MinecraftSessionWaitlistEntry.STATUS_ASSIGNED
    entry.assigned_builder_registration = registration
    entry.save(update_fields=["status", "assigned_builder_registration"])
    logger.info(
        "[waitlist] assigned builder entry id=%s ticket=%s team=%s by=%s",
        entry.pk,
        entry.ticket_number,
        registration.mc_username,
        getattr(user, "username", None),
    )
    return entry


@transaction.atomic
def activate_waitlist_for_session(
    session: MCSession,
    *,
    user: AbstractBaseUser | None = None,
) -> MinecraftSessionWaitlistEntry | None:
    """
    When a session starts from Spieler-/Bau-Sessions, bind any reserved waitlist row.
    """
    if session.account_type == MCSession.ACCOUNT_PLAYER:
        entry = (
            MinecraftSessionWaitlistEntry.objects.select_for_update()
            .filter(
                queue_type=MinecraftSessionWaitlistEntry.QUEUE_PLAYER,
                status=MinecraftSessionWaitlistEntry.STATUS_ASSIGNED,
                assigned_play_account__short_name__iexact=session.account_name,
            )
            .order_by("queued_at")
            .first()
        )
    elif session.account_type == MCSession.ACCOUNT_BUILDER:
        entry = (
            MinecraftSessionWaitlistEntry.objects.select_for_update()
            .filter(
                queue_type=MinecraftSessionWaitlistEntry.QUEUE_BUILDER,
                status=MinecraftSessionWaitlistEntry.STATUS_ASSIGNED,
                assigned_builder_registration__mc_username__iexact=session.account_name,
            )
            .order_by("queued_at")
            .first()
        )
    else:
        entry = None

    if entry is None:
        return None

    now = timezone.now()
    entry.status = MinecraftSessionWaitlistEntry.STATUS_ACTIVE
    entry.mc_session = session
    entry.started_at = now
    entry.started_by = user if getattr(user, "is_authenticated", False) else None
    entry.save(update_fields=["status", "mc_session", "started_at", "started_by"])
    logger.info(
        "[waitlist] activated entry id=%s ticket=%s session=%s",
        entry.pk,
        entry.ticket_number,
        session.account_name,
    )
    return entry


# Backward-compatible aliases (assignment only — no RCON)
start_player_from_waitlist = assign_player_from_waitlist
start_builder_from_waitlist = assign_builder_from_waitlist


def complete_waitlist_for_session(session: MCSession) -> None:
    entries = MinecraftSessionWaitlistEntry.objects.filter(
        mc_session=session,
        status=MinecraftSessionWaitlistEntry.STATUS_ACTIVE,
    )
    now = timezone.now()
    for entry in entries:
        entry.status = MinecraftSessionWaitlistEntry.STATUS_DONE
        entry.finished_at = now
        entry.save(update_fields=["status", "finished_at"])


def sync_orphaned_active_entries() -> int:
    """Mark active waitlist rows done when their MC session is no longer active."""
    updated = 0
    for entry in MinecraftSessionWaitlistEntry.objects.filter(
        status=MinecraftSessionWaitlistEntry.STATUS_ACTIVE
    ).select_related("mc_session"):
        session = entry.mc_session
        if session is None or session.status != MCSession.STATUS_ACTIVE:
            entry.status = MinecraftSessionWaitlistEntry.STATUS_DONE
            entry.finished_at = timezone.now()
            entry.save(update_fields=["status", "finished_at"])
            updated += 1
    return updated


def _queue_position(entry: MinecraftSessionWaitlistEntry) -> int:
    if entry.status != MinecraftSessionWaitlistEntry.STATUS_WAITING:
        return 0
    return (
        MinecraftSessionWaitlistEntry.objects.filter(
            queue_type=entry.queue_type,
            status=MinecraftSessionWaitlistEntry.STATUS_WAITING,
            queued_at__lte=entry.queued_at,
        ).count()
    )


def _build_player_slots(*, include_names: bool) -> list[dict[str, Any]]:
    accounts = list(
        MinecraftPlayAccount.objects.filter(is_active=True).order_by("sort_order", "short_name")
    )
    slots = []
    for index, account in enumerate(accounts):
        session_busy = get_active_session(account.short_name) is not None
        active_entry = (
            MinecraftSessionWaitlistEntry.objects.filter(
                assigned_play_account=account,
                status=MinecraftSessionWaitlistEntry.STATUS_ACTIVE,
            )
            .order_by("-started_at")
            .first()
        )
        assigned_entry = (
            None
            if active_entry
            else MinecraftSessionWaitlistEntry.objects.filter(
                assigned_play_account=account,
                status=MinecraftSessionWaitlistEntry.STATUS_ASSIGNED,
            )
            .order_by("queued_at")
            .first()
        )
        if session_busy or active_entry:
            status = "busy"
            ticket = active_entry.ticket_number if active_entry else ""
        elif assigned_entry:
            status = "assigned"
            ticket = assigned_entry.ticket_number
        else:
            status = "free"
            ticket = ""
        slot: dict[str, Any] = {
            "slot_id": account.short_name,
            "label": _slot_label_for_play(account, index),
            "status": status,
            "ticket_number": ticket,
        }
        if include_names:
            slot["account_name"] = account.short_name
            slot["display_name"] = account.label
            if assigned_entry:
                slot["guest_label"] = assigned_entry.guest_label
        slots.append(slot)
    return slots


def _build_builder_slots(*, include_names: bool) -> list[dict[str, Any]]:
    registrations = list(active_registrations())
    slots = []
    for registration in registrations:
        session_busy = get_active_session(registration.mc_username) is not None
        active_entry = (
            MinecraftSessionWaitlistEntry.objects.filter(
                assigned_builder_registration=registration,
                status=MinecraftSessionWaitlistEntry.STATUS_ACTIVE,
            )
            .order_by("-started_at")
            .first()
        )
        assigned_entry = (
            None
            if active_entry
            else MinecraftSessionWaitlistEntry.objects.filter(
                assigned_builder_registration=registration,
                status=MinecraftSessionWaitlistEntry.STATUS_ASSIGNED,
            )
            .order_by("queued_at")
            .first()
        )
        if session_busy or active_entry:
            status = "busy"
            ticket = active_entry.ticket_number if active_entry else ""
        elif assigned_entry:
            status = "assigned"
            ticket = assigned_entry.ticket_number
        else:
            status = "free"
            ticket = ""
        slot: dict[str, Any] = {
            "slot_id": registration.mc_username,
            "label": _slot_label_for_builder(registration),
            "status": status,
            "ticket_number": ticket,
        }
        if include_names:
            slot["team_name"] = registration.mc_username
            slot["group_name"] = registration.group.name if registration.group_id else ""
            if assigned_entry:
                slot["guest_label"] = assigned_entry.guest_label
        slots.append(slot)
    return slots


def _serialize_queue_entry(
    entry: MinecraftSessionWaitlistEntry,
    *,
    include_private: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": entry.pk,
        "ticket_number": entry.ticket_number,
        "status": entry.status,
        "position": _queue_position(entry) if entry.status == entry.STATUS_WAITING else 0,
        "duration_minutes": entry.duration_minutes,
        "queued_at": entry.queued_at.isoformat(),
    }
    if entry.status in (entry.STATUS_ACTIVE, entry.STATUS_ASSIGNED):
        if entry.assigned_play_account_id:
            payload["slot_id"] = entry.assigned_play_account.short_name
            payload["slot_label"] = entry.assigned_play_account.label
        elif entry.assigned_builder_registration_id:
            payload["slot_id"] = entry.assigned_builder_registration.mc_username
            payload["slot_label"] = _slot_label_for_builder(entry.assigned_builder_registration)
    if include_private:
        payload.update(
            {
                "guest_label": entry.guest_label,
                "velos_cost": entry.velos_cost,
                "internal_note": entry.internal_note,
                "started_at": entry.started_at.isoformat() if entry.started_at else None,
            }
        )
    return payload


def build_display_payload(*, include_private: bool = False) -> dict[str, Any]:
    sync_orphaned_active_entries()
    config = get_integration_config()

    player_waiting = waiting_entries(MinecraftSessionWaitlistEntry.QUEUE_PLAYER)
    builder_waiting = waiting_entries(MinecraftSessionWaitlistEntry.QUEUE_BUILDER)
    player_assigned = list(
        MinecraftSessionWaitlistEntry.objects.filter(
            queue_type=MinecraftSessionWaitlistEntry.QUEUE_PLAYER,
            status=MinecraftSessionWaitlistEntry.STATUS_ASSIGNED,
        ).order_by("queued_at")
    )
    builder_assigned = list(
        MinecraftSessionWaitlistEntry.objects.filter(
            queue_type=MinecraftSessionWaitlistEntry.QUEUE_BUILDER,
            status=MinecraftSessionWaitlistEntry.STATUS_ASSIGNED,
        ).order_by("queued_at")
    )
    player_active = list(
        MinecraftSessionWaitlistEntry.objects.filter(
            queue_type=MinecraftSessionWaitlistEntry.QUEUE_PLAYER,
            status=MinecraftSessionWaitlistEntry.STATUS_ACTIVE,
        ).order_by("started_at")
    )
    builder_active = list(
        MinecraftSessionWaitlistEntry.objects.filter(
            queue_type=MinecraftSessionWaitlistEntry.QUEUE_BUILDER,
            status=MinecraftSessionWaitlistEntry.STATUS_ACTIVE,
        ).order_by("started_at")
    )

    return {
        "server_time": timezone.now().isoformat(),
        "public_enabled": config.waitlist_public_enabled,
        "player_velos_per_minute": config.player_velos_per_minute,
        "player_min_velos": config.player_min_velos,
        "player_queue": [
            _serialize_queue_entry(e, include_private=include_private) for e in player_waiting
        ],
        "builder_queue": [
            _serialize_queue_entry(e, include_private=include_private) for e in builder_waiting
        ],
        "player_assigned": [
            _serialize_queue_entry(e, include_private=include_private) for e in player_assigned
        ],
        "builder_assigned": [
            _serialize_queue_entry(e, include_private=include_private) for e in builder_assigned
        ],
        "player_active": [
            _serialize_queue_entry(e, include_private=include_private) for e in player_active
        ],
        "builder_active": [
            _serialize_queue_entry(e, include_private=include_private) for e in builder_active
        ],
        "player_slots": _build_player_slots(include_names=include_private),
        "builder_slots": _build_builder_slots(include_names=include_private),
    }
