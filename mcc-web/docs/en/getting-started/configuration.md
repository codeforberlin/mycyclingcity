# Configuration Guide

This guide explains how to configure the MyCyclingCity application.

## Environment Variables

Configuration is managed through environment variables, typically stored in a `.env` file in the `mcc-web/` directory.

## Required Settings

### SECRET_KEY

Django secret key for cryptographic signing. **Never commit this to version control.**

```env
SECRET_KEY=django-insecure-your-secret-key-here
```

Generate a new secret key:
```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### DEBUG

Enable debug mode (development only):

```env
DEBUG=True  # Development
DEBUG=False  # Production
```

### ALLOWED_HOSTS

Comma-separated list of allowed hostnames:

```env
ALLOWED_HOSTS=localhost,127.0.0.1,mycyclingcity.net
```

## Database Configuration

### SQLite (Default - Development)

No additional configuration needed. Database file: `db.sqlite3`

### PostgreSQL (Production)

```env
DATABASE_ENGINE=django.db.backends.postgresql
DATABASE_NAME=mycyclingcity
DATABASE_USER=dbuser
DATABASE_PASSWORD=dbpassword
DATABASE_HOST=localhost
DATABASE_PORT=5432
```

## Static and Media Files

### STATIC_ROOT

Directory where static files are collected:

```env
STATIC_ROOT=/data/games/mcc/mcc-web/staticfiles
```

### MEDIA_ROOT

Directory for user-uploaded files:

```env
MEDIA_ROOT=/data/games/mcc/mcc-web/media
```

## Internationalization

### Supported Languages

- German (de) - Default
- English (en)

### Language Configuration

Configured in `config/settings.py`:

```python
LANGUAGE_CODE = 'de'
LANGUAGES = [
    ('de', 'Deutsch'),
    ('en', 'English'),
]
```

## API Configuration

### API Key

Global API key for device authentication:

```env
API_KEY=your-api-key-here
```

### Device-Specific API Keys

Configured in Django Admin under IoT → Device Configurations.

## Email Configuration (Optional)

For email notifications:

```env
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.example.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@example.com
EMAIL_HOST_PASSWORD=your-password
```

## Logging

Logging is configured in `config/settings.py`. Logs are written to:

- `logs/mcc_worker.log` - Background worker logs
- Console output (development)

## Production Settings

### Security Settings

```env
DEBUG=False
ALLOWED_HOSTS=mycyclingcity.net,www.mycyclingcity.net
CSRF_TRUSTED_ORIGINS=https://mycyclingcity.net,https://www.mycyclingcity.net
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
```

### Gunicorn Configuration

See `gunicorn_config.py` for production server settings.

## Environment-Specific Configuration

### Development

```env
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
```

### Production

```env
DEBUG=False
ALLOWED_HOSTS=mycyclingcity.net
SECRET_KEY=<strong-secret-key>
```

## Configuration Files

- `.env` - Environment variables (not in version control)
- `config/settings.py` - Django settings
- `gunicorn_config.py` - Gunicorn server configuration
- `mkdocs.yml` - Documentation configuration

## Validation

Check configuration:

```bash
python manage.py check --deploy
```

## Next Steps

- [Installation Guide](installation.md) - Return to installation
- [Admin GUI Manual](../admin/index.md) - Configure via admin interface

For production deployment, see the `DEPLOYMENT.md` file in the project root.
