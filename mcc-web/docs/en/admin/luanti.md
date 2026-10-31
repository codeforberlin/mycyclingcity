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

- **Two-step access:** (1) Luanti client login with **username + password** from MCC, (2) then **session grant** (player stays frozen until RFID/Admin starts a session).
- No self-registration on the server; passwords only in MCC Admin (not in the Luanti client).
- Start sessions from Admin or RFID: `POST /api/luanti/counter/scan/`
- Modes: `play` / `build` / `watch` (privileges + separate play/build inventories)

### Accounts (list and detail)

Under **Luanti → Accounts**:

- **List:** filter by **TOP group** (same as Sessions), text search (login, RFID, display name), active/inactive status, 25 rows per page. Superusers also get **No TOP** filter.
- **Create** stays at the top of the list; home TOP is pre-selected when a TOP filter is active.
- **Edit** opens the **detail page** per account (wallet, session duration, flags, password).

### Login passwords (Luanti client)

- Passwords are managed **only** in MCC and mirrored to the Luanti server via `SET_PASSWORD`. **“Provisioned on server”** (`password_provisioned`) is set only after a bridge ACK.
- After deploy or world restore: `python manage.py provision_all_luanti_passwords` (bridge must be running).
- Unknown / unprovisioned names: client disconnect reason explains central MCC account management. **Wrong password:** standard Luanti client message (engine default).
- Recommended in `minetest.conf`: `enable_player_registration = false`; optional `motd` pointing to MCC account management.
- **Superuser:** all accounts; view and set passwords.
- **Luanti admin** (`luanti_admin`): view/set only for accounts whose home TOP (`assigned_to_group`) is among the user's **managed TOP groups** (`User.managed_groups`, root groups).
- Permissions: `view_luanti_login_password`, `set_luanti_login_password` (included in preset group `luanti_admin`).
- After migrations that add Luanti permissions, run `python manage.py setup_luanti_preset_groups` (`utils/deploy_production.py` runs this after `migrate`).
- After create/reset, the password is shown **once** in an admin message; use “Reveal” (AJAX) later.
- Audit: `reveal` / `reset` / `create` logged under `luanti.password` **without** the secret.

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
