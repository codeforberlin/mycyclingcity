# Server-Steuerung im Admin GUI

## Übersicht

Die MCC-Web Anwendung kann jetzt über ein Script als `mcc` Benutzer gestartet, gestoppt und neu gestartet werden. Zusätzlich kann der Server direkt aus dem Admin GUI heraus gesteuert werden.

## Script-Verwendung

### Script-Location

Das Management-Script befindet sich unter:
```
mcc-web/scripts/mcc-web.sh
```

### Verfügbare Befehle

```bash
# Als mcc Benutzer ausführen
sudo -u mcc /path/to/mcc-web/scripts/mcc-web.sh start
sudo -u mcc /path/to/mcc-web/scripts/mcc-web.sh stop
sudo -u mcc /path/to/mcc-web/scripts/mcc-web.sh restart
sudo -u mcc /path/to/mcc-web/scripts/mcc-web.sh reload
sudo -u mcc /path/to/mcc-web/scripts/mcc-web.sh status
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
sudo -u mcc /data/games/mcc/mcc-web/scripts/mcc-web.sh start

# Status prüfen
sudo -u mcc /data/games/mcc/mcc-web/scripts/mcc-web.sh status

# Server neu starten
sudo -u mcc /data/games/mcc/mcc-web/scripts/mcc-web.sh restart
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
export MCC_USER=mcc          # Benutzer (Standard: mcc)
export MCC_GROUP=mcc        # Gruppe (Standard: mcc)
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

## Migration von systemd

### Vorher (systemd)

```bash
sudo systemctl start mcc-web
sudo systemctl stop mcc-web
sudo systemctl restart mcc-web
sudo systemctl status mcc-web
```

### Nachher (Script)

```bash
sudo -u mcc /path/to/mcc-web/scripts/mcc-web.sh start
sudo -u mcc /path/to/mcc-web/scripts/mcc-web.sh stop
sudo -u mcc /path/to/mcc-web/scripts/mcc-web.sh restart
sudo -u mcc /path/to/mcc-web/scripts/mcc-web.sh status
```

### systemd Service deaktivieren

Falls der systemd Service noch aktiv ist:

```bash
sudo systemctl stop mcc-web
sudo systemctl disable mcc-web
```

**Wichtig**: Der systemd Service sollte deaktiviert werden, um Konflikte zu vermeiden.

## Auto-Start bei System-Boot

Falls Sie möchten, dass der Server automatisch beim Boot startet, können Sie:

### Option 1: Cron @reboot

Fügen Sie in die crontab des mcc Benutzers ein:

```bash
sudo -u mcc crontab -e
```

Dann hinzufügen:
```
@reboot /path/to/mcc-web/scripts/mcc-web.sh start
```

### Option 2: systemd Service (nur für Start)

Sie können den systemd Service so anpassen, dass er nur beim Boot startet, aber nicht verwaltet wird:

```ini
[Service]
Type=oneshot
ExecStart=/path/to/mcc-web/scripts/mcc-web.sh start
RemainAfterExit=yes
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
3. Prüfen Sie die Gunicorn-Konfiguration: `gunicorn_config.py`

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
if sudo -u mcc /path/to/mcc-web/scripts/mcc-web.sh status; then
    echo "Server is running"
else
    echo "Server is down, restarting..."
    sudo -u mcc /path/to/mcc-web/scripts/mcc-web.sh restart
fi
```
