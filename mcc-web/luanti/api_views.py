# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    api_views.py
# @note    HTTP API for Luanti server bridge and station agents.

from __future__ import annotations

import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST

from config.logger_utils import get_logger
from luanti.services.bridge_connection import touch_bridge_connection
from luanti.services.http_security import verify_request_auth
from luanti.services.session_control import (
    SessionError,
    auth_check_payload,
    end_session,
    find_account_by_token,
    get_active_session,
    get_or_create_inventory,
    join_payload,
    set_session_mode,
    start_session,
)
from luanti.services.shop import ShopError, build_catalog_payload, shop_buy, shop_sell
from luanti.services.wallet import WalletError, withdraw_velos, wallet_payload
from luanti.services.city import build_regions_payload
from luanti.services.arena import build_arena_state
from luanti.services.stations import authenticate_station, station_desired_payload, touch_station
from luanti.models import LuantiSession

logger = get_logger("luanti")


def _parse_json(request) -> dict:
    try:
        data = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _auth_or_error(data: dict) -> tuple[dict | None, JsonResponse | None]:
    server_id = str(data.get("server_id") or "").strip()
    signature = str(data.get("signature") or "").strip()
    ts = data.get("timestamp")
    timestamp = int(ts) if ts is not None else None
    payload = {k: v for k, v in data.items() if k != "signature"}
    ok, err = verify_request_auth(
        server_id=server_id,
        signature=signature,
        payload=payload,
        timestamp=timestamp,
    )
    if not ok:
        return None, JsonResponse({"ok": False, "error": err}, status=403)
    if server_id:
        touch_bridge_connection(server_id)
    return data, None


@csrf_exempt
@require_POST
def luanti_heartbeat(request):
    data = _parse_json(request)
    data, err = _auth_or_error(data)
    if err:
        return err
    from luanti.services.command_queue import drain_commands
    from luanti.services.session_control import (
        expire_due_sessions,
        reconcile_sessions_with_online_players,
    )

    expire_due_sessions()
    # New bridge sends player_count (Lua empty arrays become JSON {}).
    # Legacy heartbeats omit player_count → skip reconcile.
    players = None
    if "player_count" in data:
        raw_players = data.get("players")
        if isinstance(raw_players, list):
            players = raw_players
        elif isinstance(raw_players, dict):
            players = [str(v) for v in raw_players.values()]
        else:
            players = []
        try:
            count = int(data.get("player_count"))
        except (TypeError, ValueError):
            count = len(players)
        if count == 0:
            players = []
    ended_offline = reconcile_sessions_with_online_players(players)
    server_id = str(data.get("server_id") or "")
    commands = drain_commands(server_id)
    return JsonResponse(
        {
            "ok": True,
            "status": "alive",
            "commands": commands,
            "ended_offline": len(ended_offline),
        }
    )


@csrf_exempt
@require_POST
def luanti_auth_check(request):
    data = _parse_json(request)
    data, err = _auth_or_error(data)
    if err:
        return err
    login = str(data.get("player") or data.get("login_name") or "").strip()
    if not login:
        return JsonResponse({"ok": False, "error": "missing_player"}, status=400)
    return JsonResponse(auth_check_payload(login))


@csrf_exempt
@require_POST
def luanti_session_join(request):
    data = _parse_json(request)
    data, err = _auth_or_error(data)
    if err:
        return err
    login = str(data.get("player") or data.get("login_name") or "").strip()
    if not login:
        return JsonResponse({"ok": False, "error": "missing_player"}, status=400)
    server_id = str(data.get("server_id") or "")
    return JsonResponse(join_payload(login, server_id=server_id))


@csrf_exempt
@require_POST
def luanti_session_leave(request):
    data = _parse_json(request)
    data, err = _auth_or_error(data)
    if err:
        return err
    login = str(data.get("player") or data.get("login_name") or "").strip()
    inventory = data.get("inventory")
    if not isinstance(inventory, list):
        inventory = None
    from luanti.services.presence import clear_waiting

    if login:
        clear_waiting(login)
    session = get_active_session(login) if login else None
    if not session:
        return JsonResponse({"ok": True, "ended": False})
    end_session(session, inventory_payload=inventory)
    return JsonResponse({"ok": True, "ended": True})


@csrf_exempt
@require_POST
def luanti_session_set_mode(request):
    data = _parse_json(request)
    data, err = _auth_or_error(data)
    if err:
        return err
    login = str(data.get("player") or "").strip()
    mode = str(data.get("mode") or "").strip()
    inventory = data.get("inventory") if isinstance(data.get("inventory"), list) else None
    session = get_active_session(login)
    if not session:
        return JsonResponse({"ok": False, "error": "no_session"}, status=404)
    try:
        set_session_mode(session, mode, save_inventory=inventory)
    except SessionError as exc:
        return JsonResponse({"ok": False, "error": exc.code}, status=400)
    return JsonResponse(join_payload(login, server_id=str(data.get("server_id") or "")))


@csrf_exempt
@require_POST
def luanti_inventory_sync(request):
    data = _parse_json(request)
    data, err = _auth_or_error(data)
    if err:
        return err
    login = str(data.get("player") or "").strip()
    mode = str(data.get("mode") or "").strip()
    inventory = data.get("inventory")
    if not login or not isinstance(inventory, list):
        return JsonResponse({"ok": False, "error": "invalid_payload"}, status=400)
    session = get_active_session(login)
    if not session:
        return JsonResponse({"ok": False, "error": "no_session"}, status=404)
    use_mode = mode or session.mode
    inv = get_or_create_inventory(session.account, use_mode)
    inv.payload = inventory
    inv.revision = inv.revision + 1
    inv.last_server_id = str(data.get("server_id") or "")
    inv.save(update_fields=["payload", "revision", "last_server_id", "updated_at"])
    return JsonResponse({"ok": True, "revision": inv.revision})


@csrf_exempt
@require_http_methods(["GET", "POST"])
def luanti_shop_catalog(request):
    if request.method == "POST":
        data = _parse_json(request)
        data, err = _auth_or_error(data)
        if err:
            return err
    return JsonResponse(build_catalog_payload())


@csrf_exempt
@require_POST
def luanti_shop_buy(request):
    data = _parse_json(request)
    data, err = _auth_or_error(data)
    if err:
        return err
    if not data.get("client_tx_id"):
        return JsonResponse({"ok": False, "error": "missing_client_tx_id"}, status=400)
    try:
        result = shop_buy(
            login_name=str(data.get("player") or ""),
            item_id=int(data.get("item_id")),
            quantity=int(data.get("quantity") or 1),
            client_tx_id=str(data.get("client_tx_id") or ""),
        )
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "invalid_payload"}, status=400)
    except ShopError as exc:
        return JsonResponse({"ok": False, "error": exc.code}, status=400)
    return JsonResponse(result)


@csrf_exempt
@require_POST
def luanti_wallet_withdraw(request):
    """Deduct spendable Velos from the player's resolved active wallet."""
    data = _parse_json(request)
    data, err = _auth_or_error(data)
    if err:
        return err
    try:
        result = withdraw_velos(
            login_name=str(data.get("player") or data.get("username") or ""),
            amount=int(data.get("amount")),
        )
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "invalid_payload"}, status=400)
    except WalletError as exc:
        return JsonResponse({"ok": False, "error": exc.code}, status=400)
    return JsonResponse(result)


@csrf_exempt
@require_POST
def luanti_wallet_balance(request):
    data = _parse_json(request)
    data, err = _auth_or_error(data)
    if err:
        return err
    login = str(data.get("player") or data.get("username") or "").strip()
    if not login:
        return JsonResponse({"ok": False, "error": "missing_player"}, status=400)
    from luanti.models import LuantiAccount

    account = LuantiAccount.objects.filter(login_name__iexact=login).first()
    session = get_active_session(login)
    payload = wallet_payload(account, session=session)
    return JsonResponse({"ok": True, **payload})


@csrf_exempt
@require_POST
def luanti_shop_sell(request):
    data = _parse_json(request)
    data, err = _auth_or_error(data)
    if err:
        return err
    tx_id = str(data.get("client_tx_id") or "")
    if not tx_id:
        return JsonResponse({"ok": False, "error": "missing_client_tx_id"}, status=400)
    try:
        result = shop_sell(
            login_name=str(data.get("player") or ""),
            item_name=str(data.get("item_name") or ""),
            quantity=int(data.get("quantity") or 1),
            client_tx_id=tx_id,
        )
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "invalid_payload"}, status=400)
    except ShopError as exc:
        return JsonResponse({"ok": False, "error": exc.code}, status=400)
    return JsonResponse(result)


@csrf_exempt
@require_POST
def luanti_regions(request):
    data = _parse_json(request)
    data, err = _auth_or_error(data)
    if err:
        return err
    return JsonResponse(build_regions_payload())


@csrf_exempt
@require_POST
def luanti_arena_state(request):
    data = _parse_json(request)
    data, err = _auth_or_error(data)
    if err:
        return err
    return JsonResponse(build_arena_state())


@csrf_exempt
@require_POST
def luanti_counter_scan(request):
    """RFID scan → start Luanti session (API key like Minecraft counter)."""
    from api.views import validate_api_key

    api_key_header = request.headers.get("X-Api-Key")
    is_valid, _api_device = validate_api_key(api_key_header)
    if not is_valid:
        return JsonResponse({"ok": False, "error": "invalid_api_key"}, status=403)
    data = _parse_json(request)
    token = ""
    for key in ("token", "id_tag", "rfid"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            token = value.strip()
            break
    if not token:
        return JsonResponse({"ok": False, "error": "missing_token"}, status=400)
    account = find_account_by_token(token)
    if not account:
        return JsonResponse({"ok": False, "error": "unknown_account"}, status=404)
    mode = str(data.get("mode") or account.default_mode).strip()
    try:
        session = start_session(
            account=account,
            mode=mode,
            source=LuantiSession.SOURCE_RFID,
        )
    except SessionError as exc:
        if exc.code == "already_active":
            session = get_active_session(account.login_name)
            return JsonResponse(
                {
                    "ok": True,
                    "already_active": True,
                    "session_id": str(session.session_id) if session else None,
                    "login_name": account.login_name,
                    "mode": session.mode if session else mode,
                }
            )
        return JsonResponse({"ok": False, "error": exc.code}, status=400)
    return JsonResponse(
        {
            "ok": True,
            "session_id": str(session.session_id),
            "login_name": account.login_name,
            "mode": session.mode,
        }
    )


@csrf_exempt
@require_http_methods(["GET", "POST"])
def luanti_station_config(request):
    api_key = request.headers.get("X-Station-Key") or request.GET.get("api_key") or ""
    if request.method == "POST":
        data = _parse_json(request)
        api_key = api_key or str(data.get("api_key") or "")
    station = authenticate_station(api_key)
    if not station:
        return JsonResponse({"ok": False, "error": "invalid_station_key"}, status=403)
    if request.method == "POST":
        data = _parse_json(request)
        touch_station(
            station,
            reported=data.get("reported") if isinstance(data.get("reported"), dict) else None,
            error=str(data.get("error") or ""),
        )
    else:
        touch_station(station)
    return JsonResponse(station_desired_payload(station))
