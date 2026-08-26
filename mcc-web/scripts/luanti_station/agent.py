#!/usr/bin/env python3
# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Luanti station agent: pull desired config from Django and write a launcher script.

Usage:
  export MCC_STATION_URL=https://mcc.example/api/luanti/station/config/
  export MCC_STATION_KEY=<api_key>
  python3 agent.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request

URL = os.environ.get("MCC_STATION_URL", "http://127.0.0.1:8000/api/luanti/station/config/")
KEY = os.environ.get("MCC_STATION_KEY", "")
POLL = int(os.environ.get("MCC_STATION_POLL", "30"))
LAUNCHER = os.environ.get(
    "MCC_STATION_LAUNCHER",
    os.path.expanduser("~/.local/bin/mcc-luanti-launch.sh"),
)
LUANTI_BIN = os.environ.get("MCC_LUANTI_BIN", "luanti")


def fetch_config() -> dict:
    req = urllib.request.Request(URL, headers={"X-Station-Key": KEY})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def write_launcher(cfg: dict) -> None:
    server = cfg.get("server") or {}
    account = cfg.get("account") or {}
    address = server.get("address", "127.0.0.1")
    port = int(server.get("port", 30000))
    name = account.get("login_name") or ""
    password = account.get("password") or ""
    os.makedirs(os.path.dirname(LAUNCHER), exist_ok=True)
    content = f"""#!/bin/bash
exec {LUANTI_BIN} --address {address} --port {port} --name {name} --password {password} --go
"""
    with open(LAUNCHER, "w", encoding="utf-8") as fh:
        fh.write(content)
    os.chmod(LAUNCHER, 0o700)


def report(reported: dict, error: str = "") -> None:
    body = json.dumps({"reported": reported, "error": error}).encode("utf-8")
    req = urllib.request.Request(
        URL,
        data=body,
        headers={
            "X-Station-Key": KEY,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        resp.read()


def main() -> int:
    if not KEY:
        print("MCC_STATION_KEY required", file=sys.stderr)
        return 1
    while True:
        try:
            cfg = fetch_config()
            if not cfg.get("ok"):
                time.sleep(POLL)
                continue
            write_launcher(cfg)
            report({"launcher": LAUNCHER, "account": (cfg.get("account") or {}).get("login_name")})
        except Exception as exc:  # noqa: BLE001
            try:
                report({}, error=str(exc))
            except Exception:
                pass
            print(f"agent error: {exc}", file=sys.stderr)
        time.sleep(POLL)


if __name__ == "__main__":
    raise SystemExit(main())
