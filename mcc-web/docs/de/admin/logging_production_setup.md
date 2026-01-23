# Production Logging Setup - Best Practices

## Übersicht

Das Logging-System ist nach **Production Best Practices** konfiguriert:

- ✅ **App-spezifische Logdateien**: Jede Anwendung schreibt in ihre eigene Datei
- ✅ **Root-Logger auf WARNING**: Nur kritische Fehler erreichen Gunicorn
- ✅ **Keine Propagation**: App-Logs werden NICHT an Gunicorn weitergegeben
- ✅ **Separate Django-Logs**: Framework-Logs in separater Datei

## Log-Dateien Struktur

```
logs/
├── api.log          # API-Anwendung (api.views, api.models, etc.)
├── mgmt.log         # Management-Anwendung (mgmt.admin, mgmt.views, etc.)
├── iot.log           # IoT-Anwendung (iot.models, iot.views, etc.)
├── kiosk.log         # Kiosk-Anwendung (kiosk.views, etc.)
├── game.log          # Game-Anwendung (game.views, game.models, etc.)
├── django.log        # Django-Framework (nur WARNING+)
├── gunicorn_access.log  # Gunicorn Access-Logs
└── gunicorn_error.log   # Gunicorn Error-Logs (nur kritische Fehler)
```

## Konfiguration

### Root-Logger
- **Level**: `WARNING` (nicht DEBUG!)
- **Handler**: Nur `django_file` (Django-Framework-Logs)
- **Zweck**: Fängt nur kritische Django-Framework-Fehler ab

### App-Logger (api, mgmt, iot, kiosk, game)
- **Level**: `DEBUG` (kann auf `INFO` für Production geändert werden)
- **Handler**: 
  - App-spezifische Datei (z.B. `api_file` → `api.log`)
  - `database` (für Admin-GUI)
- **Propagate**: `False` ⚠️ **KRITISCH**: Verhindert, dass Logs an Root-Logger/Gunicorn weitergegeben werden

### Django-Framework-Logger
- **Level**: `WARNING`
- **Handler**: `django_file` → `django.log`
- **Propagate**: `False`

## Warum diese Konfiguration?

### 1. Separation of Concerns
Jede Anwendung hat ihre eigene Logdatei, was das Debugging erleichtert:
- API-Probleme → `logs/api.log`
- Management-Probleme → `logs/mgmt.log`
- etc.

### 2. Gunicorn wird nicht belastet
- `propagate=False` verhindert, dass App-Logs an Root-Logger weitergegeben werden
- Root-Logger auf `WARNING` → nur kritische Fehler erreichen Gunicorn
- `gunicorn_error.log` bleibt sauber und enthält nur echte Server-Fehler

### 3. Skalierbarkeit
- Jede App kann unabhängig konfiguriert werden
- Log-Level können pro App angepasst werden
- Datei-Rotation pro App (50 MB, 10 Backups)

## Log-Level anpassen

### Für Production (weniger Logs):
```python
'api': {
    'handlers': ['api_file', 'database'],
    'level': 'INFO',  # Statt DEBUG
    'propagate': False,
},
```

### Für Development (mehr Logs):
```python
'api': {
    'handlers': ['api_file', 'database'],
    'level': 'DEBUG',  # Alle Logs
    'propagate': False,
},
```

## Logs anzeigen

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
- **Management** → **Log File Viewer**
- Wählen Sie die gewünschte Logdatei aus
- Filterbar nach Level, Datum, etc.

### In der Datenbank:
- **Management** → **Application Logs**
- Nur WARNING/ERROR/CRITICAL (standardmäßig)
- Konfigurierbar über **Logging Configuration**

## Best Practices

### 1. Log-Level richtig setzen
- **DEBUG**: Nur für detailliertes Debugging
- **INFO**: Normale Operationen (empfohlen für Production)
- **WARNING**: Potenzielle Probleme
- **ERROR**: Fehler, die behoben werden müssen
- **CRITICAL**: Kritische Systemfehler

### 2. Regelmäßige Bereinigung
```bash
# Logs älter als 30 Tage löschen
python manage.py cleanup_application_logs --days 30
```

### 3. Monitoring
- Prüfen Sie regelmäßig `logs/django.log` für Framework-Fehler
- Prüfen Sie `logs/gunicorn_error.log` für Server-Fehler
- Verwenden Sie die Admin-GUI für kritische App-Logs

### 4. Log-Rotation
- Automatische Rotation bei 50 MB pro Datei
- 10 Backups pro App-Logdatei
- 5 Backups für Django-Logs

## Troubleshooting

### Problem: Keine Logs in App-Dateien
**Lösung**: Prüfen Sie, ob `propagate=False` gesetzt ist

### Problem: Zu viele Logs in Gunicorn
**Lösung**: Prüfen Sie, ob Root-Logger auf `WARNING` steht und App-Logger `propagate=False` haben

### Problem: Logs erscheinen nicht
**Lösung**: 
1. Prüfen Sie die Dateiberechtigungen: `chmod 644 logs/*.log`
2. Prüfen Sie, ob die Logger-Level korrekt sind
3. Prüfen Sie, ob die Handler korrekt konfiguriert sind

## Migration von alter Konfiguration

Die alte Konfiguration verwendete:
- `app_all.log` (alle Apps zusammen)
- `app_warning_error.log` (nur WARNING+)
- Propagation an Root-Logger

**Neue Konfiguration:**
- Separate Dateien pro App
- Keine Propagation
- Root-Logger nur für Django-Framework

**Alte Logdateien bleiben erhalten** und können manuell gelöscht werden, wenn nicht mehr benötigt.
