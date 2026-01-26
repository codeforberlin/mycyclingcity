# Gunicorn Worker Konfiguration

## Übersicht

Dieses Dokument erklärt die Unterschiede zwischen verschiedenen Gunicorn Worker-Klassen, wann sie relevant werden, und wie man Signal-Handler-Probleme mit Minecraft RCON vermeidet.

## Gunicorn Worker vs. Minecraft Worker

### Gunicorn Worker

**Was sind Gunicorn Worker?**
- Web-Server-Prozesse, die HTTP-Requests verarbeiten
- Verarbeiten Requests von:
  - MCC-Geräten (alle 10 Sekunden)
  - Admin GUI (z.B. Snapshot-Button)
  - Web-Browser (User-Requests)

**Konfiguration:**
- Anzahl: Konfigurierbar (Standard: CPU * 2 + 1)
- Worker-Klasse: `sync` oder `gthread`
- Threads: Nur bei `gthread` relevant

### Minecraft Worker

**Was sind Minecraft Worker?**
- Separate Background-Prozesse (nicht Teil von Gunicorn)
- `minecraft_bridge_worker`: Verarbeitet Outbox-Events
- `minecraft_snapshot_worker`: Aktualisiert regelmäßig Snapshots
- Laufen im Hauptthread → **keine Signal-Probleme**

**Wichtig:** Diese Dokumentation bezieht sich auf **Gunicorn Worker**, nicht auf Minecraft Worker.

## Worker-Klassen: sync vs. gthread

### sync Worker

**Funktionsweise:**
- 1 Request pro Worker gleichzeitig
- Blockierend: Worker wartet, bis Request fertig ist
- Einfach, aber weniger effizient bei I/O

**Vorteile:**
- Keine Signal-Handler-Probleme
- Einfache Konfiguration
- Stabil

**Nachteile:**
- Weniger effizient bei I/O-lastigen Operationen
- Bei hoher Last können Requests warten

### gthread Worker

**Funktionsweise:**
- Mehrere Requests pro Worker gleichzeitig (via Threads)
- Nicht-blockierend bei I/O: Während ein Thread wartet, kann ein anderer arbeiten
- Effizienter bei I/O-lastigen Operationen

**Vorteile:**
- Bessere Performance bei I/O-lastigen Operationen
- Mehr gleichzeitige Requests möglich

**Nachteile:**
- **Signal-Handler-Probleme** mit `mcrcon` (Minecraft RCON)
- Komplexere Konfiguration

## Signal-Handler-Problem

### Problem-Beschreibung

**Fehler:**
```
signal only works in main thread of the main interpreter
```

**Ursache:**
- `mcrcon` (Minecraft RCON Bibliothek) verwendet Signal-Handler für Timeouts
- Signal-Handler funktionieren nur im Hauptthread
- Bei `gthread` Worker laufen Requests in Threads, nicht im Hauptthread
- → Signal-Fehler beim Snapshot-Abruf aus dem Admin GUI

**Wann tritt es auf?**
- Wenn ein Gunicorn Worker (in einem Thread bei `gthread`) `refresh_scoreboard_snapshot()` direkt aufruft
- Z.B. beim Klick auf "Snapshot aktualisieren" im Admin GUI

**Wann tritt es NICHT auf?**
- Minecraft Worker laufen als separate Prozesse im Hauptthread → keine Probleme
- Normale Requests ohne RCON-Aufrufe → keine Probleme

### Lösung

**Option 1: Worker-Klasse auf `sync` ändern (empfohlen)**
- Vorteil: Einfach, behebt Problem sofort
- Nachteil: Geringere Performance bei I/O-lastigen Requests
- Vorgehen: Im Admin GUI (`/admin/mgmt/gunicornconfig/`) `worker_class` von `gthread` auf `sync` ändern

**Option 2: RCON-Client thread-sicher machen**
- Vorteil: `gthread` bleibt, bessere Performance
- Nachteil: Code-Änderung nötig
- Status: Noch nicht implementiert

## Wann wird der Unterschied relevant?

### Bei niedriger Last (< 1 Request/Sekunde)
- Unterschied kaum spürbar
- Beide Konfigurationen reichen aus

### Bei mittlerer Last (1-5 Requests/Sekunde)
- `sync`: Kann zu Wartezeiten führen, wenn Requests überlappen
- `gthread`: Kann mehrere Requests parallel verarbeiten
- Unterschied: Spürbar, aber meist noch akzeptabel

### Bei hoher Last (> 5 Requests/Sekunde)
- `sync`: Requests müssen warten, bis Worker frei ist
- `gthread`: Kann mehrere Requests parallel verarbeiten
- Unterschied: Deutlich spürbar

### Spezifisch für MCC-Web

**I/O-lastige Operationen:**
- Datenbankzugriffe (SQLite)
- RCON-Verbindungen (Minecraft)
- Datei-Operationen (Logs, Media)
- HTTP-Requests (falls vorhanden)

**Bei diesen Operationen:**
- `sync`: Worker blockiert während I/O
- `gthread`: Andere Threads können weiterarbeiten

## Praktische Auswirkungen

### Mit 1 Worker

| Szenario | `sync` | `gthread` (2 Threads) |
|----------|--------|------------------------|
| 1 gleichzeitiger Request | ✅ OK | ✅ OK |
| 2 gleichzeitige Requests | ⚠️ 1 wartet | ✅ Beide parallel |
| 3 gleichzeitige Requests | ⚠️ 2 warten | ⚠️ 2 parallel, 1 wartet |
| 10 gleichzeitige Requests | ⚠️ 9 warten | ⚠️ 2 parallel, 8 warten |

### Lastberechnung für MCC-Geräte

**Annahme:**
- 30-40 MCC-Stationen aktiv
- Alle 10 Sekunden ein Request pro Station
- Durchschnitt: 35 Stationen

**Berechnung:**
- 35 Requests / 10 Sekunden = **3,5 Requests/Sekunde**
- Maximal gleichzeitig: Theoretisch bis zu 35 (wenn alle exakt gleichzeitig senden)
- Praktisch: Meist 1-5 gleichzeitig (wegen Zeitversatz)

**Mit 2-3 Workern (`sync`):**
- 2 Worker: 2 gleichzeitige Requests → **ausreichend**
- 3 Worker: 3 gleichzeitige Requests → **mehr als ausreichend**

## RAM-Verbrauch

### Typischer RAM-Verbrauch

**Mit `sync` Worker (keine Threads):**
- Basis: ~50-80 MB (Python + Django)
- Django-App-Code: ~20-30 MB
- Datenbank-Verbindungen: ~5-10 MB
- Request-Buffer: ~5-10 MB
- **Gesamt: ~80-130 MB pro Worker**

**Mit `gthread` Worker (2 Threads):**
- Basis: ~80-130 MB
- Zusätzlich pro Thread: ~10-20 MB
- **Gesamt: ~100-150 MB pro Worker**

### Speicher-Berechnung für MCC-Web

**Option 1: 2 Worker mit `sync`**
- 2 × ~100 MB = ~200 MB
- Plus Master: ~150 MB
- **Gesamt: ~350 MB**

**Option 2: 3 Worker mit `sync`**
- 3 × ~100 MB = ~300 MB
- Plus Master: ~150 MB
- **Gesamt: ~450 MB**

**Zusätzlich:**
- Minecraft Worker: ~100-200 MB (2 Prozesse)
- **Gesamt-System: ~450-650 MB**

### Vergleich

| Konfiguration | RAM-Verbrauch | Kapazität |
|---------------|---------------|-----------|
| 1 Worker (`gthread`, 2 Threads) | ~300 MB | 2 gleichzeitig |
| 2 Worker (`sync`) | ~350 MB | 2 gleichzeitig |
| 3 Worker (`sync`) | ~450 MB | 3 gleichzeitig |

## Empfehlungen

### Für 30-40 MCC-Stationen

**Empfohlene Konfiguration:**
- **Worker-Klasse:** `sync` (vermeidet Signal-Probleme)
- **Worker-Anzahl:** 2-3 (ausreichend für 3,5 Requests/Sekunde)
- **RAM-Verbrauch:** ~350-450 MB (überschaubar)

**Begründung:**
- 2-3 Worker mit `sync` = 2-3 gleichzeitige Requests
- Durchschnitt: 3,5 Requests/Sekunde → ausreichend
- Spitzenlast: Meist 1-5 gleichzeitig → 2-3 Worker reichen
- Signal-Probleme sind behoben

### Wann sollte man `gthread` verwenden?

**Empfohlen bei:**
- > 2 gleichzeitigen Requests
- I/O-lastigen Operationen (DB, Netzwerk, Dateien)
- Mehreren Workern (3+)
- **UND:** RCON-Client muss thread-sicher sein (Option 2 implementiert)

**Nicht nötig bei:**
- Niedriger Last (< 1 Request/Sekunde)
- Wenigen Workern (1-2)
- CPU-lastigen Operationen (Threads helfen hier nicht)

## Konfiguration ändern

### Im Admin GUI

1. Gehe zu `/admin/mgmt/gunicornconfig/`
2. Ändere `worker_class` von `gthread` auf `sync`
3. Setze `workers` auf 2 oder 3
4. Speichere
5. Starte Server neu: `/data/appl/mcc/mcc-web/scripts/mcc-web.sh restart`

### Mit Management-Command

```bash
cd /data/appl/mcc/mcc-web
source /data/appl/mcc/venv/bin/activate
python manage.py set_gunicorn_sync
```

Danach Server neu starten:
```bash
/data/appl/mcc/mcc-web/scripts/mcc-web.sh restart
```

## Zusammenfassung

- **Gunicorn Worker** verarbeiten HTTP-Requests (nicht zu verwechseln mit Minecraft Worker)
- **`sync`** Worker vermeiden Signal-Handler-Probleme mit `mcrcon`
- **2-3 Worker** mit `sync` sind ausreichend für 30-40 MCC-Stationen
- **RAM-Verbrauch** ist überschaubar (~350-450 MB)
- Die Änderung auf `sync` ist für die aktuelle Situation eine gute Lösung
