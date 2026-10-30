# Luanti-Integration (Admin)

## Übersicht

Die App `luanti` steuert einen Luanti-/Mineclonia-Server über HTTP und optional WebSocket.
Minecraft bleibt parallel unter dem Menü **Minecraft**.

## Menü

Unter `/admin/` → **Luanti** (rollenbasiert):

- Control
- Accounts
- Sessions
- Shop
- Stadtsteuerung
- Arena / Loren
- Stationen

## Control (Server-Prozess)

Unter **Luanti → Control**:

- **Server starten / stoppen / neu starten**
- Status und Link zum Log (`luanti-server.log`)
- Bridge-Heartbeat (Mod ↔ Django)

Skript: `scripts/luanti_server.sh` (PID unter `/data/var/mcc/tmp/luanti-server.pid`).

## Auth & Sessions

- Keine Self-Registration: Accounts in der Admin-GUI anlegen.
- Session-Start per Admin oder RFID: `POST /api/luanti/counter/scan/`
- Modi: `play` / `build` / `watch` (Privs + getrenntes Inventar play/build)

### Accounts (Listen- und Detailansicht)

Unter **Luanti → Accounts**:

- **Liste:** Filter nach **TOP-Gruppe** (wie bei Sessions), Textsuche (`Login`, RFID, Anzeigename), Status aktiv/inaktiv, Seiten à 25 Einträge. Superuser: zusätzlich Filter **Ohne TOP**.
- **Anlegen** bleibt oben auf der Liste; Heimat-TOP wird vorausgewählt, wenn ein TOP-Filter aktiv ist.
- **Bearbeiten** öffnet die **Detailseite** pro Account (Wallet, Session-Dauer, Flags, Passwort).

### Login-Passwörter (Luanti Client)

- Passwörter werden in MCC verwaltet und an den Luanti-Server (`SET_PASSWORD`) übergeben.
- **Superuser:** alle Accounts, Anzeigen und Setzen.
- **Luanti Admin** (`luanti_admin`): Anzeigen/Setzen nur für Accounts der **Heimat-TOP** (`assigned_to_group`), die in den **Manager-Gruppen** des Users (`User.managed_groups`, TOP-Wurzeln) liegt.
- Berechtigungen: `view_luanti_login_password`, `set_luanti_login_password` (in Preset-Gruppe `luanti_admin` enthalten).
- Nach Migrationen mit neuen Luanti-Rechten: `python manage.py setup_luanti_preset_groups` (wird von `utils/deploy_production.py` nach `migrate` mit ausgeführt).
- Nach dem Anlegen/Neu-Setzen erscheint das Passwort **einmalig** in einer Admin-Meldung zum Kopieren; dauerhaft über „Anzeigen“ (AJAX).
- Audit: Aktionen `reveal` / `reset` / `create` werden geloggt (`luanti.password`), **ohne** Passwort im Log.

## Bridge (Lua)

Mod-Pfad im Repo: `mcc-web/luanti_mod/mcc_bridge/`

Deploy:

```bash
ln -sfn /path/to/mcc-web/luanti_mod/mcc_bridge /data/games/mcc/luanti/mods/mcc_bridge
```

In `minetest.conf`:

```
secure.http_mods = mcc_bridge
mcc_bridge.base_url = http://127.0.0.1:8000
mcc_bridge.server_id = luanti-1
mcc_bridge.shared_secret = <gleich wie MCC_LUANTI_HTTP_SHARED_SECRET>
```

## Settings

```env
MCC_LUANTI_WS_ENABLED=True
MCC_LUANTI_HTTP_SHARED_SECRET=...
MCC_LUANTI_ALLOWED_SERVER_IDS=luanti-1
```

## Gruppen

`python manage.py setup_luanti_preset_groups` → `luanti_admin`, `luanti_moderator`

## Stationen

Linux-Agent: `mcc-web/scripts/luanti_station/agent.py`  
Config-Pull: `GET/POST /api/luanti/station/config/` mit Header `X-Station-Key`.
