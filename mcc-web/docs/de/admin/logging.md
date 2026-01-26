# Log-Dateien im Admin GUI anzeigen

## Übersicht

Logs werden in Dateien gespeichert und können über den Log File Viewer im Admin GUI angezeigt werden.

## Log-Dateien

Logs werden in folgenden Dateien gespeichert:
- `logs/api.log` - API-Anwendung
- `logs/mgmt.log` - Management-Anwendung
- `logs/iot.log` - IoT-Anwendung
- `logs/kiosk.log` - Kiosk-Anwendung
- `logs/game.log` - Game-Anwendung
- `logs/django.log` - Django-Framework (nur WARNING+)
- `logs/gunicorn_access.log` - Gunicorn Access-Logs
- `logs/gunicorn_error.log` - Gunicorn Error-Logs

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
# API-Logs
tail -f logs/api.log

# Management-Logs
tail -f logs/mgmt.log

# Alle App-Logs gleichzeitig
tail -f logs/*.log
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
