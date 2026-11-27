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
- Modi: `play` / `plan` / `build` / `watch` (Privs + getrenntes Inventar pro Modus: play, plan, build)

### Betrieb vor Ort: Passwort vs. Session-Freigabe

Das Login-Passwort ist ein **technisches Hilfsmittel** (Anmeldung am Server, kein Wildwuchs an Accounts). Die **eigentliche Nutzungsfreigabe** ist immer die **Session** durch Erwachsene (Admin oder RFID).

| Stufe | Bedeutung |
|-------|-----------|
| **Login** (Name + Passwort aus MCC) | Spieler ist auf dem Server, aber ohne Session **eingefroren** (Warte modus). |
| **Session-Freigabe** | Spielen/Planung/Bauen/Zeit/Modus — nur nach Start durch Betreuer. |

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
- **Spieler-Inventar (Admin):** Pro Modus (`play` / `plan` / `build`) Inventar ansehen und bearbeiten (`change_luantiplayerinventory`). Bei **Bauen** optional **Stacks verkaufen** (`sell_luantiplayerinventory`, Preset `luanti_admin`): dieselben Shop-Regeln wie ingame (Kaufguthaben, Velos-Rückerstattung, TOP-Sperre `luanti_shop_sell_own_wallet_credit_only`). Plan-Items sind nicht verkaufbar. Nach Verkauf wird das DB-Inventar angepasst und bei passender Online-Session per `SET_INVENTORY` live synchronisiert.

### Login-Passwörter (Luanti Client)

- Passwörter werden **ausschließlich** in MCC verwaltet und per Bridge (`SET_PASSWORD`) auf den Luanti-Server gespiegelt. Status **„Auf Server gesetzt“** (`password_provisioned`) erst nach Bridge-ACK.
- Nach Deploy oder Welt-Restore: **Luanti → Accounts** → *Passwörter auf Luanti-Server synchronisieren* (Filter beachten), oder pro Account auf der Detailseite *Auf Server synchronisieren*. Alternativ CLI: `python manage.py provision_all_luanti_passwords` (Bridge muss laufen).
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

**Shop-Artikel pro Kategorie:** nicht als Inline auf der Kategorie-Change-Seite (vermeidet `TooManyFieldsSent` bei großen Kategorien). Preise, Sortierung und Aktiv-Flag unter **Shop-Artikel** (Changelist, Filter **Kategorie**; Link auf der Kategorie-Change-Seite). Massenverschieben: Shop-Artikel → Action **In andere Kategorie verschieben…**

**Tab-Reihenfolge im `/mccshop`:** Kategorien alphabetisch nach **lokalisiertem Tab-Titel** (Client-Sprache / Katalog-`lang`), nicht nach DB-`sort_order`. `sort_order` gilt weiter für Admin-Listen und Shop Ops.

**Suche im `/mccshop`:** mit gesetztem Suchtext alle Kategorien; Treffer in Anzeigename, allen Labels und `item_name`.

Knoten (`kind=node`) erhalten standardmäßig Stack 64.

Optional vorher: **Minecraft-Shop importieren** (spiegelt MC-Kategorien/Preise; deckt nicht alle Mineclonia-Mods ab).

**Shop und Session-Modus:**

| Modus | `/mccshop` |
|-------|------------|
| **Spielen** / **Zuschauen** | Katalog nur ansehen (kein Kauf/Verkauf) |
| **Planung** | Plan-Käufe (0 Velo); Tabs **Planen** / **Entfernen**; in der Welt **nur Geister-Steine** legen/abbauen (keine echten Blöcke graben/setzen) |
| **Bauen** | Reale Käufe + Verkauf (Purchase Credit) + Tab **Umwandeln** (Geister-Blöcke, Plan-Pool, Auto-Umwandlung) |

## Planmodus (Hologramme / Umwandlung)

- **Shop ingame (Kinder-UI):** Plan-Session erklärt Geister-Blöcke/0 Velos; Wallet-Zeile **Kauf später von:** (keine sofortige Abbuchung). Stöbern ohne Freigabe: Hinweis statt technischer Session-Meldung.
- **Shop-Wallet** (`Velos:` im `/mccshop`) = spendbare Velos der aufgelösten Gruppe. Im **Bau**-Modus rechts vom Tab **Verkaufen** **Abbuchung:** bzw. **Gutschrift:** mit Wallet-Gruppenname je nach Tab (dieselbe Gruppe). Optional setzt die aktive **Session** ein festes `wallet_group` (Admin Session-Kontrolle).
- **Umwandlung (manuell)** (`/mccshop` → Tab **Umwandeln**, `/mccplan convert`): Velos werden in dieser **Reihenfolge** abgebucht:
  1. **Shop-Wallet des Spielers**, der umwandelt (Session, wie bei Kaufen/Verkaufen) — **auch wenn** diese Gruppe **nicht** in den Admin-Plan-Velos-Gruppen steht.
  2. Danach der **Plan-Velos-Pool** der Zone (Admin: geschützte Region → Plan-Velos-Gruppen, optional Regional-TOP).
  Im Tab **Umwandeln** siehst du den Pool, dein Wallet und kindgerechte Hinweise (Lua `shop_gui.lua`). `available_convert_velos` in der Plan-Summary zählt Pool **plus** dein Wallet, wenn es nicht schon im Pool enthalten ist.
- **Auto-Umwandlung / Live-Umwandlung** (Strampeln, Admin-START, kein Spieler am Knopf): **nur Plan-Pool**, **kein** Vorziehen des Spieler-Wallets — wie bisher.
- **Verkauf nach Umwandlung (Kaufguthaben):** strikte, einfache Regel — gut erklärbar für Kinder:
  - Zahlt **eine Person beim manuellen Umwandeln den ganzen Blockpreis allein aus ihrem Shop-Wallet** → Kaufguthaben für den späteren Verkauf liegt auf **dieser Gruppe**.
  - Wenn **irgendein Velo** aus dem Plan-Pool (oder einer zweiten Gruppe) mitbezahlt wird → Kaufguthaben auf der **effektiven Regional-TOP** der Zone (Master- oder Sub-TOP). **Kein** Anteilssplit — auch 1 Velo aus dem Pool reicht für TOP-Guthaben. Das belohnt **Eigenfinanzierung** (Anreiz, selbst Velos aufzubringen).
  - Beim **Verkaufen** gilt weiter: wer verkauft, bekommt die **Velos** auf die aktuelle Session-Wallet; Kaufguthaben muss auf der Gruppe der TOP-Kette liegen, damit der Block verkaufbar ist (Standard: eigene Wallet, sonst TOP-Pool).
- **Verkauf nur eigenes Kaufguthaben (TOP-Sperre):** Admin → **Gruppen** → TOP-Gruppe → Feldset **Luanti Shop** → Checkbox **Luanti: Verkauf nur eigenes Kaufguthaben (TOP)**. Wenn aktiv, dürfen Kind-Gruppen **kein** Kaufguthaben der TOP-Wallet mehr für Verkäufe nutzen (nur noch Guthaben auf der eigenen Shop-Wallet). Standard = aus (Pool-Verkauf wie bisher). Sinnvoll bei gemeinsamem Bau mehrerer Gruppen, um „TOP-Guthaben verkaufen, Velos auf die eigene Gruppe buchen“ zu verhindern. Im Shop-Tooltip: *TOP-Pool für eure Gruppe gesperrt*.
- **Admin → Luanti → Plan-Umwandlungs-Transaktionen:** Spalte **Verkaufsguthaben-Gruppe** (`credit_group`) zeigt, wer das spätere Verkaufsguthaben bekam; **Abbuchungs-Gruppe (primär)** ist die zuerst belastete Gruppe bei der Velo-Abbuchung.

### Umwandeln — Erklärung für Kinder (und Eltern)

Stell dir vor, du hast Geister-Steine geplant und willst daraus echte Blöcke machen:

1. **Zuerst** schauen wir auf **dein Velos-Konto im Shop** (dein Wallet). Hast du genug Velos? Dann nehmen wir sie von dort.
2. **Fehlt etwas?** Dann helfen die **Rad-Velos eurer Zone** (Plan-Pool) — das sind Velos, die beim Radfahren auf Omas Team, die Klasse oder ähnliche Gruppen gebucht wurden.
3. **Wenn du den Block später wieder verkaufen willst:**
   - Hast du **alles selbst bezahlt** → deine Gruppe darf verkaufen und behält das **Verkaufsguthaben**.
   - Hat **jemand anderes mitgezahlt** (auch nur ein bisschen aus dem Plan-Pool) → das Verkaufsguthaben liegt bei der **großen TOP-Gruppe** eurer Zone (Schule, Bezirk). Ihr könnt trotzdem verkaufen, aber der Erlös gehört der TOP — fairer Tausch: wer mitfinanziert, besitzt den Wiederverkauf.

**Tipp fürs Spiel:** Eigene Velos sparen lohnt sich, wenn du später selbst vom Verkauf profitieren willst.

**Auto beim Strampeln** (ohne dass du auf Umwandeln drückst): hier zählt **nur** der Plan-Pool — so kann Oma strampeln und eure Geister werden echt, ohne dass dein Wallet automatisch angefasst wird.
- Session **Planung**: Shop liefert Hologramm-Items; Platzierung nur in zugewiesenen Bauzonen. **Echte** Blöcke (Erde, Stein, …) dürfen in Plan **nicht** abgebaut oder gesetzt werden — nur **Geister**. Echten Aushub/Bau: Session **Bauen**. Unplatzierte Plan-Items: **`/mccshop` → Tab Entfernen**; alternativ `/mccplan discard hand|all`. Platzierte Hologramme: abbauen, `/mccplan remove`, `/mccplan clear`.
- **Tunnel/Straße (Betreuer):** (1) **Bauen** — ausheben, (2) **Planung** — Geister planen, (3) **Bauen** — kaufen oder umwandeln (Velos).
- **Plan-Hologramme (Erkennbarkeit):** Vorschau-Klone behalten die Original-Textur (halbtransparent), kein einheitliches Cyan mehr. Inventar-Tooltip und Block-`infotext` nutzen den **Shop-Anzeigenamen**. Optionale Client-Settings in `minetest.conf` / `luanti.conf`: `mcc_plan.holo_opacity` (Default 165), `mcc_plan.holo_colorize_alpha` (0 = aus), `mcc_plan.holo_border` (Default `false`, Rand-Modifier testweise).
- `/mccplan convert [n]` — manuelle Umwandlung (max. 256 pro Aufruf), **nur Session Bauen**, wenn der Pool Velos hat.
- **`/mccplan autoconvert on`** — Wartet im **Bau**-Modus auf Pool-Velos (Radfahren) und wandelt fortlaufend Hologramme um (Standard bis 4 Blöcke alle 5 s, `minetest.conf`: `mcc_plan.autoconvert_interval`, `mcc_plan.autoconvert_max_blocks`).
- **`/mccplan autoconvert off`** — stoppt die Schleife.
- **`/mccplan autoconvert`** — Status AN/AUS (auch in `summary`).
- HUD (Build-Modus): Pool und bei Auto-Umw. der Prefix `Auto-Umw. ·`.
- **Planung ingame** (`/mccplan on|off|remove|clear|…`) — nur Session **Planung**; **Umwandlung** (`convert`, `autoconvert on`) nur Session **Bauen** (`autoconvert off` jederzeit).
- **Live-Umwandlung (Admin):** `Admin → Luanti → Geschützte Regionen` → **Live-Umwandlung starten/stoppen** pro Zone. Server wandelt Hologramme um, sobald Plan-Pool-Velos ankommen (Radfahren). Ideal wenn Kinder geplant haben und Großeltern strampeln, während andere in Spiel/Flugmodus zuschauen — **ohne** `/mccplan autoconvert on` ingame.
- Beim **Live-Start** im Admin: sofort ein Umwandlungs-Schub, wenn der Plan-Pool bereits Velos hat (ohne auf IoT/Cron zu warten).
- Takt: **primär am Geräte-Sendeintervall** (`update_data` → `apply_velos_earn`, typ. 10 s; künftig MQTT gleicher Hook): bei neuen Velos sofort Live-Tick für alle gestarteten Zonen. **`mcc_worker`** (z. B. 60 s) nur Fallback. Settings in `config/settings.py`: `LUANTI_PLAN_AUTO_CONVERT_ENABLED`, `LUANTI_PLAN_LIVE_CONVERT_MAX_BLOCKS_PER_EARN` (pro Impuls, skaliert mit `velos_added`), `LUANTI_PLAN_LIVE_CONVERT_MAX_BLOCKS_PER_TICK` (Worker), kürzere FX: `LUANTI_PLAN_LIVE_CONVERT_LAYER_DELAY` (Default 0,1 s).
- Ohne Admin-**START** keine serverseitige Auto-Umwandlung für die Zone (nur manuelles `/mccplan convert` im Build oder ingame `autoconvert`).

### Velos-Abzug prüfen (Plan-Kauf vs. Umwandlung)

Wenn beim Kaufen im Planungsmodus Velos vom Konto verschwinden:

1. **Admin → Luanti → Shop-Transaktionen** nach Spieler (`login_name`) und Zeit filtern.
   - **Plan-Kauf** (`plan_buy`) mit `velos_delta=0`: Kauf war korrekt; Abzug kommt von **Umwandlung** oder vom **Plan-Velos-Pool**.
   - **Kauf** (`buy`) mit negativem Delta: der Client hat `planning` nicht gesendet (Plan-Häkchen aus, `/mccbuy` ohne Plan-Modus, oder `mcc_plan` nicht geladen).
2. **Admin → Luanti → Plan-Umwandlungs-Transaktionen**: jede Zeile ist ein umgewandelter Hologramm-Block; `velos_delta` negativ; `group` = primär abbuchbare Gruppe; `credit_group` = Verkaufsguthaben-Empfänger.
3. **Admin → Luanti → Geschützte Regionen** → **Plan-Velos-Gruppen**: hängt die Session-Wallet in diesem Pool, sinkt `Velos:` im Shop bei der Umwandlung — das ist Konfiguration, kein Plan-Kauf-Bug.
4. Im Spiel: Planungs- vs. Bau-Session prüfen, Mod `mcc_plan` geladen.

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
ln -sfn /data/appl/mcc/mcc-web/luanti_mod/mcc_bridge /data/games/mcc/luanti/games/mycyclingcity/mods/mcc_bridge
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

## Spiel mycyclingcity

Das Spiel liegt unter `/data/games/mcc/luanti/games/mycyclingcity`, nicht im Git. Basis-Mods (`default`, `stairs`, `wool`, `doors`, `walls`, `beds`, `vessels`, `xpanes`, `worldedit`, `areas`) sind Kopien. `mcc_bridge`, `mcc_plan` und `mcc_texture_painter` sind Symlinks auf `mcc-web/luanti_mod/` (`link_luanti_mods.sh`). `mcc_migrator` liegt nur während der Umstellung unter `worlds/<kopie>/worldmods/` (nicht im Spiel `mycyclingcity`).

Die Zielwelt ist `/data/games/mcc/luanti/worlds/mycyclingcity_prod`. Anlegen einmalig: `world.mt` wie unten, dann kurz `luantiserver --world …/mycyclingcity_prod --config …/scripts/minetest_prod.conf` starten (legt `map.sqlite` an). Start im Betrieb:

```bash
MCC_LUANTI_WORLD=mycyclingcity_prod \
MCC_LUANTI_CONFIG=/data/appl/mcc/mcc-web/scripts/minetest_prod.conf \
/data/appl/mcc/mcc-web/scripts/luanti_server.sh restart
```

In ihrer `world.mt`:

```
gameid = mycyclingcity
mg_name = singlenode
mg_flags = nocaves, nodungeons, light, nodecorations, nobiomes, noores
```

DEV und cbm-srv1 haben verschiedene Maps und Django-Daten. Derselbe Ablauf, jeweils auf dem Host, ohne die Mapping-Datei zu kopieren:

1. Backup von Welt und Datenbank.
2. Arbeitskopie `worlds/mycyclingcity_migrate` mit `gameid = mineclonia` in `world.mt` (MCC-Mods aus). In `worldmods/` nur Symlink `mcc_migrator` — **kein** MTG-Modpack neben Mineclonia (sonst Server-Absturz durch Alias-/ABM-Kollision). Zielknoten registriert `mcc_migrator` intern als Platzhalter. `worldmods/__mc2mt` entfernen. Nach fehlgeschlagenen Versuchen Welt **neu aus Backup kopieren**.
3. `/scan_mcl x1 y1 z1 x2 y2 z2`. Unbekannte Namen blockieren, bis `luanti/services/mcl_map.py` und `mcc_migrator/map.lua` dieselbe Regel haben.
4. `/convert_mcl x1 y1 z1 x2 y2 z2` (VoxelManip, kein LBM/`/emergeblocks`). Danach `/scan_mcl` wiederholen. Erst bei null `mcl_*` im Bereich weiter. **In dieser Welt sieht danach alles wie Stein aus** — `mcc_migrator` registriert MTG-Zielnamen nur als grafische Platzhalter, weil Mineclonia kein echtes MTG lädt. In `map.sqlite` stehen trotzdem die Ziel-Itemstrings (`default:wood`, `wool:red`, …). Sichtprüfung erst nach Schritt 6 in `mycyclingcity_prod`.
5. `worldmods/mcc_migrator` **erst nach erfolgreichem WorldEdit-Export** entfernen. `mcc_migrator_map.json` behalten.
6. WorldEdit in `mycyclingcity_migrate`: Symlink `worldmods/worldedit` → Spiel-Modpack, `load_mod_worldedit(_commands)` in `world.mt`, Ordner `schems/`. Server mit **`minetest.conf`** (nicht `minetest_prod.conf`) und Welt `mycyclingcity_migrate` starten. `luanti_server.sh` schaltet dort **MCC-Mods aus** (`mcc_bridge` blockiert sonst Login ohne Django-Provisionierung); Anmeldung über **`auth.txt`** und Welt-Passwort von `admin`. **`//wand`**, **`//pos1` / `//pos2`** exakt wie bei `/scan_mcl` und `/convert_mcl`, dann **`//save mauer_stadt`** (Datei: `worlds/mycyclingcity_migrate/schems/mauer_stadt.we`). In Prod dieselbe Box mit `//pos1` an derselben Ecke, **`//load mauer_stadt`**, danach **`//fixlight`**.
7. `python manage.py luanti_convert_from_mineclonia --world mycyclingcity_prod`, dann mit `--apply`.
8. `MCC_LUANTI_WORLD=mycyclingcity_prod` erst nach der Sichtprüfung. Die alte Welt bleibt Archiv.
