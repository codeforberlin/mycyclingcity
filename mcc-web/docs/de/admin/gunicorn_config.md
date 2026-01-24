# Gunicorn-Konfiguration im Admin GUI

## Übersicht

Der Gunicorn Log-Level kann jetzt direkt über das Admin Interface gesteuert werden, ohne Environment-Variablen ändern zu müssen.

## Verwendung

### Im Admin GUI

1. **Admin GUI öffnen**: `/admin/`
2. **Navigation**: "Mgmt" → "Gunicorn Configuration"
3. **URL direkt**: `/admin/mgmt/gunicornconfig/`
4. **Log-Level auswählen**:
   - **DEBUG** - Sehr detaillierte Ausgaben
   - **INFO** - Informative Meldungen (Standard)
   - **WARNING** - Nur Warnungen
   - **ERROR** - Nur Fehler
   - **CRITICAL** - Nur kritische Fehler
5. **Speichern** - Eine Warnung erscheint, dass ein Neustart erforderlich ist

### Server-Neustart

Nach dem Ändern des Log-Levels:

1. Gehen Sie zu `/admin/server/` (Server Control)
2. Klicken Sie auf "Restart Server"
3. Die neue Konfiguration wird beim Start geladen

## Funktionsweise

### Priorität

1. **Datenbank-Konfiguration** (GunicornConfig Model) - **Höchste Priorität**
   - Wird im Admin GUI verwaltet
   - Wird beim Server-Start aus der Datenbank gelesen
   - Als Environment-Variable `GUNICORN_LOG_LEVEL` an Gunicorn übergeben

2. **Environment-Variable** (GUNICORN_LOG_LEVEL) - **Fallback**
   - Wird nur verwendet, wenn Datenbank-Konfiguration nicht verfügbar ist
   - Nützlich während Migrationen oder wenn die Tabelle noch nicht existiert

3. **Default** - **info**
   - Wenn weder Datenbank noch Environment-Variable verfügbar sind

### Singleton-Pattern

Die GunicornConfig ist ein Singleton-Model - es existiert nur eine Instanz. Beim ersten Zugriff wird automatisch eine Instanz mit dem Standard-Wert (info) erstellt.

## Migration und Setup

### Erste Einrichtung

Nach der Migration:

```bash
# Migration ausführen
python manage.py migrate mgmt

# Standard-Wert wird automatisch erstellt (info)
```

### Deployment

Das Startup-Script liest die Konfiguration automatisch aus der Datenbank beim Start:

```bash
/path/to/mcc-web/scripts/mcc-web.sh start
```

Hinweis: In der aktuellen Produktion läuft die Anwendung als Benutzer `mcc`
unter `/data/games/mcc/mcc-web`. Passen Sie Pfade und Benutzer an Ihre Umgebung an.

Das Script verwendet das Management-Command `get_gunicorn_config`, um die Konfiguration aus der Datenbank zu lesen.

## Beispiel-Workflow

### Log-Level ändern

1. Im Admin GUI: "Mgmt" → "Gunicorn Configuration"
2. Log-Level auf "DEBUG" ändern
3. Speichern
4. Zu "Server Control" gehen (`/admin/server/`)
5. "Restart Server" klicken
6. Neue Konfiguration wird geladen

## Wichtige Hinweise

### ⚠️ Server-Neustart erforderlich

Änderungen am Gunicorn Log-Level erfordern einen **Server-Neustart**, um wirksam zu werden. Die Konfiguration wird nur beim Start geladen.

### 🔄 Sofortige Wirkung

Nach einem Neustart gilt die neue Konfiguration **sofort** für alle neuen Log-Einträge.

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
   >>> from mgmt.models import GunicornConfig
   >>> config = GunicornConfig.get_config()
   >>> print(config.log_level)
   ```

3. Prüfen Sie, ob der Server neu gestartet wurde:
   ```bash
   /path/to/mcc-web/scripts/mcc-web.sh status
   ```

4. Prüfen Sie die Environment-Variable beim Start:
   - Schauen Sie in `logs/gunicorn_startup.log`
   - Das Script sollte "Using log level from database: X" anzeigen

### Fallback auf Environment-Variable

Wenn die Datenbank-Konfiguration nicht verfügbar ist (z.B. während Migrationen), fällt das System automatisch auf die `GUNICORN_LOG_LEVEL` Environment-Variable zurück.

## Integration mit Server Control

Die Gunicorn-Konfiguration ist in die Server-Control-Seite integriert:

- **Server Control** (`/admin/server/`) zeigt das aktuelle Log-Level an
- Direkter Link zur Gunicorn-Konfiguration
- Nach dem Ändern der Konfiguration wird ein Link zum Server-Neustart angezeigt

## Migration von alter Konfiguration

Wenn Sie vorher `GUNICORN_LOG_LEVEL` in der `.env` oder als Environment-Variable verwendet haben:

```bash
# Migration ausführen
python manage.py migrate mgmt

# Konfiguration im Admin GUI setzen
# Oder über Management-Command:
python manage.py shell
>>> from mgmt.models import GunicornConfig
>>> config = GunicornConfig.get_config()
>>> config.log_level = 'info'  # oder 'debug', 'warning', etc.
>>> config.save()
```

Danach können Sie `GUNICORN_LOG_LEVEL` aus der `.env` entfernen und alles über das Admin GUI steuern.
