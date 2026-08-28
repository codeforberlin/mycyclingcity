# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    account_admin.py
# @note    Unified DTO facade over MinecraftPlayAccount and MinecraftTeamRegistration.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from django.db.models import Prefetch, Q

from api.models import Group
from minecraft.models import (
    MCSession,
    MinecraftPlayAccount,
    MinecraftProtectedRegion,
    MinecraftTeamRegistration,
)
from minecraft.services.vanilla_op import VanillaOperator, list_operators


ACCOUNT_PLAYER = "PLAYER"
ACCOUNT_BUILDER = "BUILDER"


@dataclass
class AccountDTO:
    account_type: str
    pk: int
    label: str
    login_key: str
    id_tag: str = ""
    display_name: str = ""
    ms_username: str = ""
    ms_uuid: str = ""
    is_active: bool = True
    session_duration_minutes: int | None = None
    add_time_minutes: int | None = None
    session_unlimited: bool = False
    prefer_gamemode: str = ""
    prefer_spectator: bool = False
    group_id: int | None = None
    group_name: str = ""
    top_group_id: int | None = None
    top_group_name: str = ""
    region_names: list[str] = field(default_factory=list)
    authme_is_registered: bool = False
    last_sync_error: str = ""
    is_vanilla_op: bool = False
    op_lookup_name: str = ""
    active_session_id: str = ""
    sort_key: str = ""

    @property
    def ref(self) -> str:
        return f"{self.account_type}:{self.pk}"


def top_group_for(group: Group | None) -> Group | None:
    """Walk parent chain to the TOP group (parent is None)."""
    if group is None:
        return None
    visited: set[int] = set()
    current = group
    while current is not None and current.parent_id and current.id not in visited:
        visited.add(current.id)
        current = current.parent
    return current


def list_top_groups() -> list[Group]:
    return list(Group.objects.filter(parent__isnull=True).order_by("name"))


def _op_lookup_candidates(*names: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in names:
        name = (raw or "").strip()
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(name)
    return out


def _match_op(candidates: Iterable[str], ops: list[VanillaOperator]) -> tuple[bool, str]:
    op_keys = {o.name_key: o.name for o in ops}
    for name in candidates:
        key = name.lower()
        if key in op_keys:
            return True, op_keys[key]
    primary = next(iter(candidates), "")
    return False, primary


def _active_sessions_by_account() -> dict[tuple[str, str], str]:
    rows = MCSession.objects.filter(status=MCSession.STATUS_ACTIVE).values_list(
        "account_type", "account_name", "session_id"
    )
    return {(atype, aname): str(sid) for atype, aname, sid in rows}


def play_account_to_dto(
    account: MinecraftPlayAccount,
    *,
    ops: list[VanillaOperator] | None = None,
    sessions: dict[tuple[str, str], str] | None = None,
) -> AccountDTO:
    ops = ops if ops is not None else []
    sessions = sessions if sessions is not None else {}
    candidates = _op_lookup_candidates(account.ms_username, account.short_name)
    is_op, op_name = _match_op(candidates, ops)
    top = account.assigned_to_group
    if top is not None and top.parent_id:
        top = top_group_for(top)
    return AccountDTO(
        account_type=ACCOUNT_PLAYER,
        pk=account.pk,
        label=account.label,
        login_key=account.short_name,
        id_tag=account.id_tag or "",
        display_name=(account.display_name or "").strip(),
        ms_username=(account.ms_username or "").strip(),
        ms_uuid=(account.ms_uuid or "").strip(),
        is_active=bool(account.is_active),
        session_duration_minutes=account.session_duration_minutes,
        add_time_minutes=account.add_time_minutes,
        session_unlimited=bool(account.session_unlimited),
        prefer_gamemode=(account.prefer_gamemode or "").strip(),
        prefer_spectator=bool(account.prefer_spectator),
        group_id=None,
        group_name="",
        top_group_id=top.pk if top else None,
        top_group_name=top.name if top else "",
        region_names=[],
        authme_is_registered=bool(account.authme_is_registered),
        last_sync_error="",
        is_vanilla_op=is_op,
        op_lookup_name=op_name or (account.ms_username or account.short_name or ""),
        active_session_id=sessions.get((ACCOUNT_PLAYER, account.short_name), ""),
        sort_key=f"0:{account.sort_order:05d}:{account.short_name.lower()}",
    )


def builder_account_to_dto(
    reg: MinecraftTeamRegistration,
    *,
    ops: list[VanillaOperator] | None = None,
    sessions: dict[tuple[str, str], str] | None = None,
) -> AccountDTO:
    ops = ops if ops is not None else []
    sessions = sessions if sessions is not None else {}
    group = reg.group
    top = top_group_for(group)
    candidates = _op_lookup_candidates(reg.ms_username, reg.mc_username)
    is_op, op_name = _match_op(candidates, ops)
    region_names: list[str] = []
    # Prefetch may attach .builder_regions via custom attribute
    regions = getattr(reg, "prefetched_regions", None)
    if regions is None and hasattr(reg, "protected_regions"):
        regions = list(reg.protected_regions.all())
    if regions:
        region_names = [r.display_name or r.region_id for r in regions]
    return AccountDTO(
        account_type=ACCOUNT_BUILDER,
        pk=reg.pk,
        label=group.name if group else reg.mc_username,
        login_key=reg.mc_username,
        id_tag="",
        ms_username=(reg.ms_username or "").strip(),
        ms_uuid=(reg.ms_uuid or "").strip(),
        is_active=bool(reg.is_active),
        session_duration_minutes=reg.session_duration_minutes,
        add_time_minutes=reg.add_time_minutes,
        session_unlimited=bool(reg.session_unlimited),
        prefer_gamemode=(reg.prefer_gamemode or "").strip(),
        prefer_spectator=bool(reg.prefer_spectator),
        group_id=group.pk if group else None,
        group_name=group.name if group else "",
        top_group_id=top.pk if top else None,
        top_group_name=top.name if top else "",
        region_names=region_names,
        authme_is_registered=bool(reg.authme_is_registered),
        last_sync_error=(reg.last_sync_error or "").strip(),
        is_vanilla_op=is_op,
        op_lookup_name=op_name or (reg.ms_username or reg.mc_username or ""),
        active_session_id=sessions.get((ACCOUNT_BUILDER, reg.mc_username), ""),
        sort_key=f"1:{(reg.mc_username or '').lower()}",
    )


def list_account_dtos(
    *,
    account_type: str = "",
    top_group_id: int | None = None,
    query: str = "",
    include_inactive: bool = True,
    ops: list[VanillaOperator] | None = None,
) -> list[AccountDTO]:
    """Unified account list for Admin UI."""
    try:
        ops_list = ops if ops is not None else list_operators(use_cache=True)
        ops_error = None
    except Exception as exc:  # noqa: BLE001 — surface in UI via empty OP status
        ops_list = []
        ops_error = str(exc)

    sessions = _active_sessions_by_account()
    dtos: list[AccountDTO] = []
    want_player = account_type in ("", ACCOUNT_PLAYER, "player", "PLAYER")
    want_builder = account_type in ("", ACCOUNT_BUILDER, "builder", "BUILDER")
    q = (query or "").strip()

    if want_player:
        play_qs = MinecraftPlayAccount.objects.select_related("assigned_to_group").order_by(
            "sort_order", "short_name"
        )
        if not include_inactive:
            play_qs = play_qs.filter(is_active=True)
        if top_group_id:
            play_qs = play_qs.filter(assigned_to_group_id=top_group_id)
        if q:
            play_qs = play_qs.filter(
                Q(short_name__icontains=q)
                | Q(id_tag__icontains=q)
                | Q(ms_username__icontains=q)
                | Q(display_name__icontains=q)
            )
        for acc in play_qs:
            dtos.append(play_account_to_dto(acc, ops=ops_list, sessions=sessions))

    if want_builder:
        region_prefetch = Prefetch(
            "protected_regions",
            queryset=MinecraftProtectedRegion.objects.order_by("sort_order", "region_id"),
            to_attr="prefetched_regions",
        )
        builder_qs = (
            MinecraftTeamRegistration.objects.select_related("group", "group__parent")
            .prefetch_related(region_prefetch)
            .order_by("mc_username")
        )
        if not include_inactive:
            builder_qs = builder_qs.filter(is_active=True)
        if q:
            builder_qs = builder_qs.filter(
                Q(mc_username__icontains=q)
                | Q(ms_username__icontains=q)
                | Q(group__name__icontains=q)
            )
        for reg in builder_qs:
            dto = builder_account_to_dto(reg, ops=ops_list, sessions=sessions)
            if top_group_id and dto.top_group_id != top_group_id:
                continue
            dtos.append(dto)

    dtos.sort(key=lambda d: d.sort_key)
    # Attach transient error for callers that care (optional attribute)
    for dto in dtos:
        setattr(dto, "ops_list_error", ops_error)
    return dtos


def get_account(account_type: str, pk: int) -> MinecraftPlayAccount | MinecraftTeamRegistration:
    atype = (account_type or "").strip().upper()
    if atype == ACCOUNT_PLAYER:
        return MinecraftPlayAccount.objects.select_related("assigned_to_group").get(pk=pk)
    if atype == ACCOUNT_BUILDER:
        return (
            MinecraftTeamRegistration.objects.select_related("group", "group__parent")
            .prefetch_related("protected_regions")
            .get(pk=pk)
        )
    raise ValueError(f"Unknown account type: {account_type}")


def get_account_dto(account_type: str, pk: int, *, ops: list[VanillaOperator] | None = None) -> AccountDTO:
    try:
        ops_list = ops if ops is not None else list_operators(use_cache=True)
    except Exception:  # noqa: BLE001
        ops_list = []
    sessions = _active_sessions_by_account()
    obj = get_account(account_type, pk)
    if isinstance(obj, MinecraftPlayAccount):
        return play_account_to_dto(obj, ops=ops_list, sessions=sessions)
    return builder_account_to_dto(obj, ops=ops_list, sessions=sessions)


def update_play_account(account: MinecraftPlayAccount, data: dict[str, Any]) -> MinecraftPlayAccount:
    if "ms_username" in data:
        account.ms_username = (data.get("ms_username") or "").strip()
    if "ms_uuid" in data:
        account.ms_uuid = (data.get("ms_uuid") or "").strip()
    if "display_name" in data:
        account.display_name = (data.get("display_name") or "").strip()
    if "is_active" in data:
        account.is_active = bool(data["is_active"])
    if "session_duration_minutes" in data:
        raw = data.get("session_duration_minutes")
        account.session_duration_minutes = int(raw) if raw not in (None, "") else None
    if "add_time_minutes" in data:
        raw = data.get("add_time_minutes")
        account.add_time_minutes = int(raw) if raw not in (None, "") else None
    if "session_unlimited" in data:
        account.session_unlimited = bool(data["session_unlimited"])
    if "prefer_gamemode" in data:
        account.prefer_gamemode = (data.get("prefer_gamemode") or "").strip()
    if "prefer_spectator" in data:
        account.prefer_spectator = bool(data["prefer_spectator"])
    if "assigned_to_group_id" in data:
        gid = data.get("assigned_to_group_id")
        if gid in (None, "", 0, "0"):
            account.assigned_to_group = None
        else:
            group = Group.objects.get(pk=int(gid))
            if group.parent_id is not None:
                raise ValueError("assigned_to_group must be a TOP group (parent is None).")
            account.assigned_to_group = group
    account.save()
    return account


def update_builder_account(
    reg: MinecraftTeamRegistration, data: dict[str, Any]
) -> MinecraftTeamRegistration:
    if "ms_username" in data:
        reg.ms_username = (data.get("ms_username") or "").strip()
    if "ms_uuid" in data:
        reg.ms_uuid = (data.get("ms_uuid") or "").strip()
    # is_active for builders: use deactivate_builder / reactivate_builder (outbox).
    if "session_duration_minutes" in data:
        raw = data.get("session_duration_minutes")
        reg.session_duration_minutes = int(raw) if raw not in (None, "") else None
    if "add_time_minutes" in data:
        raw = data.get("add_time_minutes")
        reg.add_time_minutes = int(raw) if raw not in (None, "") else None
    if "session_unlimited" in data:
        reg.session_unlimited = bool(data["session_unlimited"])
    if "prefer_gamemode" in data:
        reg.prefer_gamemode = (data.get("prefer_gamemode") or "").strip()
    if "prefer_spectator" in data:
        reg.prefer_spectator = bool(data["prefer_spectator"])
    reg.save()
    return reg


def create_play_account(data: dict[str, Any]) -> MinecraftPlayAccount:
    """Create a new Arena play slot."""
    short_name = (data.get("short_name") or "").strip()
    id_tag = (data.get("id_tag") or "").strip() or short_name
    if not short_name:
        raise ValueError("Kurzname / Login ist erforderlich.")
    if MinecraftPlayAccount.objects.filter(short_name__iexact=short_name).exists():
        raise ValueError(f"Kurzname „{short_name}“ existiert bereits.")
    if MinecraftPlayAccount.objects.filter(id_tag__iexact=id_tag).exists():
        raise ValueError(f"RFID-UID „{id_tag}“ existiert bereits.")

    max_order = (
        MinecraftPlayAccount.objects.order_by("-sort_order")
        .values_list("sort_order", flat=True)
        .first()
    )
    ms_username = (data.get("ms_username") or "").strip()
    ms_uuid = (data.get("ms_uuid") or "").strip()
    if not ms_uuid and ms_username:
        from minecraft.services.playerdata_uuid import resolve_ms_uuid_for_login

        ms_uuid = resolve_ms_uuid_for_login(ms_username) or ""
    account = MinecraftPlayAccount(
        short_name=short_name,
        id_tag=id_tag,
        display_name=(data.get("display_name") or "").strip(),
        ms_username=ms_username,
        ms_uuid=ms_uuid,
        is_active=bool(data.get("is_active", True)),
        sort_order=int(data["sort_order"]) if data.get("sort_order") not in (None, "") else (max_order or 0) + 1,
        session_duration_minutes=(
            int(data["session_duration_minutes"])
            if data.get("session_duration_minutes") not in (None, "")
            else None
        ),
        add_time_minutes=(
            int(data["add_time_minutes"])
            if data.get("add_time_minutes") not in (None, "")
            else None
        ),
        session_unlimited=bool(data.get("session_unlimited", False)),
        prefer_gamemode=(data.get("prefer_gamemode") or "").strip(),
        prefer_spectator=bool(data.get("prefer_spectator", False)),
    )
    gid = data.get("assigned_to_group_id")
    if gid not in (None, "", 0, "0"):
        group = Group.objects.get(pk=int(gid))
        if group.parent_id is not None:
            raise ValueError("assigned_to_group must be a TOP group (parent is None).")
        account.assigned_to_group = group
    account.save()
    return account


def delete_play_account(account: MinecraftPlayAccount, *, end_active_session: bool = True) -> None:
    """Delete play account; optionally end an active session first."""
    active = MCSession.objects.filter(
        account_type=MCSession.ACCOUNT_PLAYER,
        account_name__iexact=account.short_name,
        status=MCSession.STATUS_ACTIVE,
    ).first()
    if active is not None:
        if not end_active_session:
            raise ValueError(
                f"Spieler-Account „{account.short_name}“ hat eine aktive Session."
            )
        from minecraft.services.session_control import end_session

        end_session(account.short_name, send_rcon=True)
    account.delete()


def register_builder_group(group_id: int, *, user=None) -> MinecraftTeamRegistration:
    from minecraft.services.team_registration import register_group_for_minecraft

    group = Group.objects.get(pk=int(group_id))
    return register_group_for_minecraft(group, user=user)


def deactivate_builder(pk: int) -> MinecraftTeamRegistration:
    from minecraft.services.team_registration import deactivate_registration

    reg = MinecraftTeamRegistration.objects.select_related("group").get(pk=pk)
    # End active builder session if any
    active = MCSession.objects.filter(
        account_type=MCSession.ACCOUNT_BUILDER,
        account_name__iexact=reg.mc_username,
        status=MCSession.STATUS_ACTIVE,
    ).first()
    if active is not None:
        from minecraft.services.session_control import end_session

        end_session(reg.mc_username, send_rcon=True)
    deactivate_registration(reg, reason="manual_deactivate")
    return reg


def reactivate_builder(pk: int) -> MinecraftTeamRegistration:
    from minecraft.services.team_registration import reactivate_registration

    reg = MinecraftTeamRegistration.objects.select_related("group").get(pk=pk)
    reactivate_registration(reg)
    return reg


def pending_builder_groups() -> list[Group]:
    from minecraft.services.team_registration import pending_team_candidates

    return list(pending_team_candidates())


def builder_adopt_choices() -> list[dict[str, str]]:
    """
    Dropdown targets for adopting a Limbo login as Bau-Account.

    - pending groups → register + set ms_username
    - active registrations without ms_username → assign ms_username only
    """
    choices: list[dict[str, str]] = []
    for group in pending_builder_groups():
        choices.append(
            {
                "value": f"group:{group.pk}",
                "label": f"Neu registrieren: {group.name} ({group.mc_username})",
            }
        )
    for reg in (
        MinecraftTeamRegistration.objects.filter(is_active=True)
        .filter(Q(ms_username="") | Q(ms_username__isnull=True))
        .select_related("group")
        .order_by("mc_username")
    ):
        gname = reg.group.name if reg.group_id else reg.mc_username
        choices.append(
            {
                "value": f"reg:{reg.pk}",
                "label": f"Zuweisen: {gname} ({reg.mc_username})",
            }
        )
    return choices


def adopt_limbo_as_builder(
    ms_username: str,
    *,
    target: str,
    user=None,
) -> MinecraftTeamRegistration:
    """
    Attach a Limbo Microsoft login to a Bau-Account.

    ``target`` is ``group:<id>`` (register pending group) or ``reg:<id>``
    (assign to existing registration without ms_username).
    """
    name = (ms_username or "").strip()
    if not name:
        raise ValueError("Microsoft-Login fehlt.")
    if len(name) > 32:
        raise ValueError("Microsoft-Login zu lang (max. 32).")

    # Reject if already used
    if MinecraftPlayAccount.objects.filter(ms_username__iexact=name).exists():
        raise ValueError(f"„{name}“ ist bereits als Spieler-Account hinterlegt.")
    clash = (
        MinecraftTeamRegistration.objects.filter(ms_username__iexact=name, is_active=True)
        .exclude(ms_username="")
        .first()
    )
    if clash is not None:
        raise ValueError(f"„{name}“ ist bereits Bau-Account „{clash.mc_username}“.")

    raw = (target or "").strip()
    if raw.startswith("group:"):
        group_id = int(raw.split(":", 1)[1])
        reg = register_builder_group(group_id, user=user)
        reg.ms_username = name
        from minecraft.services.playerdata_uuid import resolve_ms_uuid_for_login

        uid = resolve_ms_uuid_for_login(name) or ""
        update_fields = ["ms_username"]
        if uid:
            reg.ms_uuid = uid
            update_fields.append("ms_uuid")
        reg.save(update_fields=update_fields)
        return reg
    if raw.startswith("reg:"):
        pk = int(raw.split(":", 1)[1])
        reg = MinecraftTeamRegistration.objects.select_related("group").get(pk=pk)
        if not reg.is_active:
            raise ValueError("Bau-Account ist nicht aktiv.")
        if (reg.ms_username or "").strip():
            raise ValueError("Bau-Account hat bereits einen Microsoft-Login.")
        reg.ms_username = name
        from minecraft.services.playerdata_uuid import resolve_ms_uuid_for_login

        uid = resolve_ms_uuid_for_login(name) or ""
        update_fields = ["ms_username"]
        if uid and not (reg.ms_uuid or "").strip():
            reg.ms_uuid = uid
            update_fields.append("ms_uuid")
        reg.save(update_fields=update_fields)
        return reg
    raise ValueError("Kein gültiges Bau-Ziel gewählt.")


def known_ms_login_keys() -> set[str]:
    """Lowercased Microsoft / slot names already known in MCC accounts."""
    keys: set[str] = set()
    for row in MinecraftPlayAccount.objects.values_list(
        "ms_username", "short_name", "id_tag"
    ):
        for raw in row:
            name = (raw or "").strip().lower()
            if name:
                keys.add(name)
    for row in MinecraftTeamRegistration.objects.values_list("ms_username", "mc_username"):
        for raw in row:
            name = (raw or "").strip().lower()
            if name:
                keys.add(name)
    return keys


def list_limbo_players_without_account() -> tuple[list[str], str]:
    """
    Live Limbo players (Velocity glist) that have no matching MCC account.

    Temporary listing only — nothing is persisted until an operator creates
    an account. Returns ``(sorted_names, error_message)``.
    """
    from mcrcon import MCRconException

    from minecraft.services.player_presence import limbo_server_name, parse_glist_players
    from minecraft.services.velocity_rcon import glist_server

    try:
        raw = glist_server(limbo_server_name())
        names = parse_glist_players(raw)
    except (MCRconException, OSError, ValueError) as exc:
        return [], str(exc)

    known = known_ms_login_keys()
    unknown = sorted(
        {n for n in names if n.strip() and n.strip().lower() not in known},
        key=str.lower,
    )
    return unknown, ""


def resolve_op_player_name(account_type: str, pk: int) -> tuple[str, AccountDTO]:
    """Prefer Microsoft login for /op; fall back to slot/team name."""
    dto = get_account_dto(account_type, pk)
    name = (dto.ms_username or dto.login_key or "").strip()
    if not name:
        raise ValueError("Kein Login-Name für /op verfügbar (ms_username/Login fehlt).")
    return name, dto
