# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    account_views.py
# @note    Unified Minecraft account admin (play + builder) with Vanilla OP actions.

from __future__ import annotations

from urllib.parse import quote

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from config.logger_utils import get_logger
from minecraft.models import MinecraftPlayAccount, MinecraftTeamRegistration, MinecraftVanillaOpLog
from minecraft.services.account_admin import (
    ACCOUNT_BUILDER,
    ACCOUNT_PLAYER,
    adopt_limbo_as_builder,
    builder_adopt_choices,
    create_play_account,
    deactivate_builder,
    delete_play_account,
    get_account,
    get_account_dto,
    list_account_dtos,
    list_limbo_players_without_account,
    list_top_groups,
    pending_builder_groups,
    reactivate_builder,
    register_builder_group,
    resolve_op_player_name,
    update_builder_account,
    update_play_account,
)
from minecraft.services.preset_permissions import (
    user_can_manage_minecraft_accounts,
    user_can_manage_minecraft_operators,
)
from minecraft.services.vanilla_op import (
    VanillaOpError,
    grant_op,
    list_operators,
    revoke_op,
)

logger = get_logger("minecraft")

VALID_GAMEMODES = frozenset({"", "survival", "adventure", "spectator"})


def _can_access_accounts(user) -> bool:
    return user_can_manage_minecraft_accounts(user) or user_can_manage_minecraft_operators(user)


def _parse_bool(raw) -> bool:
    if isinstance(raw, bool):
        return raw
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}


def _optional_int(raw):
    text = (raw or "").strip()
    if text == "":
        return None
    return int(text)


def _redirect_with_filters(redirect_name, filter_type, filter_top, filter_q, include_inactive):
    params = []
    if filter_type:
        params.append(f"type={filter_type}")
    if filter_top:
        params.append(f"top={filter_top}")
    if filter_q:
        params.append(f"q={quote(filter_q)}")
    params.append("inactive=1" if include_inactive else "inactive=0")
    params.append("filtered=1")
    url = reverse(redirect_name)
    if params:
        url = f"{url}?{'&'.join(params)}"
    return redirect(url)


@user_passes_test(_can_access_accounts)
@staff_member_required
@require_http_methods(["GET", "POST"])
def minecraft_accounts(request):
    """Unified Minecraft account management (CRUD + Vanilla OP)."""
    can_edit = user_can_manage_minecraft_accounts(request.user)
    can_op = user_can_manage_minecraft_operators(request.user)
    redirect_name = "admin:minecraft_accounts"

    filter_type = (request.GET.get("type") or request.POST.get("filter_type") or "").strip()
    filter_top = (request.GET.get("top") or request.POST.get("filter_top") or "").strip()
    filter_q = (request.GET.get("q") or request.POST.get("filter_q") or "").strip()
    if request.GET.get("filtered") == "1" or request.POST.get("filtered") == "1":
        include_inactive = (
            request.GET.get("inactive") == "1" or request.POST.get("inactive") == "1"
        )
    else:
        include_inactive = True

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        try:
            if action == "create_player":
                if not can_edit:
                    messages.error(request, _("Keine Berechtigung zum Anlegen von Accounts."))
                    return _redirect_with_filters(
                        redirect_name, filter_type, filter_top, filter_q, include_inactive
                    )
                prefer_gm = (request.POST.get("prefer_gamemode") or "").strip()
                if prefer_gm not in VALID_GAMEMODES:
                    raise ValueError(_("Ungültiger Spielmodus."))
                obj = create_play_account(
                    {
                        "short_name": request.POST.get("short_name"),
                        "id_tag": request.POST.get("id_tag"),
                        "display_name": request.POST.get("display_name"),
                        "ms_username": request.POST.get("ms_username"),
                        "ms_uuid": request.POST.get("ms_uuid"),
                        "assigned_to_group_id": request.POST.get("assigned_to_group_id"),
                        "is_active": True,
                        "prefer_gamemode": prefer_gm,
                        "prefer_spectator": _parse_bool(request.POST.get("prefer_spectator")),
                        "session_duration_minutes": _optional_int(
                            request.POST.get("session_duration_minutes")
                        ),
                        "add_time_minutes": _optional_int(request.POST.get("add_time_minutes")),
                    }
                )
                messages.success(
                    request,
                    _("Spieler-Account „%(name)s“ angelegt.") % {"name": obj.label},
                )

            elif action == "delete_player":
                if not can_edit:
                    messages.error(request, _("Keine Berechtigung zum Löschen von Accounts."))
                    return _redirect_with_filters(
                        redirect_name, filter_type, filter_top, filter_q, include_inactive
                    )
                pk = int(request.POST.get("pk") or 0)
                obj = get_account(ACCOUNT_PLAYER, pk)
                assert isinstance(obj, MinecraftPlayAccount)
                label = obj.label
                delete_play_account(obj, end_active_session=True)
                messages.success(
                    request,
                    _("Spieler-Account „%(name)s“ gelöscht.") % {"name": label},
                )

            elif action == "adopt_builder":
                if not can_edit:
                    messages.error(request, _("Keine Berechtigung zum Übernehmen als Bau-Account."))
                    return _redirect_with_filters(
                        redirect_name, filter_type, filter_top, filter_q, include_inactive
                    )
                ms_name = (request.POST.get("ms_username") or "").strip()
                target = (request.POST.get("builder_target") or "").strip()
                reg = adopt_limbo_as_builder(ms_name, target=target, user=request.user)
                messages.success(
                    request,
                    _(
                        "Limbo-Login „%(ms)s“ als Bau-Account „%(team)s“ übernommen."
                    )
                    % {"ms": ms_name, "team": reg.mc_username},
                )

            elif action == "register_builder":
                if not can_edit:
                    messages.error(request, _("Keine Berechtigung zum Registrieren von Bau-Accounts."))
                    return _redirect_with_filters(
                        redirect_name, filter_type, filter_top, filter_q, include_inactive
                    )
                group_id = int(request.POST.get("group_id") or 0)
                reg = register_builder_group(group_id, user=request.user)
                messages.success(
                    request,
                    _(
                        "Bau-Account „%(name)s“ registriert. "
                        "LuckPerms/Scoreboard werden vom Worker synchronisiert."
                    )
                    % {"name": reg.mc_username},
                )

            elif action == "deactivate_builder":
                if not can_edit:
                    messages.error(request, _("Keine Berechtigung zum Deaktivieren von Bau-Accounts."))
                    return _redirect_with_filters(
                        redirect_name, filter_type, filter_top, filter_q, include_inactive
                    )
                pk = int(request.POST.get("pk") or 0)
                reg = deactivate_builder(pk)
                messages.success(
                    request,
                    _("Bau-Account „%(name)s“ deaktiviert.") % {"name": reg.mc_username},
                )

            elif action == "reactivate_builder":
                if not can_edit:
                    messages.error(request, _("Keine Berechtigung zum Reaktivieren von Bau-Accounts."))
                    return _redirect_with_filters(
                        redirect_name, filter_type, filter_top, filter_q, include_inactive
                    )
                pk = int(request.POST.get("pk") or 0)
                reg = reactivate_builder(pk)
                messages.success(
                    request,
                    _("Bau-Account „%(name)s“ reaktiviert.") % {"name": reg.mc_username},
                )

            elif action == "save_account":
                if not can_edit:
                    messages.error(request, _("Keine Berechtigung zum Bearbeiten von Accounts."))
                    return _redirect_with_filters(
                        redirect_name, filter_type, filter_top, filter_q, include_inactive
                    )
                account_type = (request.POST.get("account_type") or "").strip().upper()
                pk = int(request.POST.get("pk") or 0)
                data = {
                    "ms_username": request.POST.get("ms_username"),
                    "ms_uuid": request.POST.get("ms_uuid"),
                    "session_duration_minutes": _optional_int(
                        request.POST.get("session_duration_minutes")
                    ),
                    "add_time_minutes": _optional_int(request.POST.get("add_time_minutes")),
                    "prefer_gamemode": (request.POST.get("prefer_gamemode") or "").strip(),
                    "prefer_spectator": _parse_bool(request.POST.get("prefer_spectator")),
                }
                if data["prefer_gamemode"] not in VALID_GAMEMODES:
                    raise ValueError(_("Ungültiger Spielmodus."))
                if account_type == ACCOUNT_PLAYER:
                    data["display_name"] = request.POST.get("display_name")
                    data["assigned_to_group_id"] = request.POST.get("assigned_to_group_id")
                    data["is_active"] = _parse_bool(request.POST.get("is_active"))
                    obj = get_account(ACCOUNT_PLAYER, pk)
                    assert isinstance(obj, MinecraftPlayAccount)
                    update_play_account(obj, data)
                    messages.success(
                        request,
                        _("Spieler-Account „%(name)s“ gespeichert.") % {"name": obj.label},
                    )
                elif account_type == ACCOUNT_BUILDER:
                    obj = get_account(ACCOUNT_BUILDER, pk)
                    assert isinstance(obj, MinecraftTeamRegistration)
                    update_builder_account(obj, data)
                    messages.success(
                        request,
                        _("Bau-Account „%(name)s“ gespeichert.") % {"name": obj.mc_username},
                    )
                else:
                    raise ValueError(_("Unbekannter Account-Typ."))

            elif action in ("op", "deop"):
                if not can_op:
                    messages.error(
                        request,
                        _("Keine Berechtigung für Vanilla-Operatorrechte."),
                    )
                    return _redirect_with_filters(
                        redirect_name, filter_type, filter_top, filter_q, include_inactive
                    )
                account_type = (request.POST.get("account_type") or "").strip().upper()
                pk = int(request.POST.get("pk") or 0)
                player_name, dto = resolve_op_player_name(account_type, pk)
                if action == "op":
                    grant_op(
                        player_name,
                        user=request.user,
                        account_type=account_type,
                        account_ref=dto.ref,
                    )
                    messages.success(
                        request,
                        _("%(name)s ist jetzt Vanilla-Operator.") % {"name": player_name},
                    )
                else:
                    revoke_op(
                        player_name,
                        user=request.user,
                        account_type=account_type,
                        account_ref=dto.ref,
                    )
                    messages.success(
                        request,
                        _("Operatorrechte von %(name)s entzogen.") % {"name": player_name},
                    )

            elif action in ("op_raw", "deop_raw"):
                if not can_op:
                    messages.error(
                        request,
                        _("Keine Berechtigung für Vanilla-Operatorrechte."),
                    )
                    return _redirect_with_filters(
                        redirect_name, filter_type, filter_top, filter_q, include_inactive
                    )
                player_name = (request.POST.get("player_name") or "").strip()
                if action == "op_raw":
                    grant_op(player_name, user=request.user)
                    messages.success(
                        request,
                        _("%(name)s ist jetzt Vanilla-Operator.") % {"name": player_name},
                    )
                else:
                    revoke_op(player_name, user=request.user)
                    messages.success(
                        request,
                        _("Operatorrechte von %(name)s entzogen.") % {"name": player_name},
                    )
            else:
                messages.warning(request, _("Unbekannte Aktion."))
        except VanillaOpError as exc:
            messages.error(request, str(exc))
        except (
            ValueError,
            MinecraftPlayAccount.DoesNotExist,
            MinecraftTeamRegistration.DoesNotExist,
        ) as exc:
            messages.error(request, str(exc) or _("Account nicht gefunden."))
        except Exception as exc:  # noqa: BLE001
            logger.exception("[minecraft_accounts] action failed: %s", exc)
            messages.error(request, _("Aktion fehlgeschlagen: %(err)s") % {"err": exc})

        return _redirect_with_filters(
            redirect_name, filter_type, filter_top, filter_q, include_inactive
        )

    top_id = int(filter_top) if filter_top.isdigit() else None
    ops_error = ""
    operators = []
    try:
        operators = list_operators(use_cache=True)
    except Exception as exc:  # noqa: BLE001
        ops_error = str(exc)

    accounts = list_account_dtos(
        account_type=filter_type,
        top_group_id=top_id,
        query=filter_q,
        include_inactive=include_inactive,
        ops=operators,
    )

    edit_dto = None
    edit_type = (request.GET.get("edit_type") or "").strip().upper()
    edit_pk = (request.GET.get("edit") or "").strip()
    if can_edit and edit_type and edit_pk.isdigit():
        try:
            edit_dto = get_account_dto(edit_type, int(edit_pk), ops=operators)
        except Exception:  # noqa: BLE001
            messages.warning(request, _("Account zum Bearbeiten nicht gefunden."))

    recent_ops = list(
        MinecraftVanillaOpLog.objects.select_related("created_by").order_by("-created_at")[:15]
    )
    pending_groups = pending_builder_groups() if can_edit else []
    adopt_choices = builder_adopt_choices() if can_edit else []
    limbo_unknown: list[str] = []
    limbo_error = ""
    try:
        limbo_unknown, limbo_error = list_limbo_players_without_account()
    except Exception as exc:  # noqa: BLE001
        limbo_error = str(exc)

    prefill_ms = (request.GET.get("ms_username") or "").strip()
    prefill_short = (request.GET.get("short_name") or "").strip()
    show_create = request.GET.get("create") == "1" and can_edit
    show_adopt_builder = request.GET.get("adopt_builder") == "1" and can_edit and bool(prefill_ms)
    prefill_uuid = ""
    if prefill_ms and (show_create or show_adopt_builder):
        from minecraft.services.playerdata_uuid import resolve_ms_uuid_for_login

        prefill_uuid = resolve_ms_uuid_for_login(prefill_ms) or ""

    context = {
        "title": _("Account-Management"),
        "accounts": accounts,
        "operators": operators,
        "ops_error": ops_error,
        "can_edit": can_edit,
        "can_op": can_op,
        "top_groups": list_top_groups(),
        "pending_builder_groups": pending_groups,
        "builder_adopt_choices": adopt_choices,
        "limbo_unknown": limbo_unknown,
        "limbo_error": limbo_error,
        "filter_type": filter_type,
        "filter_top": filter_top,
        "filter_q": filter_q,
        "include_inactive": include_inactive,
        "edit_dto": edit_dto,
        "recent_ops": recent_ops,
        "ACCOUNT_PLAYER": ACCOUNT_PLAYER,
        "ACCOUNT_BUILDER": ACCOUNT_BUILDER,
        "player_sessions_url": reverse("admin:minecraft_player_sessions"),
        "builder_sessions_url": reverse("admin:minecraft_builder_sessions"),
        "show_create": show_create,
        "show_adopt_builder": show_adopt_builder,
        "prefill_ms_username": prefill_ms,
        "prefill_short_name": prefill_short or prefill_ms,
        "prefill_ms_uuid": prefill_uuid,
    }
    return render(request, "admin/minecraft/minecraft_accounts.html", context)
