# Minecraft-Integration - Dokumentation

## Übersicht

Das Minecraft-Modul ermöglicht die Integration zwischen MyCyclingCity und einem Minecraft-Server. Es synchronisiert die Coins der Radler zwischen der Django-Datenbank und Minecraft-Scoreboards, sodass Spieler ihre verdienten Coins im Minecraft-Server verwenden können.

## Hauptfunktionen

### 1. Coin-Synchronisation

- **Bidirektionale Synchronisation**: Coins werden von MyCyclingCity zu Minecraft und zurück synchronisiert
- **Scoreboard-Integration**: Verwendet Minecraft-Scoreboards für die Coin-Anzeige
- **Echtzeit-Updates**: Änderungen werden sofort an den Minecraft-Server übertragen

### 2. RCON-Kommunikation

- **Remote-Verwaltung**: Kommunikation mit dem Minecraft-Server über RCON (Remote Console)
- **Scoreboard-Verwaltung**: Automatische Erstellung und Verwaltung von Scoreboard-Objectives
- **Player-Score-Updates**: Aktualisierung der Spieler-Scores in Echtzeit

### 3. Outbox-Pattern

- **Asynchrone Verarbeitung**: Events werden in einer Outbox gespeichert und asynchron verarbeitet
- **Fehlerbehandlung**: Automatische Wiederholung bei Fehlern
- **Event-Tracking**: Vollständige Nachverfolgbarkeit aller Synchronisations-Events

### 4. WebSocket-Support

- **Echtzeit-Kommunikation**: WebSocket-Endpunkt für direkte Kommunikation mit Minecraft-Plugins
- **Sichere Authentifizierung**: Signatur-basierte Authentifizierung
- **Coin-Ausgabe**: Unterstützung für direkte Coin-Ausgaben aus Minecraft

### 5. Snapshot-System

- **Status-Erfassung**: Periodische Erfassung des Scoreboard-Status
- **Vergleich**: Vergleich zwischen Datenbank und Minecraft-Server
- **Synchronisation**: Automatische Synchronisation bei Abweichungen

## Konfiguration

### Erforderliche Einstellungen

Fügen Sie folgende Einstellungen in Ihre `.env` Datei ein:

```env
# RCON-Verbindung
MCC_MINECRAFT_RCON_HOST=127.0.0.1
MCC_MINECRAFT_RCON_PORT=25575
MCC_MINECRAFT_RCON_PASSWORD=ihr-rcon-passwort

# Scoreboard-Namen
MCC_MINECRAFT_SCOREBOARD_COINS_TOTAL=player_coins_total
MCC_MINECRAFT_SCOREBOARD_COINS_SPENDABLE=player_coins_spendable

# Worker-Intervalle (in Sekunden)
MCC_MINECRAFT_WORKER_POLL_INTERVAL=1
MCC_MINECRAFT_RCON_HEALTH_INTERVAL=30
MCC_MINECRAFT_SNAPSHOT_INTERVAL=60

# Snapshot-Einstellungen
MCC_MINECRAFT_SNAPSHOT_UPDATE_DB_SPENDABLE=True

# Outbox-Einstellungen
MCC_MINECRAFT_OUTBOX_DONE_TTL_DAYS=7
MCC_MINECRAFT_OUTBOX_FAILED_TTL_DAYS=30
MCC_MINECRAFT_OUTBOX_MAX_EVENTS=50000

# WebSocket (optional)
MCC_MINECRAFT_WS_ENABLED=False
MCC_MINECRAFT_WS_SHARED_SECRET=ihr-geheimer-schlüssel
MCC_MINECRAFT_WS_ALLOWED_SERVER_IDS=server1,server2
```

### RCON-Setup im Minecraft-Server

Aktivieren Sie RCON in der `server.properties`:

```properties
enable-rcon=true
rcon.port=25575
rcon.password=ihr-rcon-passwort
```

## Admin GUI

### Zugriff

Navigieren Sie zu `/admin/minecraft/` im Django Admin Interface (nur für Superuser).

### Funktionen

#### Worker-Steuerung

- **Start**: Startet den Minecraft-Bridge-Worker
- **Stop**: Stoppt den Worker
- **Status**: Zeigt den aktuellen Worker-Status an

#### Snapshot-Worker

- **Start**: Startet den Snapshot-Worker (periodische Status-Erfassung)
- **Stop**: Stoppt den Snapshot-Worker
- **Status**: Zeigt den Snapshot-Worker-Status an

#### Manuelle Aktionen

- **Sync**: Manuelle vollständige Synchronisation aller Spieler
- **Snapshot**: Manuelle Aktualisierung des Scoreboard-Snapshots
- **RCON-Test**: Testet die RCON-Verbindung
- **Cleanup**: Bereinigt alte Outbox-Events

### Status-Anzeige

Das Admin-Interface zeigt:

- **Worker-Status**: Ob der Bridge-Worker läuft
- **Snapshot-Status**: Ob der Snapshot-Worker läuft
- **Outbox-Status**: Anzahl der ausstehenden, verarbeitenden und fehlgeschlagenen Events
- **RCON-Status**: Verbindungsstatus zum Minecraft-Server
- **Player-Liste**: Alle Spieler mit ihren Coin-Werten und Snapshot-Status

## Datenmodelle

### MinecraftOutboxEvent

Speichert Events für die asynchrone Verarbeitung:

- `event_type`: Typ des Events (`update_player_coins`, `sync_all`)
- `payload`: JSON-Daten des Events
- `status`: Status (`pending`, `processing`, `done`, `failed`)
- `attempts`: Anzahl der Verarbeitungsversuche
- `last_error`: Letzte Fehlermeldung (falls vorhanden)

### MinecraftPlayerScoreboardSnapshot

Speichert Snapshots des Scoreboard-Status:

- `player_name`: Minecraft-Benutzername
- `cyclist`: Verknüpfung zum Cyclist-Modell
- `coins_total`: Gesamt-Coins (aus Scoreboard)
- `coins_spendable`: Ausgebbare Coins (aus Scoreboard)
- `source`: Quelle des Snapshots (`rcon`)
- `captured_at`: Zeitstempel der Erfassung

### MinecraftWorkerState

Speichert den Status des Workers:

- `is_running`: Ob der Worker läuft
- `pid`: Prozess-ID des Workers
- `started_at`: Startzeitpunkt
- `last_heartbeat`: Letzter Heartbeat
- `last_error`: Letzte Fehlermeldung

## Worker-Prozesse

### Bridge-Worker

Der Bridge-Worker verarbeitet kontinuierlich Events aus der Outbox:

```bash
python manage.py minecraft_bridge_worker
```

**Funktionen:**
- Verarbeitet `update_player_coins` Events
- Verarbeitet `sync_all` Events
- Aktualisiert Scoreboards über RCON
- Erstellt Snapshots nach Updates

**Start/Stop über Script:**
```bash
scripts/minecraft.sh start
scripts/minecraft.sh stop
scripts/minecraft.sh status
```

### Snapshot-Worker

Der Snapshot-Worker erfasst periodisch den Scoreboard-Status:

```bash
python manage.py minecraft_snapshot_worker
```

**Funktionen:**
- Liest alle Spieler-Scores aus dem Minecraft-Server
- Aktualisiert die Snapshot-Tabelle
- Synchronisiert `coins_spendable` zurück zur Datenbank (optional)

**Start/Stop über Script:**
```bash
scripts/minecraft.sh snapshot-start
scripts/minecraft.sh snapshot-stop
scripts/minecraft.sh snapshot-status
```

## WebSocket-Integration

### Aktivierung

Setzen Sie in der `.env`:

```env
MCC_MINECRAFT_WS_ENABLED=True
MCC_MINECRAFT_WS_SHARED_SECRET=ihr-geheimer-schlüssel
MCC_MINECRAFT_WS_ALLOWED_SERVER_IDS=server1
```

### Endpunkt

WebSocket-Endpunkt: `ws://your-domain/ws/minecraft/events/`

### Unterstützte Events

#### SPEND_COINS

Spieler gibt Coins im Minecraft aus:

```json
{
  "type": "SPEND_COINS",
  "player": "SpielerName",
  "amount": 100,
  "server_id": "server1",
  "signature": "hmac-signatur"
}
```

**Antwort:**
```json
{
  "status": "ok"
}
```

### Signatur-Berechnung

Die Signatur wird mit HMAC-SHA256 berechnet:

```python
import hmac
import hashlib
import json

payload = {"type": "SPEND_COINS", "player": "SpielerName", "amount": 100}
message = json.dumps(payload, sort_keys=True)
signature = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
```

## Management-Commands

### Vollständige Synchronisation

```bash
python manage.py minecraft_sync_full
```

Synchronisiert alle Spieler mit einem Minecraft-Benutzernamen.

### Snapshot aktualisieren

```bash
python manage.py minecraft_snapshot_refresh
```

Aktualisiert den Scoreboard-Snapshot manuell.

### Outbox bereinigen

```bash
python manage.py minecraft_outbox_cleanup
```

Bereinigt alte Events aus der Outbox (automatisch nach TTL).

## Spieler-Verknüpfung

Um einen Radler mit einem Minecraft-Spieler zu verknüpfen:

1. Navigieren Sie zu **MCC Core API & Models** → **Radler**
2. Wählen Sie den Radler aus
3. Tragen Sie im Feld `mc_username` den Minecraft-Benutzernamen ein
4. Speichern Sie

Nach der Verknüpfung werden die Coins automatisch synchronisiert.

## Workflow

### Coin-Update von MyCyclingCity zu Minecraft

1. Radler verdient Coins (z.B. durch Radfahren)
2. `coins_total` oder `coins_spendable` wird in der Datenbank aktualisiert
3. Event wird in die Outbox eingereiht
4. Bridge-Worker verarbeitet das Event
5. RCON-Befehl wird an Minecraft-Server gesendet
6. Scoreboard wird aktualisiert
7. Snapshot wird erstellt

### Coin-Ausgabe von Minecraft zu MyCyclingCity

1. Spieler gibt Coins im Minecraft aus (z.B. über Plugin)
2. Plugin sendet WebSocket-Event an MyCyclingCity
3. `coins_spendable` wird in der Datenbank reduziert
4. Event wird in die Outbox eingereiht
5. Bridge-Worker aktualisiert das Scoreboard
6. Snapshot wird aktualisiert

## Fehlerbehebung

### RCON-Verbindung schlägt fehl

1. Prüfen Sie die RCON-Einstellungen in `server.properties`
2. Testen Sie die Verbindung im Admin GUI (`RCON-Test`)
3. Prüfen Sie Firewall-Einstellungen
4. Stellen Sie sicher, dass der Minecraft-Server läuft

### Worker startet nicht

1. Prüfen Sie die Logs: `logs/minecraft_action.log`
2. Stellen Sie sicher, dass das Script ausführbar ist: `chmod +x scripts/minecraft.sh`
3. Prüfen Sie die Python-Umgebung
4. Prüfen Sie die Datenbankverbindung

### Coins werden nicht synchronisiert

1. Prüfen Sie die Outbox im Admin GUI
2. Prüfen Sie fehlgeschlagene Events
3. Prüfen Sie die Logs: `logs/minecraft.log`
4. Stellen Sie sicher, dass der Worker läuft
5. Prüfen Sie, ob der Spieler einen `mc_username` hat

### Snapshot zeigt falsche Werte

1. Führen Sie manuell einen Snapshot aus (Admin GUI)
2. Prüfen Sie die RCON-Verbindung
3. Prüfen Sie, ob die Scoreboards im Minecraft existieren
4. Führen Sie eine vollständige Synchronisation aus

## Best Practices

1. **Regelmäßige Snapshots**: Lassen Sie den Snapshot-Worker laufen, um Abweichungen früh zu erkennen
2. **Outbox-Monitoring**: Überwachen Sie die Outbox regelmäßig auf fehlgeschlagene Events
3. **RCON-Sicherheit**: Verwenden Sie ein starkes RCON-Passwort
4. **WebSocket-Sicherheit**: Verwenden Sie einen starken Shared Secret
5. **Backup**: Sichern Sie regelmäßig die Outbox-Events und Snapshots
6. **Logging**: Aktivieren Sie ausführliches Logging für Debugging

## Verwandte Dokumentation

- [Admin GUI Handbuch](index.md) - Übersicht über alle Admin-Funktionen
- [Server Control](index.md#server-control) - Server-Verwaltung
- [Log File Viewer](index.md#log-file-viewer) - Log-Dateien anzeigen
