#!/usr/bin/env python3
# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    shop_spend_load_test.py
# @note    Phase-B load: simulate Minecraft shop spends → outbox → worker/RCON.
#
# Modes:
#   django (default): call spend_group_velos_from_minecraft (same DB/outbox path as WS)
#   ws:               send signed SPEND_GROUP_VELOS over WebSocket (needs websockets pkg)
#
# Examples:
#   cd /data/appl/mcc/mcc-web
#   /data/appl/mcc/venv/bin/python3 /path/to/shop_spend_load_test.py --list
#   /data/appl/mcc/venv/bin/python3 /path/to/shop_spend_load_test.py --interval 15 --amount 2 --duration 600
#   /data/appl/mcc/venv/bin/python3 /path/to/shop_spend_load_test.py --mode ws --interval 15

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sys
import time
import uuid
from pathlib import Path


def _bootstrap_django() -> None:
    repo_web = Path(__file__).resolve().parents[1]
    candidates = [Path("/data/appl/mcc/mcc-web"), repo_web]
    for root in candidates:
        if (root / "manage.py").exists():
            sys.path.insert(0, str(root))
            break
    else:
        sys.path.insert(0, str(repo_web))

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()


def _active_players(explicit: list[str] | None) -> list[str]:
    from minecraft.models import MinecraftTeamRegistration

    qs = MinecraftTeamRegistration.objects.filter(is_active=True).order_by("mc_username")
    players = list(qs.values_list("mc_username", flat=True))
    if explicit:
        wanted = {p.strip() for p in explicit if p.strip()}
        players = [p for p in players if p in wanted]
        missing = wanted - set(players)
        if missing:
            print(f"WARN: not active / unknown players ignored: {sorted(missing)}")
    return players


def _list_players() -> int:
    from api.models import Group
    from minecraft.models import MinecraftTeamRegistration

    regs = (
        MinecraftTeamRegistration.objects.filter(is_active=True)
        .select_related("group")
        .order_by("mc_username")
    )
    if not regs.exists():
        print("No active Minecraft team registrations.")
        return 1
    print(f"{'mc_username':<24} {'group':<20} velos_spendable")
    print("-" * 60)
    for reg in regs:
        spendable = int(reg.group.velos_spendable or 0)
        print(f"{reg.mc_username:<24} {reg.group.name:<20} {spendable}")
    # Also show leaf groups with mc_username but no registration (optional hint)
    orphan = (
        Group.objects.filter(mc_username__isnull=False)
        .exclude(mc_username="")
        .exclude(pk__in=regs.values_list("group_id", flat=True))
    )
    if orphan.exists():
        print("\nGroups with mc_username but no active registration:")
        for g in orphan:
            print(f"  {g.name} mc={g.mc_username} spendable={int(g.velos_spendable or 0)}")
    return 0


def _spend_django(player: str, amount: int) -> str:
    from minecraft.services.group_velos import spend_group_velos_from_minecraft

    return spend_group_velos_from_minecraft(player, amount)


async def _spend_ws_once(url: str, server_id: str, player: str, amount: int) -> str:
    import websockets
    from minecraft.services.ws_security import sign_payload

    payload = {
        "type": "SPEND_GROUP_VELOS",
        "player": player,
        "amount": amount,
        "server_id": server_id,
        "request_id": str(uuid.uuid4()),
    }
    payload["signature"] = sign_payload({k: v for k, v in payload.items()})

    async with websockets.connect(url, open_timeout=10, close_timeout=5) as ws:
        await ws.send(json.dumps(payload))
        raw = await asyncio.wait_for(ws.recv(), timeout=10)
        data = json.loads(raw)
        if data.get("status") == "ok":
            return "ok"
        return data.get("error") or json.dumps(data)


def _spend_ws(player: str, amount: int) -> str:
    from django.conf import settings
    from minecraft.services.ws_url import build_ws_events_url

    url = build_ws_events_url()
    allowed = list(settings.MCC_MINECRAFT_WS_ALLOWED_SERVER_IDS or [])
    if not allowed:
        return "no_server_id_configured"
    server_id = allowed[0]
    try:
        return asyncio.run(_spend_ws_once(url, server_id, player, amount))
    except ImportError:
        return "websockets_not_installed"
    except Exception as exc:
        return f"ws_error:{exc}"


def run_loop(args: argparse.Namespace) -> int:
    players = _active_players(args.players)
    if not players:
        print("ERROR: no active players to spend for. Use --list.")
        return 1

    spend_fn = _spend_ws if args.mode == "ws" else _spend_django
    print(
        f"Shop-spend load: mode={args.mode} players={players} "
        f"amount={args.amount}-{args.amount_max} interval={args.interval}s "
        f"duration={args.duration or '∞'}s"
    )

    start = time.time()
    ok = fail = 0
    iteration = 0
    try:
        while True:
            iteration += 1
            if args.duration and (time.time() - start) >= args.duration:
                break
            player = random.choice(players)
            amount = random.randint(args.amount, args.amount_max)
            result = spend_fn(player, amount)
            if result == "ok":
                ok += 1
                print(f"[{iteration}] OK {player} -{amount}")
            else:
                fail += 1
                print(f"[{iteration}] FAIL {player} -{amount} → {result}")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nInterrupted.")

    elapsed = time.time() - start
    print(f"Done: ok={ok} fail={fail} elapsed={elapsed:.0f}s")
    return 0 if fail == 0 or ok > 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Minecraft shop spend load test (Phase B)")
    parser.add_argument("--list", action="store_true", help="List active MC team registrations and exit")
    parser.add_argument(
        "--mode",
        choices=("django", "ws"),
        default="django",
        help="django=ORM spend (default), ws=WebSocket SPEND_GROUP_VELOS",
    )
    parser.add_argument(
        "--players",
        nargs="*",
        help="Limit to these mc_username values (default: all active registrations)",
    )
    parser.add_argument("--amount", type=int, default=1, help="Min Velos per spend (default: 1)")
    parser.add_argument("--amount-max", type=int, default=5, help="Max Velos per spend (default: 5)")
    parser.add_argument("--interval", type=float, default=15.0, help="Seconds between spends (default: 15)")
    parser.add_argument("--duration", type=int, default=0, help="Stop after N seconds (0=infinite)")
    args = parser.parse_args()

    if args.amount < 1 or args.amount_max < args.amount:
        print("ERROR: invalid amount range")
        return 1

    _bootstrap_django()

    if args.list:
        return _list_players()
    return run_loop(args)


if __name__ == "__main__":
    raise SystemExit(main())
