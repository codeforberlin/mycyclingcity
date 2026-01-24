# Server-Steuerung im Admin GUI

## Übersicht

Die MCC-Web Anwendung kann über ein Script gestartet, gestoppt und neu gestartet werden. Zusätzlich kann der Server direkt aus dem Admin GUI heraus gesteuert werden.
Hinweis: In der aktuellen Produktion läuft die Anwendung als Benutzer `mcc` unter `/data/games/mcc/mcc-web`. Passen Sie Pfade und Benutzer an Ihre Umgebung an.

## Script-Verwendung

### Script-Location

Das Management-Script befindet sich unter:
```
mcc-web/scripts/mcc-web.sh
```

### Verfügbare Befehle

```bash
/path/to/mcc-web/scripts/mcc-web.sh start
/path/to/mcc-web/scripts/mcc-web.sh stop
/path/to/mcc-web/scripts/mcc-web.sh restart
/path/to/mcc-web/scripts/mcc-web.sh reload
/path/to/mcc-web/scripts/mcc-web.sh status
```

### Befehle im Detail

- **start** - Startet den Gunicorn-Server
- **stop** - Stoppt den Server (graceful shutdown)
- **restart** - Startet den Server neu (stop + start)
- **reload** - Lädt die Konfiguration neu (HUP-Signal, kein Neustart)
- **status** - Zeigt den aktuellen Status an

### Beispiel-Verwendung

```bash
# Server starten
/data/games/mcc/mcc-web/scripts/mcc-web.sh start

# Status prüfen
/data/games/mcc/mcc-web/scripts/mcc-web.sh status

# Server neu starten
/data/games/mcc/mcc-web/scripts/mcc-web.sh restart
```

## Admin GUI Steuerung

### Zugriff

1. **Admin GUI öffnen**: `/admin/`
2. **Navigation**: Gehen Sie zu `/admin/server/`
3. **URL direkt**: `/admin/server/`

### Verfügbare Aktionen

- **Start Server** - Startet den Server
- **Stop Server** - Stoppt den Server
- **Restart Server** - Startet den Server neu
- **Reload Configuration** - Lädt Konfiguration neu (ohne Neustart)
- **Refresh Status** - Aktualisiert den Status

### Sicherheit

- Nur **Superuser** können den Server steuern
- Alle Aktionen erfordern Bestätigung
- Stop und Restart zeigen Warnungen vor der Ausführung

## Konfiguration

### Environment-Variablen

Das Script unterstützt folgende Environment-Variablen:

```bash
export VENV_DIR=/path/to/venv  # Virtual Environment (Standard: $PROJECT_DIR/venv)
```

### PID-File

Das Script erstellt ein PID-File unter:
```
mcc-web/mcc-web.pid
```

Dieses File wird automatisch verwaltet und gelöscht, wenn der Server gestoppt wird.

### Log-Dateien

Startup-Logs werden gespeichert unter:
```
mcc-web/logs/gunicorn_startup.log
```

## Start/Stop über Script

```bash
/path/to/mcc-web/scripts/mcc-web.sh start
/path/to/mcc-web/scripts/mcc-web.sh stop
/path/to/mcc-web/scripts/mcc-web.sh restart
/path/to/mcc-web/scripts/mcc-web.sh status
```

## Auto-Start bei System-Boot

Falls Sie möchten, dass der Server automatisch beim Boot startet, können Sie:

### Option 1: Cron @reboot

Fügen Sie in die crontab des gewünschten Benutzers ein:

```bash
crontab -e
```

Dann hinzufügen:
```
@reboot /path/to/mcc-web/scripts/mcc-web.sh start
```


## Troubleshooting

### Script ist nicht ausführbar

```bash
chmod +x /path/to/mcc-web/scripts/mcc-web.sh
```

### Permission Denied

Stellen Sie sicher, dass:
1. Das Script als `mcc` Benutzer ausgeführt wird
2. Der `mcc` Benutzer Zugriff auf das Projekt-Verzeichnis hat
3. Das Virtual Environment existiert und gunicorn installiert ist

### Server startet nicht

1. Prüfen Sie die Logs: `logs/gunicorn_startup.log`
2. Prüfen Sie, ob der Port bereits belegt ist: `netstat -tuln | grep 8001`
3. Prüfen Sie die Gunicorn-Konfiguration: `config/gunicorn_config.py`

### PID-File bleibt bestehen

Wenn das PID-File nach einem Crash bestehen bleibt:

```bash
# Prüfen, ob Prozess noch läuft
ps aux | grep gunicorn

# Falls nicht, PID-File löschen
rm /path/to/mcc-web/mcc-web.pid
```

## Best Practices

1. **Graceful Shutdown**: Verwenden Sie `stop` statt `kill -9`
2. **Konfiguration ändern**: Verwenden Sie `reload` statt `restart`
3. **Status prüfen**: Prüfen Sie immer den Status vor Aktionen
4. **Logs überwachen**: Beobachten Sie die Logs nach Neustarts

## Integration mit Monitoring

Das Script kann in Monitoring-Tools integriert werden:

```bash
# Health Check
if /path/to/mcc-web/scripts/mcc-web.sh status; then
    echo "Server is running"
else
    echo "Server is down, restarting..."
    /path/to/mcc-web/scripts/mcc-web.sh restart
fi
```
