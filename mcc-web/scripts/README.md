# MCC-Web Management Scripts

## mcc-web.sh

Management-Script für den MCC-Web Gunicorn Server.

### Installation

```bash
chmod +x scripts/mcc-web.sh
```

### Verwendung

```bash
/path/to/mcc-web/scripts/mcc-web.sh {start|stop|restart|reload|status}
```

Hinweis: In der aktuellen Produktion läuft die Anwendung als Benutzer `mcc`
unter `/data/games/mcc/mcc-web`. Passen Sie Pfade und Benutzer an Ihre Umgebung an.

### Befehle

- **start** - Startet den Server
- **stop** - Stoppt den Server (graceful)
- **restart** - Startet den Server neu
- **reload** - Lädt Konfiguration neu (HUP-Signal)
- **status** - Zeigt Server-Status an

### Konfiguration

Das Script erkennt automatisch:
- Projekt-Verzeichnis (aus Script-Pfad)
- Virtual Environment (Standard: `$PROJECT_DIR/venv`)
- Gunicorn-Config (Standard: `$PROJECT_DIR/config/gunicorn_config.py`)

Environment-Variablen:
- `VENV_DIR` - Virtual Environment Pfad

### Dateien

- **PID-File**: `data/tmp/mcc-web.pid` (Entwicklung) / `/data/var/mcc/tmp/mcc-web.pid` (Produktion)
- **Startup-Log**: `data/logs/gunicorn_startup.log` (Entwicklung) / `/data/var/mcc/logs/gunicorn_startup.log` (Produktion)

### Beispiel

```bash
# Server starten
/data/games/mcc/mcc-web/scripts/mcc-web.sh start

# Status prüfen
/data/games/mcc/mcc-web/scripts/mcc-web.sh status

# Server neu starten
/data/games/mcc/mcc-web/scripts/mcc-web.sh restart
```

## backup_mcc.sh

Backup-Script für MyCyclingCity Datenbank und wichtige Daten (ohne Logfiles) via rsync über SSH.

### Installation

```bash
chmod +x scripts/backup_mcc.sh
```

### Konfiguration

1. Kopieren Sie die Beispiel-Konfiguration:
```bash
cp scripts/backup_mcc.conf.example scripts/backup_mcc.conf
```

2. Bearbeiten Sie `scripts/backup_mcc.conf` und passen Sie die Werte an:
   - `SSH_HOST` - Hostname oder IP des Backup-Servers
   - `SSH_USER` - Benutzername für SSH-Verbindung
   - `SSH_PORT` - SSH-Port (Standard: 22)
   - `SSH_KEY` - Optional: Pfad zu SSH-Private-Key
   - `REMOTE_BACKUP_DIR` - Zielverzeichnis auf dem Remote-Server

### Verwendung

```bash
# Manuelles Backup ausführen (Produktion) - Standard-Konfiguration
/data/appl/mcc/mcc-web/scripts/backup_mcc.sh

# Eigene Konfigurationsdatei angeben (absoluter Pfad)
/data/appl/mcc/mcc-web/scripts/backup_mcc.sh /path/to/custom_backup.conf

# Eigene Konfigurationsdatei angeben (relativ zum Script-Verzeichnis)
cd /data/appl/mcc/mcc-web
./scripts/backup_mcc.sh custom_backup.conf

# Hilfe anzeigen
./scripts/backup_mcc.sh --help
```

**Hinweis**: Das Script erkennt automatisch die Produktionsumgebung und verwendet:
- **Anwendung**: `/data/appl/mcc/mcc-web`
- **Daten**: `/data/var/mcc`
- **Standard-Konfiguration**: `/data/appl/mcc/mcc-web/scripts/backup_mcc.conf`

### Was wird gesichert?

- **Datenbank**: `/data/var/mcc/db/db.sqlite3` (inkl. WAL/SHM falls vorhanden)
- **Media-Dateien**: `/data/var/mcc/media/` (ohne Logfiles)
  - Excludes: `*.log`, `*.log.*`, `logs/`, `*.tmp`, `*.temp`

### Was wird NICHT gesichert?

- **Log-Verzeichnis**: `/data/var/mcc/logs/` wird **NICHT** gesichert
  - Logs werden durch eine systemweite Log-Rotation (logrotate) verwaltet
  - Siehe Abschnitt "Log-Rotation" weiter unten

### Automatische tägliche Ausführung (Cron)

Erstellen Sie einen Cron-Job für tägliche Backups:

```bash
# Crontab bearbeiten
crontab -e

# Täglich um 2:00 Uhr morgens (Produktion)
0 2 * * * /data/appl/mcc/mcc-web/scripts/backup_mcc.sh >> /data/var/mcc/logs/backup_cron.log 2>&1
```

Oder verwenden Sie das bereitgestellte Cron-Script:
```bash
# Cron-Job installieren (täglich um 22:00 Uhr) - Produktion
/data/appl/mcc/mcc-web/scripts/install_backup_cron.sh

# Mit eigener Uhrzeit (z.B. 2:00 Uhr morgens)
/data/appl/mcc/mcc-web/scripts/install_backup_cron.sh 2

# Mit eigener Konfigurationsdatei
/data/appl/mcc/mcc-web/scripts/install_backup_cron.sh 22 /data/appl/mcc/backup_mcc.conf
```

### Logging

- **Log-Dateien**: `/data/var/mcc/logs/backup_YYYYMMDD.log`
- **Log-Retention**: 90 Tage (automatische Bereinigung)
- **Backup-Retention**: 30 Tage (lokale Backups)

### Beispiel-Ausgabe

```
[INFO] === MyCyclingCity Backup gestartet ===
[INFO] Konfiguration geladen: backup-user@backup.example.com:22 -> /backup/mcc
[INFO] Starte Datenbank-Backup...
[INFO] Datenbank-Backup erstellt: /data/var/mcc/backups/db_backup_20260125_020000.sqlite3
[INFO] Synchronisiere Datenbank-Backup...
[INFO] Datenbank-Backup erfolgreich synchronisiert
[INFO] Synchronisiere Media-Verzeichnis (ohne Logfiles)...
[INFO] Media-Verzeichnis erfolgreich synchronisiert
[INFO] Räume alte Backups auf (älter als 30 Tage)...
[INFO] === Backup abgeschlossen (Dauer: 45s) ===
```

### Voraussetzungen

- `rsync` muss installiert sein
- SSH-Zugriff auf den Backup-Server (mit oder ohne Passwort)
- Schreibrechte auf `/data/var/mcc/backups/` und `/data/var/mcc/logs/`
- Leserechte auf `/data/var/mcc/db/` und `/data/var/mcc/media/`

## Log-Rotation (logrotate)

Die Log-Dateien werden durch eine systemweite Log-Rotation verwaltet und werden daher **nicht** im Backup gesichert.

### Installation

```bash
# Logrotate-Konfiguration installieren (als root)
sudo /data/appl/mcc/mcc-web/scripts/install_logrotate.sh
```

### Konfiguration

Die Log-Rotation ist in `/etc/logrotate.d/mcc` konfiguriert:

- **App-Logs** (`api.log`, `mgmt.log`, `iot.log`, etc.):
  - Rotation: täglich
  - Aufbewahrung: 30 Tage
  - Kompression: ja (mit Verzögerung)

- **Backup-Logs** (`backup_*.log`):
  - Rotation: wöchentlich
  - Aufbewahrung: 12 Wochen
  - Kompression: ja

- **Gunicorn-Logs** (`gunicorn_*.log`):
  - Rotation: täglich
  - Aufbewahrung: 14 Tage
  - Kompression: ja

### Manuelle Rotation testen

```bash
# Trockenlauf (zeigt was passieren würde)
sudo logrotate -d /etc/logrotate.d/mcc

# Rotation sofort ausführen
sudo logrotate -f /etc/logrotate.d/mcc
```

### Hinweis

Die Log-Rotation sendet automatisch ein HUP-Signal an Gunicorn, damit die Log-Handler die rotierten Dateien korrekt neu öffnen. Dies geschieht nur, wenn Gunicorn läuft.
