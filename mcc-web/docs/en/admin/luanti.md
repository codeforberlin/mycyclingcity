# Luanti Integration (Admin)

## Overview

The `luanti` app controls a Luanti/Mineclonia server via HTTP and optional WebSocket.
Minecraft remains available under the **Minecraft** menu.

## Menu

Under `/admin/` → **Luanti** (role-based):

- Control
- Accounts
- Sessions
- Shop
- City control
- Arena / carts
- Stations

## Control (server process)

Under **Luanti → Control**:

- **Start / stop / restart server**
- Status and log link (`luanti-server.log`)
- Bridge heartbeat (mod ↔ Django)

Script: `scripts/luanti_server.sh` (PID under `/data/var/mcc/tmp/luanti-server.pid`).

## Auth & sessions

- No self-registration: create accounts in the Admin GUI.
- Start sessions from Admin or RFID: `POST /api/luanti/counter/scan/`
- Modes: `play` / `build` / `watch` (privileges + separate play/build inventories)

## Bridge (Lua)

Repo path: `mcc-web/luanti_mod/mcc_bridge/`

Deploy:

```bash
ln -sfn /path/to/mcc-web/luanti_mod/mcc_bridge /data/games/mcc/luanti/mods/mcc_bridge
```

In `minetest.conf`:

```
secure.http_mods = mcc_bridge
mcc_bridge.base_url = http://127.0.0.1:8000
mcc_bridge.server_id = luanti-1
mcc_bridge.shared_secret = <same as MCC_LUANTI_HTTP_SHARED_SECRET>
```

## Settings

```env
MCC_LUANTI_WS_ENABLED=True
MCC_LUANTI_HTTP_SHARED_SECRET=...
MCC_LUANTI_ALLOWED_SERVER_IDS=luanti-1
```

## Groups

`python manage.py setup_luanti_preset_groups` → `luanti_admin`, `luanti_moderator`

## Stations

Linux agent: `mcc-web/scripts/luanti_station/agent.py`  
Config pull: `GET/POST /api/luanti/station/config/` with header `X-Station-Key`.
