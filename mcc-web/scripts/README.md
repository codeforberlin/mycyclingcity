# MCC-Web Management Scripts

## mcc-web.sh

Management-Script für den MCC-Web Gunicorn Server.

### Installation

```bash
chmod +x scripts/mcc-web.sh
```

### Verwendung

```bash
# Als mcc Benutzer ausführen
sudo -u mcc /path/to/mcc-web/scripts/mcc-web.sh {start|stop|restart|reload|status}
```

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
- Gunicorn-Config (Standard: `$PROJECT_DIR/gunicorn_config.py`)

Environment-Variablen:
- `MCC_USER` - Benutzer (Standard: mcc)
- `MCC_GROUP` - Gruppe (Standard: mcc)
- `VENV_DIR` - Virtual Environment Pfad

### Dateien

- **PID-File**: `mcc-web.pid` (im Projekt-Verzeichnis)
- **Startup-Log**: `logs/gunicorn_startup.log`

### Beispiel

```bash
# Server starten
sudo -u mcc /data/games/mcc/mcc-web/scripts/mcc-web.sh start

# Status prüfen
sudo -u mcc /data/games/mcc/mcc-web/scripts/mcc-web.sh status

# Server neu starten
sudo -u mcc /data/games/mcc/mcc-web/scripts/mcc-web.sh restart
```
