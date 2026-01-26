# Konfigurations-Anleitung

Diese Anleitung erklärt, wie Sie die MyCyclingCity Anwendung konfigurieren.

## Umgebungsvariablen

Die Konfiguration erfolgt über Umgebungsvariablen, typischerweise gespeichert in einer `.env` Datei im `mcc-web/` Verzeichnis.

## Erforderliche Einstellungen

### SECRET_KEY

Django Secret Key für kryptographische Signierung. **Niemals in die Versionskontrolle committen.**

```env
SECRET_KEY=django-insecure-ihr-geheimer-schlüssel-hier
```

Neuen Secret Key generieren:
```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### DEBUG

Debug-Modus aktivieren (nur Entwicklung):

```env
DEBUG=True  # Entwicklung
DEBUG=False  # Produktion
```

### ALLOWED_HOSTS

Komma-separierte Liste erlaubter Hostnamen:

```env
ALLOWED_HOSTS=localhost,127.0.0.1,mycyclingcity.net
```

## Datenbank-Konfiguration

### SQLite (Standard - Entwicklung)

Keine zusätzliche Konfiguration erforderlich. Die Datenbankdatei wird automatisch erstellt unter:
- **Entwicklung**: `data/db/db.sqlite3`
- **Produktion**: `/data/var/mcc/db/db.sqlite3`

Stellen Sie sicher, dass das Verzeichnis `data/db/` existiert, bevor Sie Migrationen ausführen.

### PostgreSQL (Produktion)

```env
DATABASE_ENGINE=django.db.backends.postgresql
DATABASE_NAME=mycyclingcity
DATABASE_USER=dbuser
DATABASE_PASSWORD=dbpassword
DATABASE_HOST=localhost
DATABASE_PORT=5432
```

## Statische und Media-Dateien

### STATIC_ROOT

Verzeichnis, in dem statische Dateien gesammelt werden:

```env
STATIC_ROOT=/data/games/mcc/mcc-web/staticfiles
```

### MEDIA_ROOT

Verzeichnis für hochgeladene Dateien:

```env
MEDIA_ROOT=/data/games/mcc/mcc-web/media
```

## Internationalisierung

### Unterstützte Sprachen

- Deutsch (de) - Standard
- Englisch (en)

### Sprach-Konfiguration

Konfiguriert in `config/settings.py`:

```python
LANGUAGE_CODE = 'de'
LANGUAGES = [
    ('de', 'Deutsch'),
    ('en', 'English'),
]
```

## API-Konfiguration

### API-Key

Globaler API-Key für Geräte-Authentifizierung:

```env
API_KEY=ihr-api-key-hier
```

### Geräte-spezifische API-Keys

Konfiguriert im Django Admin unter IoT → Device Configurations.

## E-Mail-Konfiguration (Optional)

Für E-Mail-Benachrichtigungen:

```env
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.example.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=ihre-email@example.com
EMAIL_HOST_PASSWORD=ihr-passwort
```

## Logging

Logging ist in `config/settings.py` konfiguriert. Logs werden geschrieben nach:

- **Entwicklung**: `data/logs/` (z.B. `data/logs/mcc_worker.log`)
- **Produktion**: `/data/var/mcc/logs/`
- Konsolen-Ausgabe (Entwicklung)

Das `data/logs/` Verzeichnis wird automatisch erstellt, wenn die Anwendung startet.

## Produktions-Einstellungen

### Sicherheits-Einstellungen

```env
DEBUG=False
ALLOWED_HOSTS=mycyclingcity.net,www.mycyclingcity.net
CSRF_TRUSTED_ORIGINS=https://mycyclingcity.net,https://www.mycyclingcity.net
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
```

### Gunicorn-Konfiguration

Siehe `config/gunicorn_config.py` für Produktions-Server-Einstellungen.

## Umgebungs-spezifische Konfiguration

### Entwicklung

```env
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
```

### Produktion

```env
DEBUG=False
ALLOWED_HOSTS=mycyclingcity.net
SECRET_KEY=<starker-geheimer-schlüssel>
```

## Konfigurationsdateien

- `.env` - Umgebungsvariablen (nicht in Versionskontrolle)
- `config/settings.py` - Django-Einstellungen
- `config/gunicorn_config.py` - Gunicorn-Server-Konfiguration
- `mkdocs.yml` - Dokumentations-Konfiguration

## Validierung

Konfiguration überprüfen:

```bash
python manage.py check --deploy
```

## Nächste Schritte

- [Installations-Anleitung](installation.md) - Zurück zur Installation
- [Admin GUI Handbuch](../admin/index.md) - Über Admin-Interface konfigurieren

Für Produktions-Deployment siehe die `DEPLOYMENT.md` Datei in diesem Verzeichnis.
