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
- Modes: `play` / `plan` / `build` / `watch` (privileges + separate inventories per mode: play, plan, build)

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

**Tab order in `/mccshop`:** categories are sorted alphabetically by **localized tab title** (client language / catalog `lang`), not by DB `sort_order`. `sort_order` still applies to Admin lists and Shop Ops.

**`/mccshop` search:** with a filter text, all categories are searched (display name, all labels, `item_name`).

Nodes (`kind=node`) default to stack size 64.

Optional first step: **Import Minecraft shop** (mirrors MC categories/prices; does not cover every Mineclonia mod).

**Shop vs session mode:**

| Mode | `/mccshop` |
|------|------------|
| **Play** / **Watch** | Catalog view only (no buy/sell) |
| **Plan** | Plan buys (0 Velos); tabs **Plan** / **Remove**; in-world **holograms only** (no dig/place of real blocks) |
| **Build** | Real buys + sell (purchase credit) + **Umwandeln** tab (holograms, plan pool, auto-convert) |

## Plan mode (holograms / convert)

- **Ingame shop (kid-facing DE copy):** plan session explains holograms / 0 Velos; wallet line **Kauf später von:** (“debited later”). Browse without release: friendly hint instead of admin jargon.
- **Shop wallet** (`Velos:` in `/mccshop`) = spendable Velos on the resolved group. In **build** mode, to the right of the **Sell** tab: **Abbuchung:** / **Gutschrift:** plus wallet group name per tab (same group). An active **session** may pin `wallet_group` (Admin session control).
- **Manual materialization** (`/mccshop` → **Umwandeln**, `/mccplan convert`) debits in order: (1) **converting player’s shop wallet** (session), even if not listed in admin plan funding groups; (2) the region **plan Velo pool**. Plan summary field `available_convert_velos` includes pool plus non-pool wallet velos for the button enable logic.
- **Auto / live conversion** (cycling, admin START, no player button): **plan pool only** — no actor-wallet-first rule.
- **Sell credit after convert:** binary rule — **100% from actor wallet** on manual convert → purchase credit on **that group**; **any** plan-pool velo in the mix → credit on **regional effective TOP**. Incentivizes self-funding; no proportional split. Admin materialize transactions log `credit_group`.
- Direct build buy/sell still uses the shop wallet. Cycling must credit Velos to a plan funding group for pool-backed converts.
- **Sell own purchase credit only (TOP lock):** Admin → **Groups** → TOP group → **Luanti Shop** → **Luanti: Verkauf nur eigenes Kaufguthaben (TOP)**. When enabled, child groups cannot use the TOP wallet’s purchase credit for sells (only credit on their own shop wallet). Default off (pooled TOP credit allowed as today). Use when several groups build together to prevent “sell using TOP credit, book Velos to our group”. Ingame tooltip: *TOP-Pool für eure Gruppe gesperrt* (DE UI).

### Convert — kid-friendly explanation (DE UI strings)

The ingame **Umwandeln** tab uses German copy aimed at children: own wallet first, then plan pool; sell credit goes to your group only if you paid the full block price yourself, otherwise regional TOP — see German section in `docs/de/admin/luanti.md` for the full story parents can read aloud.
- Session **Plan**: hologram shop items; placement only in assigned build regions. **Real** nodes cannot be dug or placed in plan — **holograms only**. Real digging/building: **Build** session. Unplaced plan items: **`/mccshop` → Remove`**; or `/mccplan discard hand|all`. Placed holograms: dig, `/mccplan remove`, `/mccplan clear`.
- **Tunnel/road (staff):** (1) **Build** — dig out, (2) **Plan** — place holograms, (3) **Build** — buy or convert (Velos).
- **Plan holograms (recognition):** shape previews keep the real block texture (semi-transparent), not a uniform cyan tint. Inventory tooltip and block `infotext` use the **shop display name**. Optional client settings in `minetest.conf` / `luanti.conf`: `mcc_plan.holo_opacity` (default 165), `mcc_plan.holo_colorize_alpha` (0 = off), `mcc_plan.holo_border` (default `false`, optional edge highlight).
- `/mccplan convert [n]` — manual convert (max 256 per call), **build session only**, when the pool has Velos.
- **`/mccplan autoconvert on`** — **build** session: polls every 5s (configurable) and converts up to 4 blocks when pool Velos arrive (cycling).
- **`/mccplan autoconvert off`** — stop the loop.
- **`/mccplan autoconvert`** — status on/off (also shown in `summary`).
- HUD (build mode): pool; prefix `Auto-Umw. ·` when auto-convert is on.
- **Planning commands** (`/mccplan on|off|remove|clear|…`) — **plan** session only; **materialize** (`convert`, `autoconvert on`) — **build** session only (`autoconvert off` anytime).
- **Live conversion (Admin):** `Admin → Luanti → Protected regions` → **start/stop live conversion** per zone. The server materializes holograms as plan-pool Velos arrive (cycling). Use when children planned in build and grandparents pedal while others watch in play/watch — **no** ingame `/mccplan autoconvert on`.
- Tick: on `apply_velos_earn` and in **`mcc_worker`** / optional `python manage.py luanti_plan_live_convert_tick` (cron). Master switch `LUANTI_PLAN_AUTO_CONVERT_ENABLED`; batch size `LUANTI_PLAN_LIVE_CONVERT_MAX_BLOCKS_PER_TICK` (default 4).
- Without Admin **START**, no server-side auto conversion for that zone (only manual `/mccplan convert` in build or ingame autoconvert).

### Diagnosing Velo deductions (plan buy vs. convert)

If Velos leave the wallet when buying in plan mode:

1. **Admin → Luanti → Shop transactions** — filter by player (`login_name`) and time.
   - **Plan buy** (`plan_buy`) with `velos_delta=0`: purchase was correct; the debit came from **materialization** or the **plan Velo pool**.
   - **Buy** (`buy`) with a negative delta: the client did not send `planning` (checkbox off, `/mccbuy` without plan mode, or `mcc_plan` not loaded).
2. **Admin → Luanti → Plan materialize transactions**: each row is one converted hologram; a negative `velos_delta` debits the pool.
3. **Admin → Luanti → Protected regions** → **plan funding groups**: if the session wallet is in that pool, shop `Velos:` drops on convert — configuration, not a plan-buy bug.
4. In-game: check plan vs build session, `mcc_plan` mod loaded.

## Bridge (Lua)

Repo path: `mcc-web/luanti_mod/mcc_bridge/`

Deploy:

Production: mod **files** at `/data/appl/mcc/mcc-web/luanti_mod/` (`sync_luanti_mod.sh`). Game dir: symlinks only (`link_luanti_mods.sh`).

```bash
MCC_WEB_DIR=/data/appl/mcc/mcc-web /data/appl/mcc/mcc-web/scripts/sync_luanti_mod.sh
MCC_WEB_DIR=/data/appl/mcc/mcc-web /data/appl/mcc/mcc-web/scripts/link_luanti_mods.sh
```

Manual (only if needed):

```bash
ln -sfn /data/appl/mcc/mcc-web/luanti_mod/mcc_bridge /data/games/mcc/luanti/games/mycyclingcity/mods/mcc_bridge
```

In `minetest.conf`:

```
secure.http_mods = mcc_bridge
mcc_bridge.base_url = http://127.0.0.1:8000
mcc_bridge.server_id = luanti-1
mcc_bridge.shared_secret = <same as MCC_LUANTI_HTTP_SHARED_SECRET>
```

Optional debug trace (server `luanti-server.log`; default off):

```
mcc_bridge.debug = session,shop
mcc_bridge.debug_heartbeat = false
```

Restart Luanti after changing these settings. Filter: `grep mcc_bridge:debug luanti-server.log`.

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

## Game mycyclingcity

The game lives at `/data/games/mcc/luanti/games/mycyclingcity`, not in git. Base mods (`default`, `stairs`, `wool`, `doors`, `walls`, `beds`, `vessels`, `xpanes`, `worldedit`, `areas`) are copies. `mcc_bridge`, `mcc_plan`, and `mcc_texture_painter` are symlinks to `mcc-web/luanti_mod/` (`link_luanti_mods.sh`). `mcc_migrator` lives only under `worlds/<copy>/worldmods/` during conversion (not in the `mycyclingcity` game tree).

The target world is `/data/games/mcc/luanti/worlds/mycyclingcity_prod`. Create once: `world.mt` as below, then run `luantiserver --world …/mycyclingcity_prod --config …/scripts/minetest_prod.conf` briefly (creates `map.sqlite`). Normal start:

```bash
MCC_LUANTI_WORLD=mycyclingcity_prod \
MCC_LUANTI_CONFIG=/data/appl/mcc/mcc-web/scripts/minetest_prod.conf \
/data/appl/mcc/mcc-web/scripts/luanti_server.sh restart
```

Its `world.mt`:

```
gameid = mycyclingcity
mg_name = singlenode
mg_flags = nocaves, nodungeons, light, nodecorations, nobiomes, noores
```

DEV and cbm-srv1 have different maps and Django data. Run the same steps on each host. Do not copy the mapping file across.

1. Back up the world and the database.
2. Working copy `worlds/mycyclingcity_migrate` with `gameid = mineclonia` in `world.mt` (MCC mods off). In `worldmods/` only symlink `mcc_migrator` — do **not** load MTG mods beside Mineclonia (alias/ABM crash). Target nodes are stub-registered by `mcc_migrator`. Remove `worldmods/__mc2mt`. After failed runs, **re-copy the world from backup**.
3. `/scan_mcl x1 y1 z1 x2 y2 z2`. Unknown names block until `mcl_map.py` and `map.lua` match.
4. `/convert_mcl x1 y1 z1 x2 y2 z2` (VoxelManip, not LBM/`/emergeblocks`). Run `/scan_mcl` again until zero `mcl_*` in the box. **Every block looks like stone here** — `mcc_migrator` registers MTG target names as texture stubs only (Mineclonia cannot load real MTG). `map.sqlite` still stores the target itemstrings. Judge visuals only after step 6 in `mycyclingcity_prod`.
5. Remove `worldmods/mcc_migrator`. Keep `mcc_migrator_map.json`.
6. WorldEdit `//save` (signs and metadata) or `//mtschemcreate`. Import into `worlds/mycyclingcity_prod` at the same coordinates, then `//fixlight`.
7. `python manage.py luanti_convert_from_mineclonia --world mycyclingcity_prod`, then again with `--apply`.
8. Set `MCC_LUANTI_WORLD=mycyclingcity_prod` only after a visual check. The old world stays as an archive.
