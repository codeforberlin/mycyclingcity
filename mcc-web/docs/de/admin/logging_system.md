# Logging-System - Detaillierte Dokumentation

## Übersicht

Das MyCyclingCity Logging-System ist ein mehrstufiges System, das Logs in verschiedenen Ausgabekanälen speichert:
- **Console** (für Entwicklung)
- **Dateien** (`app_all.log`, `app_warning_error.log`)
- **Datenbank** (für Admin-GUI-Anzeige)

## Architektur

```
┌─────────────────────────────────────────────────────────────┐
│                    Application Code                         │
│  (api/views.py, game/views.py, etc.)                        │
│                                                             │
│  logger = logging.getLogger(__name__)                      │
│  logger.warning("Message")                                  │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│              Django Logging Framework                       │
│                                                             │
│  - Root Logger (Level: INFO)                               │
│  - App-spezifische Logger (z.B. 'api.views')              │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                    Handler Layer                            │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │   Console    │  │ File Handler  │  │  Database    │    │
│  │   Handler    │  │  (2 Dateien)  │  │   Handler    │    │
│  └──────────────┘  └──────────────┘  └──────────────┘    │
└─────────────────────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                    Output Targets                           │
│                                                             │
│  - Terminal/Console                                         │
│  - app_all.log (alle Logs)                                  │
│  - app_warning_error.log (nur WARNING+)                     │
│  - ApplicationLog (Datenbank)                               │
└─────────────────────────────────────────────────────────────┘
```

## Komponenten im Detail

### 1. Logger-Initialisierung im Code

In den Views und anderen Modulen wird ein Logger wie folgt initialisiert:

```python
import logging

logger = logging.getLogger(__name__)
```

**Beispiel aus `api/views.py`:**
- Logger-Name: `api.views`
- Verwendung: `logger.warning()`, `logger.error()`, `logger.info()`

**Wichtig:** Der Logger-Name entspricht dem Modulnamen (`__name__`), was eine präzise Zuordnung ermöglicht.

### 2. Django Logging-Konfiguration (`config/settings.py`)

Die Logging-Konfiguration ist in `settings.py` definiert:

```python
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '[{levelname}] {asctime} {name}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        'file_warning_error': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(LOGS_DIR / 'app_warning_error.log'),
            'maxBytes': 10 * 1024 * 1024,  # 10 MB
            'backupCount': 5,
            'formatter': 'verbose',
            'level': 'WARNING',  # Nur WARNING und höher
        },
        'file_all': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(LOGS_DIR / 'app_all.log'),
            'maxBytes': 50 * 1024 * 1024,  # 50 MB
            'backupCount': 10,
            'formatter': 'verbose',
            'level': 'DEBUG',  # Alle Logs
        },
        'database': {
            'class': 'mgmt.logging_handler.DatabaseLogHandler',
            'level': 'DEBUG',  # Empfängt alle Logs, Filterung im Handler
            'batch_size': 10,
            'flush_interval': 5.0,
        },
    },
    'root': {
        'handlers': ['console', 'file_warning_error', 'file_all', 'database'],
        'level': 'INFO',  # Globales Minimum-Level
    },
    'loggers': {
        'api': {
            'handlers': ['console', 'file_warning_error', 'file_all', 'database'],
            'level': 'INFO',
            'propagate': True,  # WICHTIG: Logs werden an Root-Logger weitergegeben
        },
    },
}
```

**Wichtige Punkte:**
- **Root Logger Level:** `INFO` - Alle Logs unter INFO werden ignoriert
- **Propagate:** `True` für `api` Logger - Logs werden an Root-Logger weitergegeben
- **Handler Level:** Jeder Handler kann ein eigenes Minimum-Level haben

### 3. DatabaseLogHandler (`mgmt/logging_handler.py`)

Der `DatabaseLogHandler` ist ein **asynchroner Batch-Handler**, der Logs in die Datenbank schreibt.

#### Funktionsweise:

1. **Initialisierung:**
   ```python
   handler = DatabaseLogHandler(batch_size=10, flush_interval=5.0)
   ```
   - Erstellt eine Queue für Log-Einträge
   - Startet einen Background-Worker-Thread
   - Empfängt alle Log-Level (DEBUG und höher)

2. **Log-Empfang (`emit`-Methode):**
   ```python
   def emit(self, record):
       # 1. Prüft, ob Log-Level gespeichert werden soll
       if not self._should_store(record.levelno):
           return
       
       # 2. Formatiert den Log-Record
       log_entry = self._format_record(record)
       
       # 3. Fügt Log in Queue ein (non-blocking)
       self.log_queue.put(log_entry, block=False)
   ```

3. **Level-Filterung (`_should_store`-Methode):**
   ```python
   def _should_store(self, levelno):
       # 1. Liest LoggingConfig aus Datenbank
       config = LoggingConfig.get_config()
       
       # 2. Prüft, ob Level gespeichert werden soll
       return config.should_store_level(level_str)
   ```
   
   **Standard:** Nur WARNING, ERROR, CRITICAL werden gespeichert
   **Konfigurierbar:** Über `LoggingConfig` im Admin-GUI

4. **Batch-Verarbeitung (`_worker`-Thread):**
   ```python
   def _worker(self):
       while not self._shutdown:
           # 1. Sammelt Logs in Batch (max. batch_size)
           entry = self.log_queue.get(timeout=1.0)
           self.batch.append(entry)
           
           # 2. Flusht Batch wenn:
           #    - batch_size erreicht ODER
           #    - flush_interval überschritten
           if len(self.batch) >= self.batch_size or timeout:
               self._flush_batch()
   ```

5. **Datenbank-Schreiben (`_flush_batch`-Methode):**
   ```python
   def _flush_batch(self):
       # Bulk-Insert für Performance
       with transaction.atomic():
           log_entries = [ApplicationLog(**entry) for entry in self.batch]
           ApplicationLog.objects.bulk_create(log_entries, ignore_conflicts=True)
   ```

**Vorteile:**
- **Asynchron:** Blockiert nicht den Haupt-Thread
- **Batch-Inserts:** Bessere Performance durch Bulk-Operationen
- **Konfigurierbar:** Level-Filterung über Admin-GUI
- **Robust:** Fehlerbehandlung verhindert Abstürze

### 4. LoggingConfig (`mgmt/models.py`)

Das `LoggingConfig`-Model ist ein **Singleton**, das steuert, welche Log-Level in der Datenbank gespeichert werden.

```python
class LoggingConfig(models.Model):
    min_log_level = models.CharField(
        max_length=10,
        choices=MIN_LOG_LEVEL_CHOICES,
        default='WARNING',
    )
    
    @classmethod
    def get_config(cls):
        """Singleton-Pattern: Gibt immer die gleiche Instanz zurück."""
        config, _ = cls.objects.get_or_create(pk=1, defaults={'min_log_level': 'WARNING'})
        return config
    
    def should_store_level(self, level):
        """Prüft, ob ein Level gespeichert werden soll."""
        level_order = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        min_level_index = level_order.index(self.min_log_level)
        log_level_index = level_order.index(level)
        return log_level_index >= min_level_index
```

**Verfügbare Level:**
- `DEBUG`: Alle Logs (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- `INFO`: Informative und kritische Logs (INFO, WARNING, ERROR, CRITICAL)
- `WARNING`: Nur kritische Logs (WARNING, ERROR, CRITICAL) - **Standard**
- `ERROR`: Nur Fehler (ERROR, CRITICAL)
- `CRITICAL`: Nur kritische Fehler

### 5. ApplicationLog (`mgmt/models.py`)

Das `ApplicationLog`-Model speichert die Log-Einträge in der Datenbank:

```python
class ApplicationLog(models.Model):
    level = models.CharField(max_length=10, choices=LEVEL_CHOICES)
    logger_name = models.CharField(max_length=100)  # z.B. 'api.views'
    message = models.TextField()
    module = models.CharField(max_length=200)  # z.B. 'views'
    timestamp = models.DateTimeField(auto_now_add=True)
    exception_info = models.TextField(blank=True, null=True)  # Traceback
    extra_data = models.JSONField(blank=True, null=True)  # Zusätzliche Daten
```

**Indizes:**
- `level` + `timestamp` (für Filterung nach Level)
- `logger_name` + `timestamp` (für Filterung nach Logger)
- `timestamp` (für Sortierung)

## Datenfluss - Beispiel

### Beispiel: API-Request mit ungültigem API-Key

1. **Code in `api/views.py`:**
   ```python
   logger = logging.getLogger(__name__)  # Logger-Name: 'api.views'
   
   def update_data(request):
       if not validate_api_key(api_key):
           logger.warning(f"Invalid API key: {api_key}")
           return JsonResponse({'error': 'Invalid API key'}, status=401)
   ```

2. **Logger-Verarbeitung:**
   - Logger `api.views` erhält WARNING-Level
   - Logger hat `propagate=True` → Log wird an Root-Logger weitergegeben

3. **Handler-Verarbeitung:**
   - **Console Handler:** Schreibt sofort in Terminal
     ```
     [WARNING] 2026-01-22 18:35:19 api.views: Invalid API key: abc123
     ```
   - **File Handler (warning_error):** Schreibt in `app_warning_error.log`
   - **File Handler (all):** Schreibt in `app_all.log`
   - **Database Handler:** 
     - Prüft `LoggingConfig.should_store_level('WARNING')` → `True`
     - Formatiert Record → `{'level': 'WARNING', 'logger_name': 'api.views', ...}`
     - Fügt in Queue ein

4. **Datenbank-Schreiben (asynchron):**
   - Worker-Thread sammelt Logs in Batch
   - Nach 10 Logs oder 5 Sekunden → `_flush_batch()`
   - Bulk-Insert in `ApplicationLog`-Tabelle

5. **Admin-GUI:**
   - Log erscheint in "Application Logs" im Admin
   - Filterbar nach Level, Logger-Name, Datum

## Konfiguration

### Log-Level im Code ändern

**Standard:** `logger.warning()`, `logger.error()`, `logger.info()`

**Verfügbare Methoden:**
- `logger.debug()` - Detaillierte Debug-Informationen
- `logger.info()` - Informative Meldungen
- `logger.warning()` - Warnungen (werden standardmäßig gespeichert)
- `logger.error()` - Fehler
- `logger.critical()` - Kritische Fehler

### Datenbank-Logging konfigurieren

**Im Admin-GUI:**
1. Gehe zu "Management" → "Logging Configuration"
2. Wähle "Minimum Log Level"
3. Speichere

**Programmatisch:**
```python
from mgmt.models import LoggingConfig

config = LoggingConfig.get_config()
config.min_log_level = 'INFO'  # Jetzt werden auch INFO-Logs gespeichert
config.save()
```

### Logger-Level ändern

**In `settings.py`:**
```python
'loggers': {
    'api': {
        'level': 'DEBUG',  # Jetzt werden auch DEBUG-Logs verarbeitet
    },
}
```

**Wichtig:** Auch wenn der Logger-Level auf DEBUG gesetzt ist, werden DEBUG-Logs nur in der Datenbank gespeichert, wenn `LoggingConfig.min_log_level = 'DEBUG'` ist.

## Performance-Optimierungen

1. **Batch-Processing:**
   - Logs werden in Batches von 10 gesammelt
   - Bulk-Insert statt einzelner Inserts
   - Reduziert Datenbank-Overhead

2. **Asynchrones Schreiben:**
   - Background-Thread blockiert nicht den Haupt-Thread
   - API-Requests werden nicht durch Logging verlangsamt

3. **Queue-basierte Architektur:**
   - Non-blocking Queue-Einfügungen
   - Bei voller Queue werden Logs verworfen (statt Blockierung)

4. **Level-Filterung:**
   - Frühe Filterung verhindert unnötige Verarbeitung
   - Nur relevante Logs werden formatiert und gespeichert

## Fehlerbehandlung

Der `DatabaseLogHandler` ist robust gegen Fehler:

1. **Datenbank-Fehler:**
   - Wenn Datenbank nicht verfügbar → Fallback auf Settings
   - Fehler werden in Console geloggt (nicht rekursiv)

2. **Queue-Überlauf:**
   - Wenn Queue voll → Log wird verworfen
   - Verhindert Blockierung des Haupt-Threads

3. **Worker-Thread-Fehler:**
   - Exceptions werden abgefangen
   - Thread läuft weiter (mit 1s Pause)

## Debugging

### Logs in Dateien prüfen

```bash
# Alle Logs
tail -f logs/app_all.log

# Nur Warnings/Errors
tail -f logs/app_warning_error.log

# Gunicorn-Logs
tail -f logs/gunicorn_error.log
```

### Logs in Datenbank prüfen

**Im Admin-GUI:**
- "Management" → "Application Logs"
- Filterbar nach Level, Logger-Name, Datum

**Programmatisch:**
```python
from mgmt.models import ApplicationLog

# Alle WARNING-Logs
logs = ApplicationLog.objects.filter(level='WARNING')

# Logs von einem bestimmten Logger
logs = ApplicationLog.objects.filter(logger_name='api.views')

# Neueste Logs
logs = ApplicationLog.objects.all()[:10]
```

### Handler-Status prüfen

Der Handler schreibt Debug-Ausgaben in `stderr` (erscheint in `gunicorn_error.log`):

```
[DatabaseLogHandler] Queued WARNING from api.views: Invalid API key
[DatabaseLogHandler] Flushed 1 log entries to database
```

## Best Practices

1. **Logger-Namen:**
   - Immer `logging.getLogger(__name__)` verwenden
   - Ermöglicht präzise Filterung nach Modul

2. **Log-Level:**
   - `DEBUG`: Nur für detaillierte Debug-Informationen
   - `INFO`: Für normale Operationen (z.B. erfolgreiche API-Requests)
   - `WARNING`: Für potenzielle Probleme (z.B. ungültige API-Keys)
   - `ERROR`: Für Fehler, die behoben werden müssen
   - `CRITICAL`: Für kritische Systemfehler

3. **Exception-Logging:**
   ```python
   try:
       # Code
   except Exception as e:
       logger.error("Fehler beim Verarbeiten", exc_info=True)
       # exc_info=True fügt Traceback hinzu
   ```

4. **Extra-Daten:**
   ```python
   logger.warning("API-Request fehlgeschlagen", extra={
       'user_id': user.id,
       'request_path': request.path,
   })
   ```

## Zusammenfassung

Das Logging-System ist ein **mehrstufiges, asynchrones System** mit folgenden Eigenschaften:

✅ **Multi-Channel:** Console, Dateien, Datenbank  
✅ **Asynchron:** Blockiert nicht den Haupt-Thread  
✅ **Batch-Processing:** Optimierte Datenbank-Inserts  
✅ **Konfigurierbar:** Level-Filterung über Admin-GUI  
✅ **Robust:** Fehlerbehandlung verhindert Abstürze  
✅ **Performance-optimiert:** Queue-basiert, Bulk-Inserts  

Die Logs sind in der Admin-GUI sichtbar und können nach Level, Logger-Name und Datum gefiltert werden.
