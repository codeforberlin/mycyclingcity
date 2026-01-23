# Logging-Konfiguration im Admin GUI

## Übersicht

Das Log-Level für die Anzeige von Logs im Admin GUI kann jetzt direkt über das Admin Interface gesteuert werden, ohne Environment-Variablen ändern zu müssen.

## Verwendung

### Im Admin GUI

1. **Admin GUI öffnen**: `/admin/`
2. **Navigation**: "Mgmt" → "Logging Configuration"
3. **URL direkt**: `/admin/mgmt/loggingconfig/`
4. **Log-Level auswählen**:
   - **DEBUG** - Alle Logs (DEBUG, INFO, WARNING, ERROR, CRITICAL)
   - **INFO** - Informative und kritische Logs (INFO, WARNING, ERROR, CRITICAL)
   - **WARNING** - Nur kritische Logs (WARNING, ERROR, CRITICAL) - **Standard**
   - **ERROR** - Nur Fehler (ERROR, CRITICAL)
   - **CRITICAL** - Nur kritische Fehler

5. **Speichern** - Änderungen gelten sofort für neue Log-Einträge

### Über Command Line (für Deployment/Setup)

#### Standard-Wert setzen:

```bash
# Standard (WARNING)
python manage.py set_logging_level WARNING

# Alle Logs aktivieren
python manage.py set_logging_level DEBUG

# Nur Fehler
python manage.py set_logging_level ERROR
```

#### Von Environment-Variable lesen:

```bash
# Liest LOG_DB_DEBUG aus .env (True=DEBUG, False=WARNING)
python manage.py set_logging_level --from-env
```

#### Auf Standard zurücksetzen:

```bash
python manage.py set_logging_level --default
```

## Funktionsweise

### Priorität

1. **Datenbank-Konfiguration** (LoggingConfig Model) - **Höchste Priorität**
   - Wird im Admin GUI verwaltet
   - Gilt sofort für neue Log-Einträge
   - Persistiert über Server-Neustarts

2. **Environment-Variable** (LOG_DB_DEBUG) - **Fallback**
   - Wird nur verwendet, wenn Datenbank-Konfiguration nicht verfügbar ist
   - Nützlich während Migrationen oder wenn die Tabelle noch nicht existiert

### Singleton-Pattern

Die LoggingConfig ist ein Singleton-Model - es existiert nur eine Instanz. Beim ersten Zugriff wird automatisch eine Instanz mit dem Standard-Wert (WARNING) erstellt.

## Migration und Setup

### Erste Einrichtung

Nach der Migration:

```bash
# Migration ausführen
python manage.py migrate mgmt

# Standard-Wert setzen (optional, wird automatisch erstellt)
python manage.py set_logging_level WARNING
```

### Deployment

In Deployment-Skripten können Sie den Default-Wert setzen:

```bash
# In deploy.sh oder ähnlich
python manage.py set_logging_level --from-env
```

Oder direkt:

```bash
python manage.py set_logging_level WARNING
```

## Beispiel-Workflow

### Entwicklung mit DEBUG-Logs

1. Im Admin GUI: "Mgmt" → "Logging Configuration"
2. Log-Level auf "DEBUG" ändern
3. Speichern
4. Neue Logs werden sofort mit DEBUG-Level gespeichert

### Produktion mit nur kritischen Logs

1. Im Admin GUI: "Mgmt" → "Logging Configuration"
2. Log-Level auf "WARNING" oder "ERROR" ändern
3. Speichern
4. Nur kritische Logs werden gespeichert

## Wichtige Hinweise

### ⚠️ Datenbank-Größe

- **DEBUG/INFO**: Kann die Datenbank schnell wachsen
- **WARNING/ERROR**: Empfohlen für Produktion
- Regelmäßige Bereinigung mit `cleanup_application_logs` empfohlen

### 🔄 Sofortige Wirkung

Änderungen im Admin GUI gelten **sofort** für neue Log-Einträge. Bereits gespeicherte Logs werden nicht gelöscht.

### 📊 Best Practices

- **Entwicklung**: DEBUG oder INFO
- **Staging**: INFO oder WARNING
- **Produktion**: WARNING oder ERROR
- **Kritische Systeme**: ERROR oder CRITICAL

## Troubleshooting

### Konfiguration wird nicht übernommen

1. Prüfen Sie, ob die Migration ausgeführt wurde:
   ```bash
   python manage.py showmigrations mgmt
   ```

2. Prüfen Sie die aktuelle Konfiguration:
   ```bash
   python manage.py shell
   >>> from mgmt.models import LoggingConfig
   >>> config = LoggingConfig.get_config()
   >>> print(config.min_log_level)
   ```

3. Konfiguration zurücksetzen:
   ```bash
   python manage.py set_logging_level --default
   ```

### Fallback auf Environment-Variable

Wenn die Datenbank-Konfiguration nicht verfügbar ist (z.B. während Migrationen), fällt das System automatisch auf die `LOG_DB_DEBUG` Environment-Variable zurück.

## Migration von alter Konfiguration

Wenn Sie vorher `LOG_DB_DEBUG=True` in der `.env` verwendet haben:

```bash
# Migration ausführen
python manage.py migrate mgmt

# Konfiguration von Environment-Variable übernehmen
python manage.py set_logging_level --from-env
```

Danach können Sie `LOG_DB_DEBUG` aus der `.env` entfernen und alles über das Admin GUI steuern.
