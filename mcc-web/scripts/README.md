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

- **PID-File**: `tmp/mcc-web.pid` (im tmp-Verzeichnis)
- **Startup-Log**: `logs/gunicorn_startup.log`

### Beispiel

```bash
# Server starten
/data/games/mcc/mcc-web/scripts/mcc-web.sh start

# Status prüfen
/data/games/mcc/mcc-web/scripts/mcc-web.sh status

# Server neu starten
/data/games/mcc/mcc-web/scripts/mcc-web.sh restart
```
