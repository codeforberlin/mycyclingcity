# Konfigurations-Anleitung

Diese Anleitung erklärt, wie Sie die MyCyclingCity Anwendung konfigurieren.

## Umgebungsvariablen

Die Konfiguration erfolgt über Umgebungsvariablen, typischerweise gespeichert in einer `.env` Datei.

**Wichtig:**
- **Produktion**: Die `.env` Datei liegt außerhalb der Software in `/data/appl/mcc/.env`
- **Entwicklung**: Die `.env` Datei kann im Projektverzeichnis (`mcc-web/.env`) oder individuell konfiguriert sein
- Die Anwendung findet die `.env` Datei automatisch, da sie relativ im Projektverzeichnis sucht

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

### SQLite (Standard - Entwicklung und Produktion)

Die Anwendung verwendet SQLite für alle Umgebungen. Keine zusätzliche Konfiguration erforderlich.

**Produktion:**
- Datenbankdatei: `/data/var/mcc/db/db.sqlite3`
- Die Datenbank wird automatisch erstellt, falls sie nicht existiert

**Entwicklung:**
- Datenbankdatei: `data/db.sqlite3` (relativ zum Projektverzeichnis)
- Die Anwendung findet die Datenbank automatisch im Projektverzeichnis

## Statische und Media-Dateien

### STATIC_ROOT

Verzeichnis, in dem statische Dateien gesammelt werden:

**Produktion:**
```env
STATIC_ROOT=/data/appl/mcc/mcc-web/staticfiles
```

**Entwicklung:**
- Kann individuell konfiguriert sein (z.B. `mcc-web/staticfiles`)
- Die Anwendung verwendet relative Pfade im Projektverzeichnis

### MEDIA_ROOT

Verzeichnis für hochgeladene Dateien:

**Produktion:**
```env
MEDIA_ROOT=/data/appl/mcc/mcc-web/media
```

**Entwicklung:**
- Kann individuell konfiguriert sein (z.B. `mcc-web/media`)
- Die Anwendung verwendet relative Pfade im Projektverzeichnis

**Hinweis:** In Entwicklungsumgebungen können die Pfade individuell sein, da die Anwendung relativ im Projektverzeichnis alle Informationen findet.

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

- `logs/mcc_worker.log` - Background-Worker-Logs
- Konsolen-Ausgabe (Entwicklung)

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
  - **Produktion**: `/data/appl/mcc/.env` (außerhalb der Software)
  - **Entwicklung**: `mcc-web/.env` oder individuell konfiguriert
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
