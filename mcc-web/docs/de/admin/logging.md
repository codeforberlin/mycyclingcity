# Log-Dateien im Admin GUI anzeigen

## Übersicht

Logs werden in Dateien gespeichert und können über den Log File Viewer im Admin GUI angezeigt werden.

## Log-Dateien

Logs werden in folgenden Dateien gespeichert:
- `data/logs/api.log` - API-Anwendung (Entwicklung) / `/data/var/mcc/logs/api.log` (Produktion)
- `data/logs/mgmt.log` - Management-Anwendung (Entwicklung) / `/data/var/mcc/logs/mgmt.log` (Produktion)
- `data/logs/iot.log` - IoT-Anwendung (Entwicklung) / `/data/var/mcc/logs/iot.log` (Produktion)
- `data/logs/kiosk.log` - Kiosk-Anwendung (Entwicklung) / `/data/var/mcc/logs/kiosk.log` (Produktion)
- `data/logs/game.log` - Game-Anwendung (Entwicklung) / `/data/var/mcc/logs/game.log` (Produktion)
- `data/logs/django.log` - Django-Framework (nur WARNING+) (Entwicklung) / `/data/var/mcc/logs/django.log` (Produktion)
- `data/logs/gunicorn_access.log` - Gunicorn Access-Logs (Entwicklung) / `/data/var/mcc/logs/gunicorn_access.log` (Produktion)
- `data/logs/gunicorn_error.log` - Gunicorn Error-Logs (Entwicklung) / `/data/var/mcc/logs/gunicorn_error.log` (Produktion)

## Logs im Admin anzeigen

1. **Admin GUI öffnen**: `/admin/`
2. **Navigation**: "Mgmt" → "View Application Logs"
3. **URL direkt**: `/admin/logs/`
4. **Log-Datei auswählen**: Wählen Sie eine Log-Datei aus dem Dropdown-Menü
5. **Features**:
   - Echtzeit-Log-Anzeige
   - Auto-Refresh-Funktion
   - Suche in Log-Einträgen
   - Rotierte Log-Dateien durchsuchen

## Log-Level

Alle Log-Level werden in den Log-Dateien gespeichert:
- **DEBUG** - Debug-Informationen
- **INFO** - Informationsmeldungen
- **WARNING** - Warnungen
- **ERROR** - Fehler
- **CRITICAL** - Kritische Fehler

Die Log-Level können pro App in `config/settings.py` konfiguriert werden.

## Log-Dateien anzeigen

### Im Terminal:
```bash
# API-Logs (Entwicklung)
tail -f data/logs/api.log

# Management-Logs (Entwicklung)
tail -f data/logs/mgmt.log

# Alle App-Logs gleichzeitig (Entwicklung)
tail -f data/logs/*.log
```

### Im Admin-GUI:
- **Management** → **View Application Logs**
- Wählen Sie die gewünschte Logdatei aus
- Filterbar nach Level, Datum, etc.

## Best Practices

1. **Log-Rotation**: Automatische Rotation bei 50 MB pro Datei (10 Backups)
2. **Monitoring**: Prüfen Sie regelmäßig kritische Logs
3. **Retention**: Alte Log-Dateien werden automatisch rotiert
4. **Performance**: Logs werden direkt in Dateien geschrieben, keine Datenbank-Overhead
