# Logger-Initialisierung - Wann werden Logger erstellt?

## Kurze Antwort

**Logger werden erst beim ersten Import/Verwendung des Moduls initialisiert, NICHT beim Serverstart.**

Das bedeutet:
- ✅ **Beim Serverstart**: Keine Logs in App-Logdateien (außer wenn Module explizit importiert werden)
- ✅ **Beim ersten API-Request**: Logger wird initialisiert → "[Logger Init]" Log erscheint
- ✅ **Beim ersten GUI-Aufruf**: Logger wird initialisiert → "[Logger Init]" Log erscheint

## Detaillierte Erklärung

### 1. Python/Django Lazy Loading

Django verwendet **Lazy Loading** für Views und Models:
- Module werden erst importiert, wenn sie tatsächlich benötigt werden
- Beim Serverstart werden nur die **URL-Konfiguration** und **Settings** geladen
- Views werden erst beim ersten Request importiert

### 2. Logger-Initialisierung

```python
# In api/views.py (Modulebene)
from config.logger_utils import get_logger
logger = get_logger(__name__)  # Wird beim Import des Moduls ausgeführt
```

**Wann wird `api/views.py` importiert?**
- ❌ **NICHT** beim Serverstart
- ✅ **Beim ersten API-Request** zu einem Endpoint in `api/views.py`
- ✅ **Beim ersten Import** des Moduls (z.B. in Tests)

### 3. Was passiert beim Serverstart?

```python
# config/wsgi.py
application = get_wsgi_application()  # Lädt Settings, aber keine Views
```

**Geladen werden:**
- ✅ Settings (`config.settings`)
- ✅ URL-Konfiguration (`config.urls`)
- ✅ Middleware-Klassen (nur die Klassen, nicht die Views)
- ✅ Models (nur die Model-Definitionen, nicht die Views)

**NICHT geladen werden:**
- ❌ View-Funktionen (werden erst bei Request importiert)
- ❌ Logger in Views (werden erst bei View-Import erstellt)

### 4. Logger-Initialisierungs-Log

Die `get_logger()` Funktion schreibt einen INFO-Log beim ersten Aufruf:

```python
def get_logger(name):
    logger = logging.getLogger(name)
    if not hasattr(logger, '_mcc_initialized'):
        logger._mcc_initialized = True
        root_logger.info(f"[Logger Init] Logger '{name}' initialized ...")
    return logger
```

**Wann erscheint dieser Log?**
- Beim ersten Import des Moduls, das `get_logger()` verwendet
- Also beim ersten API-Request oder GUI-Aufruf

## Beispiel-Ablauf

### Serverstart (keine Logs)
```bash
gunicorn --workers 5 --threads 2 --bind 0.0.0.0:8001 config.wsgi:application
```

**Was passiert:**
1. Django lädt Settings
2. Django lädt URL-Konfiguration
3. **Keine Views werden importiert**
4. **Keine Logger werden initialisiert**
5. **Keine Logs in `api.log`, `mgmt.log`, etc.**

### Erster API-Request
```bash
curl -X POST http://localhost:8001/api/update-data \
  -H "X-Api-Key: test-key" \
  -H "Content-Type: application/json" \
  -d '{"id_tag": "test", "device_id": "test", "distance": 1.0}'
```

**Was passiert:**
1. Django findet Route in `api.urls`
2. Django importiert `api.views` (erst jetzt!)
3. `logger = get_logger(__name__)` wird ausgeführt
4. `[Logger Init] Logger 'api.views' initialized ...` wird geloggt
5. View-Funktion wird ausgeführt
6. Weitere Logs werden geschrieben

**Ergebnis in `logs/api.log`:**
```
INFO 2026-01-23 08:00:00,000 api.views: [Logger Init] Logger 'api.views' initialized ...
INFO 2026-01-23 08:00:00,100 api.views: [update_data] Incoming request ...
```

### Erster GUI-Aufruf
```bash
# Browser öffnet /admin/
```

**Was passiert:**
1. Django findet Route in `config.urls`
2. Django importiert Admin-Views (erst jetzt!)
3. Wenn Admin-Views `get_logger()` verwenden → Logger wird initialisiert
4. `[Logger Init]` Log erscheint

## Praktische Konsequenzen

### ✅ Normal: Leere Logdateien beim Start

```bash
# Nach Serverstart
ls -lh logs/*.log
# api.log: 0 Bytes (leer)
# mgmt.log: 0 Bytes (leer)
# iot.log: 0 Bytes (leer)
```

**Das ist normal und erwartet!**

### ✅ Erste Logs erscheinen beim ersten Request

```bash
# Nach erstem API-Request
tail logs/api.log
# INFO 2026-01-23 08:00:00,000 api.views: [Logger Init] Logger 'api.views' initialized ...
# INFO 2026-01-23 08:00:00,100 api.views: [update_data] Incoming request ...
```

## Ausnahmen: Module, die beim Start geladen werden

### 1. Middleware
```python
# mgmt/middleware_request_logging.py
logger = get_logger(__name__)  # Wird beim Start geladen!
```

**Warum?** Middleware wird beim Serverstart importiert.

**Ergebnis:** `[Logger Init] Logger 'mgmt.middleware_request_logging' initialized ...` erscheint beim Start.

### 2. App `ready()` Methoden
```python
# game/apps.py
def ready(self):
    from . import signals  # Wird beim Start geladen
```

**Wenn** `signals.py` einen Logger hat → Logger wird beim Start initialisiert.

### 3. URL-Konfiguration (nur wenn Views direkt importiert werden)
```python
# config/urls.py
from api.views import some_view  # Wird beim Start geladen!
```

**Aber:** Django verwendet normalerweise `include()`, was lazy loading ermöglicht.

## Best Practices

### 1. Logger-Initialisierung erwarten
- Erwarten Sie keine Logs beim Serverstart
- Erste Logs erscheinen beim ersten Request/Aufruf
- Das ist normal und effizient (spart Ressourcen)

### 2. Server-Status prüfen
```bash
# Prüfen, ob Server läuft
curl http://localhost:8001/health/

# Prüfen, ob Logs funktionieren
curl -X POST http://localhost:8001/api/update-data ...
tail -f logs/api.log
```

### 3. Logger-Initialisierung testen
```python
# In Django Shell
python manage.py shell
>>> from api.views import logger
>>> logger.info("Test")
>>> # Prüfen Sie logs/api.log
```

## Zusammenfassung

| Zeitpunkt | Logger initialisiert? | Logs in Dateien? |
|-----------|---------------------|------------------|
| **Serverstart** | ❌ Nein (außer Middleware) | ❌ Nein |
| **Erster API-Request** | ✅ Ja | ✅ Ja |
| **Erster GUI-Aufruf** | ✅ Ja | ✅ Ja |
| **Tests** | ✅ Ja (beim Import) | ✅ Ja |

**Fazit:** Leere Logdateien beim Serverstart sind **normal und erwartet**. Logger werden erst bei Bedarf (lazy loading) initialisiert.
