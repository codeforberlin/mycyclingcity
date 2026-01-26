# Configuration Guide

This guide explains how to configure the MyCyclingCity application.

## Environment Variables

Configuration is managed through environment variables, typically stored in a `.env` file.

**Important:**
- **Production**: The `.env` file is located outside the software in `/data/appl/mcc/.env`
- **Development**: The `.env` file can be in the project directory (`mcc-web/.env`) or individually configured
- The application automatically finds the `.env` file by searching relative to the project directory

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

### SQLite (Default - Development and Production)

The application uses SQLite for all environments. No additional configuration needed.

**Production:**
- Database file: `/data/var/mcc/db/db.sqlite3`
- The database is automatically created if it doesn't exist

**Development:**
- Database file: `data/db.sqlite3` (relative to project directory)
- The application automatically finds the database in the project directory

## Static and Media Files

### STATIC_ROOT

Directory where static files are collected:

**Production:**
```env
STATIC_ROOT=/data/appl/mcc/mcc-web/staticfiles
```

**Development:**
- Can be individually configured (e.g., `mcc-web/staticfiles`)
- The application uses relative paths in the project directory

### MEDIA_ROOT

Directory for user-uploaded files:

**Production:**
```env
MEDIA_ROOT=/data/appl/mcc/mcc-web/media
```

**Development:**
- Can be individually configured (e.g., `mcc-web/media`)
- The application uses relative paths in the project directory

**Note:** In development environments, paths can be individual, as the application finds all information relative to the project directory.

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

See `config/gunicorn_config.py` for production server settings.
The application is started via the script `scripts/mcc-web.sh` by the user configured by the administrator (e.g., `mcc`, `www-data`, etc.). The user `mcc` is not mandatory.

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
  - **Production**: `/data/appl/mcc/.env` (outside the software)
  - **Development**: `mcc-web/.env` or individually configured
- `config/settings.py` - Django settings
- `config/gunicorn_config.py` - Gunicorn server configuration
- `mkdocs.yml` - Documentation configuration

## Validation

Check configuration:

```bash
python manage.py check --deploy
```

## Next Steps

- [Installation Guide](installation.md) - Return to installation
- [Admin GUI Manual](../admin/index.md) - Configure via admin interface

For production deployment, see the `DEPLOYMENT.md` file in this directory.
