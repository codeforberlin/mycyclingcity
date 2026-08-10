# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Stations (physical PCs) and Microsoft login allowlist.

from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from minecraft.models import (
    MCSession,
    MinecraftMsAllowlistEntry,
    MinecraftPlayAccount,
    MinecraftStation,
)


class StationAdminError(Exception):
    code = "station_error"

    def __init__(self, message: str, *, code: str | None = None):
        super().__init__(message)
        if code:
            self.code = code


@dataclass
class StationDTO:
    pk: int
    name: str
    location: str
    role: str
    role_label: str
    is_active: bool
    sort_order: int
    note: str
    default_play_account_id: int | None
    default_play_account_name: str
    active_session_account: str
    active_session_ms: str


def list_stations(*, include_inactive: bool = False) -> list[MinecraftStation]:
    qs = MinecraftStation.objects.select_related("default_play_account").order_by(
        "sort_order", "name"
    )
    if not include_inactive:
        qs = qs.filter(is_active=True)
    return list(qs)


def list_station_dtos(*, include_inactive: bool = False) -> list[StationDTO]:
    stations = list_stations(include_inactive=include_inactive)
    active_by_station: dict[int, MCSession] = {}
    for session in MCSession.objects.filter(
        status=MCSession.STATUS_ACTIVE,
        station_id__isnull=False,
    ).select_related("station"):
        active_by_station[session.station_id] = session

    role_labels = dict(MinecraftStation.ROLE_CHOICES)
    result: list[StationDTO] = []
    for station in stations:
        active = active_by_station.get(station.pk)
        play = station.default_play_account
        result.append(
            StationDTO(
                pk=station.pk,
                name=station.name,
                location=station.location or "",
                role=station.role,
                role_label=str(role_labels.get(station.role, station.role)),
                is_active=station.is_active,
                sort_order=station.sort_order,
                note=station.note or "",
                default_play_account_id=play.pk if play else None,
                default_play_account_name=play.short_name if play else "",
                active_session_account=active.account_name if active else "",
                active_session_ms=(active.ms_username or "") if active else "",
            )
        )
    return result


def get_station(station_id: int | str | None) -> MinecraftStation | None:
    if station_id in (None, ""):
        return None
    try:
        pk = int(station_id)
    except (TypeError, ValueError):
        return None
    return MinecraftStation.objects.filter(pk=pk).first()


def stations_for_role(role: str, *, only_free: bool = False) -> list[MinecraftStation]:
    """Return active stations that support play or builder sessions."""
    if role == "play":
        roles = [MinecraftStation.ROLE_PLAY, MinecraftStation.ROLE_BOTH]
    elif role == "builder":
        roles = [MinecraftStation.ROLE_BUILDER, MinecraftStation.ROLE_BOTH]
    else:
        roles = [MinecraftStation.ROLE_PLAY, MinecraftStation.ROLE_BUILDER, MinecraftStation.ROLE_BOTH]

    stations = list(
        MinecraftStation.objects.filter(is_active=True, role__in=roles).order_by(
            "sort_order", "name"
        )
    )
    if not only_free:
        return stations
    busy_ids = set(
        MCSession.objects.filter(
            status=MCSession.STATUS_ACTIVE,
            station_id__isnull=False,
        ).values_list("station_id", flat=True)
    )
    return [s for s in stations if s.pk not in busy_ids]


def resolve_station_for_session(
    station_id: int | str | None,
    *,
    role: str,
) -> MinecraftStation | None:
    station = get_station(station_id)
    if station is None:
        if station_id not in (None, ""):
            raise StationAdminError(
                _("Station nicht gefunden."),
                code="station_not_found",
            )
        return None
    if not station.is_active:
        raise StationAdminError(_("Station ist inaktiv."), code="station_inactive")
    if role == "play" and not station.supports_play():
        raise StationAdminError(
            _("Station unterstützt keine Spiel-Sessions."),
            code="station_role",
        )
    if role == "builder" and not station.supports_builder():
        raise StationAdminError(
            _("Station unterstützt keine Bau-Sessions."),
            code="station_role",
        )
    busy = MCSession.objects.filter(
        status=MCSession.STATUS_ACTIVE,
        station=station,
    ).exists()
    if busy:
        raise StationAdminError(
            _("Station %(name)s hat bereits eine aktive Session.") % {"name": station.name},
            code="station_busy",
        )
    return station


@transaction.atomic
def create_station(data: dict, *, user=None) -> MinecraftStation:
    name = (data.get("name") or "").strip()
    if not name:
        raise StationAdminError(_("Name ist erforderlich."), code="invalid_name")
    if MinecraftStation.objects.filter(name__iexact=name).exists():
        raise StationAdminError(
            _("Station %(name)s existiert bereits.") % {"name": name},
            code="duplicate_name",
        )
    role = (data.get("role") or MinecraftStation.ROLE_BOTH).strip()
    if role not in dict(MinecraftStation.ROLE_CHOICES):
        role = MinecraftStation.ROLE_BOTH
    play_id = data.get("default_play_account_id") or None
    play = None
    if play_id:
        play = MinecraftPlayAccount.objects.filter(pk=int(play_id)).first()
    try:
        sort_order = int(data.get("sort_order") or 0)
    except (TypeError, ValueError):
        sort_order = 0
    return MinecraftStation.objects.create(
        name=name,
        location=(data.get("location") or "").strip(),
        role=role,
        is_active=bool(data.get("is_active", True)),
        sort_order=sort_order,
        default_play_account=play,
        note=(data.get("note") or "").strip(),
    )


@transaction.atomic
def update_station(station: MinecraftStation, data: dict) -> MinecraftStation:
    name = (data.get("name") or station.name).strip()
    if not name:
        raise StationAdminError(_("Name ist erforderlich."), code="invalid_name")
    if (
        MinecraftStation.objects.filter(name__iexact=name)
        .exclude(pk=station.pk)
        .exists()
    ):
        raise StationAdminError(
            _("Station %(name)s existiert bereits.") % {"name": name},
            code="duplicate_name",
        )
    role = (data.get("role") or station.role).strip()
    if role not in dict(MinecraftStation.ROLE_CHOICES):
        role = station.role
    play_id = data.get("default_play_account_id")
    if play_id in ("", None):
        play = None
    else:
        play = MinecraftPlayAccount.objects.filter(pk=int(play_id)).first()
    try:
        sort_order = int(data.get("sort_order") if data.get("sort_order") not in (None, "") else station.sort_order)
    except (TypeError, ValueError):
        sort_order = station.sort_order
    station.name = name
    station.location = (data.get("location") if "location" in data else station.location) or ""
    station.location = station.location.strip()
    station.role = role
    if "is_active" in data:
        station.is_active = bool(data.get("is_active"))
    station.sort_order = sort_order
    station.default_play_account = play
    if "note" in data:
        station.note = (data.get("note") or "").strip()
    station.save()
    return station


@transaction.atomic
def delete_station(station: MinecraftStation) -> None:
    if MCSession.objects.filter(status=MCSession.STATUS_ACTIVE, station=station).exists():
        raise StationAdminError(
            _("Station hat eine aktive Session und kann nicht gelöscht werden."),
            code="station_busy",
        )
    station.delete()


def list_allowlist_entries(*, station_id: int | None = None) -> list[MinecraftMsAllowlistEntry]:
    qs = MinecraftMsAllowlistEntry.objects.select_related("station", "created_by").order_by(
        "ms_username", "station_id"
    )
    if station_id is not None:
        qs = qs.filter(Q(station_id=station_id) | Q(station__isnull=True))
    return list(qs)


def allowlist_is_enforced() -> bool:
    """When no active entries exist, freigabe is not blocked (pre-seed / empty DB)."""
    return MinecraftMsAllowlistEntry.objects.filter(is_active=True).exists()


def list_allowed_ms_usernames(*, station: MinecraftStation | None = None) -> list[str]:
    qs = MinecraftMsAllowlistEntry.objects.filter(is_active=True)
    if station is not None:
        qs = qs.filter(Q(station__isnull=True) | Q(station=station))
    names = sorted(
        {(e.ms_username or "").strip() for e in qs if (e.ms_username or "").strip()},
        key=str.lower,
    )
    return names


def is_ms_login_allowed(
    ms_username: str,
    *,
    station: MinecraftStation | None = None,
) -> bool:
    login = (ms_username or "").strip()
    if not login:
        return False
    if not allowlist_is_enforced():
        return True
    qs = MinecraftMsAllowlistEntry.objects.filter(is_active=True, ms_username__iexact=login)
    if station is not None:
        qs = qs.filter(Q(station__isnull=True) | Q(station=station))
    return qs.exists()


def assert_ms_login_allowed(
    ms_username: str,
    *,
    station: MinecraftStation | None = None,
) -> str:
    login = (ms_username or "").strip()
    if not login:
        raise StationAdminError(
            _("Microsoft-Login ist erforderlich."),
            code="ms_required",
        )
    if not is_ms_login_allowed(login, station=station):
        raise StationAdminError(
            _("Microsoft-Login %(name)s steht nicht auf der Allowlist.") % {"name": login},
            code="ms_not_allowed",
        )
    return login


@transaction.atomic
def add_allowlist_entry(
    *,
    ms_username: str,
    station_id: int | str | None = None,
    note: str = "",
    user=None,
) -> MinecraftMsAllowlistEntry:
    login = (ms_username or "").strip()
    if not login:
        raise StationAdminError(_("Microsoft-Login ist erforderlich."), code="ms_required")
    station = get_station(station_id)
    if station_id not in (None, "") and station is None:
        raise StationAdminError(_("Station nicht gefunden."), code="station_not_found")
    existing = MinecraftMsAllowlistEntry.objects.filter(ms_username__iexact=login)
    if station is None:
        existing = existing.filter(station__isnull=True)
    else:
        existing = existing.filter(station=station)
    if existing.exists():
        raise StationAdminError(
            _("Allowlist-Eintrag für %(name)s existiert bereits.") % {"name": login},
            code="duplicate_allowlist",
        )
    return MinecraftMsAllowlistEntry.objects.create(
        ms_username=login,
        station=station,
        note=(note or "").strip(),
        is_active=True,
        created_by=user if getattr(user, "is_authenticated", False) else None,
    )


@transaction.atomic
def set_allowlist_active(entry_id: int, *, is_active: bool) -> MinecraftMsAllowlistEntry:
    entry = MinecraftMsAllowlistEntry.objects.filter(pk=entry_id).first()
    if entry is None:
        raise StationAdminError(_("Allowlist-Eintrag nicht gefunden."), code="not_found")
    entry.is_active = bool(is_active)
    entry.save(update_fields=["is_active"])
    return entry


@transaction.atomic
def delete_allowlist_entry(entry_id: int) -> None:
    deleted, _ = MinecraftMsAllowlistEntry.objects.filter(pk=entry_id).delete()
    if not deleted:
        raise StationAdminError(_("Allowlist-Eintrag nicht gefunden."), code="not_found")
