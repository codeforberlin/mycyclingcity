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
- Bridge-Heartbeat (Mod ↔ Django): auf Control gilt die Bridge nur als **online**, wenn der **Luanti-Server-Prozess läuft** und zuletzt ein Heartbeat kam. Nach **Server stoppen** setzt Django die Bridge-Einträge zurück (sofort offline, nicht erst nach Heartbeat-Timeout).

Skript: `scripts/luanti_server.sh` (PID unter `/data/var/mcc/tmp/luanti-server.pid`).

## Auth & Sessions

- **Zweistufiger Zugang:** (1) Luanti-Client-Login mit **Benutzername + Passwort** aus MCC, (2) danach **Session-Freigabe** (Spieler bleibt eingefroren bis RFID/Admin eine Session startet).
- Keine Self-Registration am Server: Accounts nur in der Admin-GUI anlegen; Passwortänderung nur in MCC (nicht im Luanti-Client).
- Session-Start per Admin oder RFID: `POST /api/luanti/counter/scan/`
- Modi: `play` / `build` / `watch` (Privs + getrenntes Inventar play/build)

### Betrieb vor Ort: Passwort vs. Session-Freigabe

Das Login-Passwort ist ein **technisches Hilfsmittel** (Anmeldung am Server, kein Wildwuchs an Accounts). Die **eigentliche Nutzungsfreigabe** ist immer die **Session** durch Erwachsene (Admin oder RFID).

| Stufe | Bedeutung |
|-------|-----------|
| **Login** (Name + Passwort aus MCC) | Spieler ist auf dem Server, aber ohne Session **eingefroren** (Warte modus). |
| **Session-Freigabe** | Spielen/Bauen/Zeit/Modus — nur nach Start durch Betreuer. |

Nach dem Start (Admin **Start** oder RFID) sendet Django **`SESSION_STARTED`** an die Bridge; der Mod fordert sofort `/api/luanti/session/join/` an (veraltete HTTP-Antworten werden ignoriert). Der Spieler sollte **ohne Reconnect** innerhalb von Sekundenbruchteilen freigegeben werden, sobald die Bridge erreichbar ist.

**Praktische Folgen für Schulen / vor Ort:**

- **Einfache, gut lesbare Passwörter** sind in Ordnung (z. B. kurz, pro Gruppe gleich). Geheimhaltung **vor Kindern im Raum** ist **kein** Sicherheitsziel — wer das Passwort kennt, kann ohne laufende Session trotzdem nicht sinnvoll spielen.
- Passwort **dürfen** an Aushang, Whiteboard oder mündlich durch Erwachsene weitergegeben werden; Alternativ tippt ein Betreuer beim Luanti-Client mit.
- Der **Luanti-GUI-Client speichert Passwörter in der Regel nicht dauerhaft** (Engine-Standard). Wiederholtes Eingeben ist lästig, aber **kein** Sicherheitsproblem. Stationen können das Passwort automatisch übergeben (`scripts/luanti_station/`).
- Admin-Rechte zum **Anzeigen/Setzen** von Passwörtern dienen der **Operator-Trennung** (TOP, Rollen, Fern-Admin), nicht dem „Verstecken vor Kindern“.

### Accounts (Listen- und Detailansicht)

Unter **Luanti → Accounts**:

- **Liste:** Filter nach **TOP-Gruppe** (wie bei Sessions), Textsuche (`Login`, RFID, Anzeigename), Status aktiv/inaktiv, Seiten à 25 Einträge. Superuser: zusätzlich Filter **Ohne TOP**.
- **Anlegen** bleibt oben auf der Liste; Heimat-TOP wird vorausgewählt, wenn ein TOP-Filter aktiv ist.
- **Bearbeiten** öffnet die **Detailseite** pro Account (Wallet, Session-Dauer, Flags, Passwort).

### Login-Passwörter (Luanti Client)

- Passwörter werden **ausschließlich** in MCC verwaltet und per Bridge (`SET_PASSWORD`) auf den Luanti-Server gespiegelt. Status **„Auf Server gesetzt“** (`password_provisioned`) erst nach Bridge-ACK.
- Nach Deploy oder Welt-Restore: `python manage.py provision_all_luanti_passwords` (Bridge muss laufen).
- Unbekannte / nicht provisionierte Namen: Client sieht einen **Abbruch-Hinweis** (Registrierung deaktiviert, zentral in MCC). **Falsches Passwort:** Standard-Meldung des Luanti-Clients (vom Engine, nicht anpassbar).
- Empfohlen in `minetest.conf`: `enable_player_registration = false`; optional `motd` mit Hinweis auf zentrale Account-Verwaltung.
- **Superuser:** alle Accounts, Anzeigen und Setzen.
- **Luanti Admin** (`luanti_admin`): Anzeigen/Setzen nur für Accounts der **Heimat-TOP** (`assigned_to_group`), die in den **Manager-Gruppen** des Users (`User.managed_groups`, TOP-Wurzeln) liegt.
- Berechtigungen: `view_luanti_login_password`, `set_luanti_login_password` (in Preset-Gruppe `luanti_admin` enthalten).
- Nach Migrationen mit neuen Luanti-Rechten: `python manage.py setup_luanti_preset_groups` (wird von `utils/deploy_production.py` nach `migrate` mit ausgeführt).
- Nach dem Anlegen/Neu-Setzen erscheint das Passwort **einmalig** in einer Admin-Meldung zum Kopieren; dauerhaft über „Anzeigen“ (AJAX).
- Audit: Aktionen `reveal` / `reset` / `create` werden geloggt (`luanti.password`), **ohne** Passwort im Log.

## Shop (Velos-Katalog)

Unter **Luanti → Shop** (`/admin/luanti/shop-ops/`). Berechtigung: `luanti.access_luanti_shop` (Preset-Gruppe `luanti_admin` u. a.).

**Ziel:** Fehlende Mineclonia-Items aus der Live-Registry in den Luanti-Shop übernehmen — ohne jeden Itemstring einzeln in „Shop-Artikel“ anzulegen.

1. Luanti-Server und Bridge laufen → **Registry vom Server aktualisieren** (Dump von `core.registered_items` in `LuantiRegisteredItem`).
2. Filter **Nur fehlende** (Standard): zeigt Itemstrings, die noch in keiner Shop-Kategorie vorkommen. Oben: Anzahl fehlender Einträge gesamt und pro Mod-Chip (`+N`).
3. Optional Mod-Chip oder Suche (z. B. `mcl_fencing`) einschränken.
4. **Ziel-Kategorie:** bestehende wählen oder **Neu anlegen** (Slug, Anzeigename, Sortierung).
5. **Kaufpreis (Velos)** setzen, dann eine Massenaktion:
   - **Auswahl in Shop übernehmen** — markierte Zeilen in der Liste (Anzeige-Limit 200);
   - **Alle fehlenden von Mod … übernehmen** — serverseitig alle fehlenden des aktiven Mods (Limit `LUANTI_SHOP_BULK_MOD_MAX`, Default 500 in `settings.py`);
   - **Alle fehlenden im Filter übernehmen** — wenn der aktuelle Filter ≤ Limit Treffer hat.
6. Im Spiel `/mccshop` oder Shop-GUI stichprobenartig prüfen.

Anzeigenamen werden in **`LuantiShopItemLabel`** pro Sprachcode gepflegt (zuerst **de**, **en**). Bulk-Import legt **de** aus der Registry an.

**Mehrsprachige Namen:**

- **DE-Labels aus Mineclonia-Locales** (empfohlen zuerst) — matcht Registry-/Legacy-EN-Text gegen `locale/*.de.tr`; Shop Ops oder `python manage.py sync_luanti_shop_labels --lang de --source locales`
- **DE-Labels aus Registry** — Plain-Text aus `LuantiRegisteredItem.description` (oft Englisch, füllt Lücken); `--lang de` / `--source registry` oder `--source both`
- **EN-Labels aus Mineclonia** — invertiert dieselben `*.de.tr`-Dateien; Pfad **`MCC_LUANTI_LOCALE_ROOT`**; `--lang en`
- Shop Ops zeigt **DE/EN-Anzeigenamen** pro Artikel und **Shop-Suche** wie ingame (`holz` über alle Kategorien)
- Manuell: Shop-Artikel im Admin → Inline „Shop-Artikel-Übersetzungen“

Im Spiel: **Luanti-Client-Sprache** steuert Menü (`mcc_bridge` `.tr`), **Kategorie-Titel** und **Artikelnamen** (Bridge sendet `lang` an `/api/luanti/shop/catalog/`). Fallback: angefragte Sprache → de → en → gespeicherter Name.

**Kategorie-Titel (Tabs):** `LuantiShopCategoryLabel` (de/en). Shop Ops: **Kategorie-Titel DE/EN (Slug-Vorschläge)** oder `python manage.py sync_luanti_shop_labels --categories`. Gängige Slugs (`blocks`, `tools`, …) werden automatisch deutsch benannt (z. B. „Blöcke“, „Werkzeuge“); Anpassung im Admin unter Shop-Kategorien → Inline Übersetzungen.

**Suche im `/mccshop`:** mit gesetztem Suchtext alle Kategorien; Treffer in Anzeigename, allen Labels und `item_name`.

Knoten (`kind=node`) erhalten standardmäßig Stack 64.

Optional vorher: **Minecraft-Shop importieren** (spiegelt MC-Kategorien/Preise; deckt nicht alle Mineclonia-Mods ab).

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
