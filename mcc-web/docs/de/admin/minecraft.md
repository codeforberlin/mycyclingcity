# Minecraft-Integration - Dokumentation

## Übersicht

Das Minecraft-Modul synchronisiert **Gruppen-Velos** zwischen MyCyclingCity und einem Minecraft-Server. Leaf-Gruppen mit `mc_username` werden über RCON-Scoreboards und optional WebSocket gespiegelt.

## Hauptfunktionen

### 1. Gruppen-Velos-Synchronisation

- **MyCyclingCity → Minecraft**: Earn/Admin-Updates landen in der Outbox und setzen Scoreboards
- **Minecraft → MyCyclingCity**: Ausgaben per WebSocket reduzieren `Group.velos_spendable`
- **Scoreboards**: `group_velos_total` und `group_velos_spendable` (konfigurierbar)

### 2. RCON-Kommunikation

- Scoreboard-Objectives anlegen und Spieler-Scores setzen
- Health-Checks und manuelle Tests über Admin-GUI

### 3. Outbox-Pattern

- Asynchrone Verarbeitung mit Retry und TTL-Cleanup
- Event-Typen: `update_group_velos`, `sync_all` (Legacy: `update_player_coins` wird übersprungen)

### 4. WebSocket-Support

- Signierte Events vom Minecraft-Plugin
- `SPEND_GROUP_VELOS` (Legacy-Alias: `SPEND_COINS`)
- `GET_TEAM_VELOS`
- `SYNC_SHOP_CATALOG`
- `HEARTBEAT` (Präsenz für Admin Shop-Push; aktualisiert `last_seen`)

### 5. Snapshot-System

- Periodisches Einlesen der Gruppen-Scoreboards
- Optional: `velos_spendable` in der DB aus dem Scoreboard zurückschreiben

## Konfiguration (Online-Mode)

```env
# Paper RCON
MCC_MINECRAFT_RCON_HOST=127.0.0.1
MCC_MINECRAFT_RCON_PORT=25575
MCC_MINECRAFT_RCON_PASSWORD=...

# Velocity / Velocircon
MCC_MINECRAFT_VELOCITY_RCON_HOST=127.0.0.1
MCC_MINECRAFT_VELOCITY_RCON_PORT=25576
MCC_MINECRAFT_VELOCITY_RCON_PASSWORD=...
MCC_MINECRAFT_VELOCITY_PAPER_SERVER=mycyclingcity
MCC_MINECRAFT_VELOCITY_LIMBO_SERVER=limbo

# online (Default) | authme (Legacy)
MCC_MINECRAFT_SESSION_AUTH_MODE=online
MCC_MINECRAFT_LP_SYNC_ENABLED=False
```

Siehe auch: [`docs/de/guides/minecraft_online_mode_migration.md`](../guides/minecraft_online_mode_migration.md)

## Konfiguration

```env
# RCON
MCC_MINECRAFT_RCON_HOST=127.0.0.1
MCC_MINECRAFT_RCON_PORT=25575
MCC_MINECRAFT_RCON_PASSWORD=ihr-rcon-passwort

# Gruppen-Velos-Scoreboards (aktiv)
MCC_MINECRAFT_SCOREBOARD_GROUP_VELOS_TOTAL=group_velos_total
MCC_MINECRAFT_SCOREBOARD_GROUP_VELOS_SPENDABLE=group_velos_spendable

# Legacy (nicht mehr verwendet)
MCC_MINECRAFT_SCOREBOARD_COINS_TOTAL=player_coins_total
MCC_MINECRAFT_SCOREBOARD_COINS_SPENDABLE=player_coins_spendable

MCC_MINECRAFT_WORKER_POLL_INTERVAL=1
MCC_MINECRAFT_RCON_HEALTH_INTERVAL=30
MCC_MINECRAFT_SNAPSHOT_INTERVAL=60
MCC_MINECRAFT_SNAPSHOT_UPDATE_DB_SPENDABLE=True

MCC_MINECRAFT_OUTBOX_DONE_TTL_DAYS=7
MCC_MINECRAFT_OUTBOX_FAILED_TTL_DAYS=30
MCC_MINECRAFT_OUTBOX_MAX_EVENTS=50000

MCC_MINECRAFT_WS_ENABLED=False
MCC_MINECRAFT_WS_SHARED_SECRET=ihr-geheimer-schlüssel
MCC_MINECRAFT_WS_ALLOWED_SERVER_IDS=server1,server2
```

## Admin GUI

Unter `/admin/` → App **Minecraft** (rollenbasiert, nicht nur Superuser):

- Worker- und Snapshot-Steuerung (Control)
- Manuelle Aktionen: Sync, Snapshot, RCON-Test, Cleanup
- **Gruppen-Tabelle**: DB-Werte vs. Scoreboard-Snapshot pro `mc_username`
- **Account-Management** (`/admin/minecraft/accounts/`): Anlegen/Bearbeiten/Löschen von Spieler-Accounts, Registrieren/Deaktivieren/Reaktivieren von Bau-Accounts, TOP-Filter, Vanilla-`/op`/`/deop`, temporäre Liste **Limbo ohne Account** (Velocity-Live, nicht persistiert)
- **Spieler-Sessions** / **Bau-Sessions**: Session-Start, Kick, Zeit verlängern (eigene Permissions)

Die alten Menü-Kacheln „Spieler-Accounts“ / „Bau-Accounts“ erscheinen nur noch als Fallback, wenn `manage_minecraft_accounts` fehlt.

### Berechtigungen (Auswahl)

| Permission | Zweck |
|------------|--------|
| `manage_player_sessions` | Spieler-Sessions (z. B. `minecraft_moderator` / FEZitty-Betrieb) |
| `manage_builder_sessions` | Bau-Sessions und klassische Bau-Accounts-Liste |
| `manage_minecraft_accounts` | Stammdaten Spieler + Bau in Minecraft-Accounts |
| `manage_minecraft_operators` | Vanilla-OP zuweisen/entziehen (`ops.json` + RCON) |

`minecraft_moderator` erhält absichtlich **keine** Account-/OP-Permissions — nur Sessions und Stadt/Arena. Setup: `python manage.py setup_minecraft_preset_groups`.

### Vanilla-Operatoren

OP-Status kommt aus `ops.json` unter `MCC_MINECRAFT_PAPER_DIR` (Vanilla hat keinen List-Befehl). Zuweisen/Entziehen läuft per RCON `op` / `deop` und wird in `MinecraftVanillaOpLog` protokolliert.

## Datenmodelle

### MinecraftOutboxEvent

- `update_group_velos` – Scoreboard-Update für eine Gruppe
- `sync_all` – alle Gruppen mit `mc_username`
- `update_player_coins` – deprecated, Worker markiert als erledigt ohne Aktion

### MinecraftPlayerScoreboardSnapshot

- `player_name` – Minecraft-Name (= `Group.mc_username`)
- `group` – Verknüpfung zur Leaf-Gruppe
- `velos_total`, `velos_spendable` – letzter RCON-Stand

## WebSocket

Endpunkt: `ws://your-domain/ws/minecraft/events/`

```json
{
  "type": "SPEND_GROUP_VELOS",
  "player": "GruppenMcName",
  "amount": 100,
  "server_id": "server1",
  "signature": "hmac-signatur"
}
```

Antwort bei Erfolg: `{"status": "ok"}`

## Gruppen-Verknüpfung

1. **MCC Core API & Models** → **Gruppe** (Leaf-Gruppe)
2. Feld `mc_username` setzen (Minecraft-Teamname)
3. Nach Earn oder manuellem Sync werden Velos an den Server gepusht

## Workflow

**Earn → Minecraft:** VelosEarn → Outbox `update_group_velos` → Worker → RCON → Snapshot

**Ausgabe in Minecraft:** Plugin → WebSocket `SPEND_GROUP_VELOS` → `velos_spendable` − amount → Outbox → Scoreboard-Update

## RFID-Scan (MCC-Counter)

Geräte starten Play-Sessions über:

`POST /api/mcc-counter/scan/` mit Header `X-Api-Key` und JSON `{"token": "Arena1"}` (Aliase: `id_tag`, `rfid`).

Der Token wird gegen aktive `MinecraftPlayAccount`-Einträge (`id_tag` oder `short_name`) aufgelöst und startet eine Session mit Quelle `rfid`. Operator-Tag-Reset über `/api/get-user-id` bleibt unverändert.

## Fehlerbehebung

- Outbox und Worker-Logs prüfen (`logs/minecraft.log`)
- RCON-Test in der Admin-GUI
- Gruppe muss `mc_username` haben
- Scoreboard-Namen in `.env` mit Server-Objectives abgleichen

## Verwandte Dokumentation

- [Admin GUI Handbuch](index.md)
- [Velo-Arena Scoreboard-Modi (Bau vs. Spectator / TOP 3)](../guides/velo_arena_scoreboard_modes.md)
- [Velocity & Limbo Admin-Steuerung](../guides/minecraft_proxy_admin.md)
- [Online-Mode Migration](../guides/minecraft_online_mode_migration.md)
- Test-Harness: `mcc-web/test/velo_arena_race/`
