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

**Tab-Reihenfolge im `/mccshop`:** Kategorien alphabetisch nach **lokalisiertem Tab-Titel** (Client-Sprache / Katalog-`lang`), nicht nach DB-`sort_order`. `sort_order` gilt weiter für Admin-Listen und Shop Ops.

**Suche im `/mccshop`:** mit gesetztem Suchtext alle Kategorien; Treffer in Anzeigename, allen Labels und `item_name`.

Knoten (`kind=node`) erhalten standardmäßig Stack 64.

Optional vorher: **Minecraft-Shop importieren** (spiegelt MC-Kategorien/Preise; deckt nicht alle Mineclonia-Mods ab).

## Planmodus (Hologramme / Umwandlung)

- **Shop-Wallet** (`Velos:` im `/mccshop`) = persönliche spendbare Velos.
- **Umwandlung** (`/mccplan convert`, Auto-Umwandlung) belastet den **Plan-Velos-Pool** der Bauzone (Admin: geschützte Region → Plan-Velos-Gruppen). Strampeln muss Velos auf eine dieser Gruppen buchen, nicht nur auf die Shop-Wallet.
- **Verkauf nach Umwandlung:** Purchase Credit liegt auf der **effektiven TOP** der Zone — bei **Master** die dort gewählte TOP; bei **Sub** optional **eigene TOP** (Admin: TOP-Gruppe), sonst TOP der Master. Kinder/Enkel mit Leaf-Wallet können über die Parent-Kette verkaufen; die **Velos-Gutschrift** geht auf die **aktuelle Session-Wallet** des Verkäufers (z. B. Omas Velos finanzieren Umwandeln, die Klasse verkauft wieder und füllt ihr Konto).
- `/mccplan on` — Plan-Käufe (0 Velo beim Kauf); Hologramme setzen.
- `/mccplan convert [n]` — manuelle Umwandlung (max. 256 pro Aufruf), nur wenn der Pool Velos hat.
- **`/mccplan autoconvert on`** — Wartet im Build-Modus auf Pool-Velos (Radfahren) und wandelt fortlaufend Hologramme um (Standard bis 4 Blöcke alle 5 s, `minetest.conf`: `mcc_plan.autoconvert_interval`, `mcc_plan.autoconvert_max_blocks`).
- **`/mccplan autoconvert off`** — stoppt die Schleife.
- **`/mccplan autoconvert`** — Status AN/AUS (auch in `summary`).
- HUD (Build-Modus): Pool und bei Auto-Umw. der Prefix `Auto-Umw. ·`.
- **Alle `/mccplan`-Befehle (außer `autoconvert off`) nur im Build-Modus** — Zuschauer in Spiel/Flugmodus führen kein manuelles Convert aus.
- **Live-Umwandlung (Admin):** `Admin → Luanti → Geschützte Regionen` → **Live-Umwandlung starten/stoppen** pro Zone. Server wandelt Hologramme um, sobald Plan-Pool-Velos ankommen (Radfahren). Ideal wenn Kinder geplant haben und Großeltern strampeln, während andere in Spiel/Flugmodus zuschauen — **ohne** `/mccplan autoconvert on` ingame.
- Beim **Live-Start** im Admin: sofort ein Umwandlungs-Schub, wenn der Plan-Pool bereits Velos hat (ohne auf IoT/Cron zu warten).
- Takt: **primär am Geräte-Sendeintervall** (`update_data` → `apply_velos_earn`, typ. 10 s; künftig MQTT gleicher Hook): bei neuen Velos sofort Live-Tick für alle gestarteten Zonen. **`mcc_worker`** (z. B. 60 s) nur Fallback. Settings in `config/settings.py`: `LUANTI_PLAN_AUTO_CONVERT_ENABLED`, `LUANTI_PLAN_LIVE_CONVERT_MAX_BLOCKS_PER_EARN` (pro Impuls, skaliert mit `velos_added`), `LUANTI_PLAN_LIVE_CONVERT_MAX_BLOCKS_PER_TICK` (Worker), kürzere FX: `LUANTI_PLAN_LIVE_CONVERT_LAYER_DELAY` (Default 0,1 s).
- Ohne Admin-**START** keine serverseitige Auto-Umwandlung für die Zone (nur manuelles `/mccplan convert` im Build oder ingame `autoconvert`).

### Velos-Abzug prüfen (Plan-Kauf vs. Umwandlung)

Wenn beim Kaufen im Planungsmodus Velos vom Konto verschwinden:

1. **Admin → Luanti → Shop-Transaktionen** nach Spieler (`login_name`) und Zeit filtern.
   - **Plan-Kauf** (`plan_buy`) mit `velos_delta=0`: Kauf war korrekt; Abzug kommt von **Umwandlung** oder vom **Plan-Velos-Pool**.
   - **Kauf** (`buy`) mit negativem Delta: der Client hat `planning` nicht gesendet (Plan-Häkchen aus, `/mccbuy` ohne Plan-Modus, oder `mcc_plan` nicht geladen).
2. **Admin → Luanti → Plan-Umwandlungs-Transaktionen**: jede Zeile ist ein umgewandelter Hologramm-Block; `velos_delta` negativ belastet den Pool.
3. **Admin → Luanti → Geschützte Regionen** → **Plan-Velos-Gruppen**: hängt die Session-Wallet in diesem Pool, sinkt `Velos:` im Shop bei der Umwandlung — das ist Konfiguration, kein Plan-Kauf-Bug.
4. Im Spiel: `/mccplan` (AN/AUS), Build-Modus-Session, Mod `mcc_plan` geladen.

## Bridge (Lua)

Mod-Pfad im Repo: `mcc-web/luanti_mod/mcc_bridge/`

Deploy:

Produktion: Mod-**Dateien** unter `/data/appl/mcc/mcc-web/luanti_mod/` (rsync via `scripts/sync_luanti_mod.sh`). Spielverzeichnis: nur Symlinks (`link_luanti_mods.sh`).

```bash
MCC_WEB_DIR=/data/appl/mcc/mcc-web /data/appl/mcc/mcc-web/scripts/sync_luanti_mod.sh
MCC_WEB_DIR=/data/appl/mcc/mcc-web /data/appl/mcc/mcc-web/scripts/link_luanti_mods.sh
```

Manuell (nur falls nötig):

```bash
ln -sfn /data/appl/mcc/mcc-web/luanti_mod/mcc_bridge /data/games/mcc/luanti/mods/mcc_bridge
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
