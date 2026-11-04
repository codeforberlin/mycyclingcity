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
- Bridge heartbeat (mod ↔ Django): on Control, the bridge is **online** only when the **Luanti server process is running** and a recent heartbeat was received. After **stop server**, Django clears bridge rows (offline immediately, not after the heartbeat stale window).

Script: `scripts/luanti_server.sh` (PID under `/data/var/mcc/tmp/luanti-server.pid`).

## Auth & sessions

- **Two-step access:** (1) Luanti client login with **username + password** from MCC, (2) then **session grant** (player stays frozen until RFID/Admin starts a session).
- No self-registration on the server; passwords only in MCC Admin (not in the Luanti client).
- Start sessions from Admin or RFID: `POST /api/luanti/counter/scan/`
- Modes: `play` / `build` / `watch` (privileges + separate play/build inventories)

### On-site operation: password vs. session grant

The login password is a **technical helper** (server sign-in, no ad-hoc accounts). **Actual play access** is always the **session** started by an adult (Admin or RFID).

| Step | Meaning |
|------|---------|
| **Login** (name + password from MCC) | Player is on the server but **frozen** without an active session (wait mode). |
| **Session grant** | Play/build, time limits, mode — only after staff starts a session. |

After start (Admin **Start** or RFID), Django sends **`SESSION_STARTED`** to the bridge; the mod immediately calls `/api/luanti/session/join/` (stale HTTP responses are ignored). The player should be granted **without reconnect** within a second once the bridge is reachable.

**Practical notes for venues:**

- **Simple, readable passwords** are fine (short, shared per group). **Hiding the password from children in the room** is **not** a security goal — knowing the password does not allow meaningful play without an active session.
- Passwords **may** be posted on a sign, whiteboard, or given verbally by staff; alternatively an adult types at the Luanti client.
- The **Luanti GUI client usually does not persist passwords** (engine default). Re-typing is inconvenient, not a security gap. Stations can inject the password automatically (`scripts/luanti_station/`).
- Admin permissions to **view/set** passwords are for **operator separation** (TOP, roles, remote admin), not for “keeping secrets from children”.

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

## Shop (Velos catalog)

Open **Luanti → Shop** (`/admin/luanti/shop-ops/`). Permission: `luanti.access_luanti_shop`.

**Goal:** Add missing Mineclonia items from the live registry to the Luanti shop in bulk instead of creating each `LuantiShopItem` by hand.

1. With Luanti and the bridge running, **refresh registry** from the server (dump into `LuantiRegisteredItem`).
2. Use **Only missing** (default) to list itemstrings not yet in any shop category. The page shows total missing counts and per-mod badges (`+N`).
3. Narrow with a mod chip or search (e.g. `mcl_fencing`).
4. Pick a **target category** (existing or **create new** with slug, display name, sort order).
5. Set **buy price (Velos)**, then run a bulk action:
   - **Add selection to shop** — checked rows (list display limit 200);
   - **Add all missing from mod …** — server-side for the active mod (cap `LUANTI_SHOP_BULK_MOD_MAX`, default 500 in `settings.py`);
   - **Add all missing in filter** — when the current filter has ≤ cap matches.
6. Spot-check in-game via `/mccshop` or the bridge shop GUI.

Display names live in **`LuantiShopItemLabel`** per language (initially **de**, **en**). Bulk import sets **de** from the registry.

**Multilingual names:**

- **DE from Mineclonia locales** (run first) — matches registry/legacy English to `locale/*.de.tr`; `--lang de --source locales` or `--source both`
- **DE from registry** — plain text from registered item descriptions (often English, fills gaps); `--lang de` / `--source registry`
- **EN from Mineclonia** — inverted same `*.de.tr` files; set **`MCC_LUANTI_LOCALE_ROOT`**; `--lang en`
- Shop Ops lists **DE/EN display names** per item and **shop search** like in-game (`holz` across all categories)
- Manual edits: Shop item admin → inline translations

In-game: **Luanti client language** drives menu strings (`mcc_bridge` `.tr`), **category tab titles**, and **item names** (bridge sends `lang` to `/api/luanti/shop/catalog/`). Fallback: requested → de → en → stored name.

**Category tabs:** `LuantiShopCategoryLabel` (de/en). Shop Ops: **Category titles DE/EN (slug presets)** or `python manage.py sync_luanti_shop_labels --categories`. Common slugs map to German child-friendly titles (e.g. blocks → Blöcke); edit via Shop categories → inline translations.

**`/mccshop` search:** with a filter text, all categories are searched (display name, all labels, `item_name`).

Nodes (`kind=node`) default to stack size 64.

Optional first step: **Import Minecraft shop** (mirrors MC categories/prices; does not cover every Mineclonia mod).

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
