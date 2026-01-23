# Application Logs im Admin GUI

## Übersicht

Das Application Logging System speichert kritische Logmeldungen (WARNING, ERROR, CRITICAL) in der Datenbank, damit sie im Django Admin GUI angezeigt werden können.

## Wann sind Logs sichtbar?

### 1. Migration ausgeführt
Die Datenbank-Tabelle muss existieren:
```bash
python manage.py migrate mgmt
```

### 2. Log-Level
**Standardmäßig werden nur folgende Log-Level gespeichert:**
- ✅ **WARNING** - Warnungen
- ✅ **ERROR** - Fehler
- ✅ **CRITICAL** - Kritische Fehler

**Nicht gespeichert (standardmäßig):**
- ❌ **DEBUG** - Debug-Informationen
- ❌ **INFO** - Informationsmeldungen

### 3. Batch-Processing
Der Handler verwendet Batch-Processing für bessere Performance:
- **Batch-Größe**: 10 Einträge
- **Flush-Intervall**: 5 Sekunden

**Das bedeutet:** Logs erscheinen im Admin erst nach:
- 10 gesammelten Log-Einträgen ODER
- 5 Sekunden Wartezeit

### 4. Handler-Konfiguration
Der Handler muss in `config/settings.py` korrekt konfiguriert sein:
```python
'handlers': {
    'database': {
        'class': 'mgmt.logging_handler.DatabaseLogHandler',
        'level': 'WARNING',
        'batch_size': 10,
        'flush_interval': 5.0,
    },
}
```

## Logs im Admin anzeigen

1. **Admin GUI öffnen**: `/admin/`
2. **Navigation**: "Mgmt" → "Application Logs"
3. **URL direkt**: `/admin/mgmt/applicationlog/`

## Features im Admin

- **Filterung**: Nach Level, Logger-Name, Datum
- **Suche**: In Message, Logger-Name, Module, Exception-Info
- **Farbcodierung**: 
  - WARNING: Orange
  - ERROR: Rot
  - CRITICAL: Dunkelrot
- **Sortierung**: Standardmäßig nach neuestem zuerst

## Testen des Logging-Systems

### Management-Command verwenden:
```bash
python manage.py test_logging
```

Dieses Command:
- Prüft, ob die Tabelle existiert
- Generiert Test-Logs (WARNING, ERROR, CRITICAL)
- Wartet auf Batch-Processing
- Zeigt an, ob Logs erstellt wurden

### Manuell testen:
```python
import logging
logger = logging.getLogger('api')
logger.warning("Test WARNING message")
logger.error("Test ERROR message")
```

**Wichtig**: Warten Sie 5-6 Sekunden, bevor Sie im Admin nachsehen!

## DEBUG/INFO Logs aktivieren

Um auch DEBUG und INFO Logs zu speichern, setzen Sie in `.env`:
```env
LOG_DB_DEBUG=True
```

**Warnung**: Dies kann die Datenbank schnell füllen!

## Häufige Probleme

### Problem: Keine Logs im Admin sichtbar

**Lösung 1: Migration prüfen**
```bash
python manage.py migrate mgmt
python manage.py showmigrations mgmt
```

**Lösung 2: Test-Logs generieren**
```bash
python manage.py test_logging
```

**Lösung 3: Warten auf Batch-Flush**
- Warten Sie 5-6 Sekunden nach dem Generieren von Logs
- Oder generieren Sie 10+ Logs, dann wird sofort geflusht

**Lösung 4: Handler-Konfiguration prüfen**
- Prüfen Sie `config/settings.py` - ist der 'database' Handler konfiguriert?
- Prüfen Sie, ob die Logger den 'database' Handler verwenden

**Lösung 5: Log-Level prüfen**
- Nur WARNING, ERROR, CRITICAL werden standardmäßig gespeichert
- INFO/DEBUG werden nur gespeichert, wenn `LOG_DB_DEBUG=True`

### Problem: Logs erscheinen verzögert

Das ist normal! Der Handler verwendet Batch-Processing:
- Maximale Verzögerung: 5 Sekunden
- Oder sofort bei 10+ Logs

### Problem: Zu viele Logs

Verwenden Sie das Cleanup-Command:
```bash
# Logs älter als 30 Tage löschen
python manage.py cleanup_application_logs --days 30

# Nur DEBUG/INFO Logs löschen
python manage.py cleanup_application_logs --days 7 --level INFO
```

## Log-Dateien

Zusätzlich zur Datenbank werden Logs auch in Dateien gespeichert:
- `logs/app_warning_error.log` - Nur WARNING, ERROR, CRITICAL
- `logs/app_all.log` - Alle Log-Level

Diese Dateien können für detailliertes Debugging verwendet werden.

## Best Practices

1. **Regelmäßige Bereinigung**: Setzen Sie einen Cron-Job für `cleanup_application_logs`
2. **Monitoring**: Prüfen Sie regelmäßig kritische Logs im Admin
3. **Performance**: Der Batch-Handler ist für Produktion optimiert
4. **Retention**: Definieren Sie eine Retention-Policy (z.B. 30 Tage)

## Cron-Job Beispiel

```bash
# Täglich um 2 Uhr morgens Logs älter als 30 Tage löschen
0 2 * * * cd /path/to/mcc-web && python manage.py cleanup_application_logs --days 30
```
