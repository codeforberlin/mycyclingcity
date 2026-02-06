# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    settings.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
import os
import sys
from pathlib import Path
from django.utils.translation import gettext_lazy as _
from decouple import config, Csv

# Basis-Verzeichnisse
# CODE_DIR zeigt auf das aktuelle Verzeichnis (über Symlink auf aktuelle Version)
CODE_DIR = Path(__file__).resolve().parent.parent

# BASE_DIR bleibt für relative Pfade im Code
BASE_DIR = CODE_DIR

# Prüfe ob wir in Produktion sind (Pfad enthält /data/appl/mcc)
# Oder über Umgebungsvariable
if os.environ.get('MCC_ENV') == 'production' or '/data/appl/mcc' in str(CODE_DIR):
    DATA_DIR = Path('/data/var/mcc')                   # Daten-Verzeichnis
    APP_DIR = Path('/data/appl/mcc')                    # App-Verzeichnis (für .env und venv)
else:
    # Entwicklung: relative Pfade oder lokale Verzeichnisse
    DATA_DIR = BASE_DIR / 'data'  # Fallback zu altem Verhalten
    APP_DIR = BASE_DIR  # .env im Projektverzeichnis

# .env Datei explizit aus /data/appl/mcc/.env laden
ENV_FILE = APP_DIR / '.env'
if not ENV_FILE.exists():
    # Fallback für Entwicklung: Suche .env im Projektverzeichnis
    ENV_FILE = BASE_DIR / '.env'

# Lade .env Datei manuell in os.environ (vor allen config()-Aufrufen)
if ENV_FILE.exists():
    with open(ENV_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                # Entferne Anführungszeichen falls vorhanden
                value = value.strip('"\'')
                os.environ[key.strip()] = value.strip()

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('SECRET_KEY', default='django-insecure-YOUR_SECRET_KEY_HERE')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config('DEBUG', default=True, cast=bool)

ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='mycyclingcity.net,127.0.0.1', cast=Csv())
##ALLOWED_HOSTS = ['*']

# Add HTTPS origin of external domain
CSRF_TRUSTED_ORIGINS = config(
    'CSRF_TRUSTED_ORIGINS',
    default='https://mycyclingcity.net',
    cast=Csv()
)

# 2. SSL/HTTPS-Proxy-Header (CRITICAL for security)
# This tells Django to trust the 'X-Forwarded-Proto' header,
# which you set in your Apache configuration.
# This header is needed because your application runs on port 8001 (HTTP),
# but the client connects via port 443 (HTTPS).
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# 3. CSRF-Cookies and Sessions (Optional, but recommended for SSL proxies)
# Ensures that the session cookie is only sent over HTTPS
# In development (DEBUG=True) these should be False, in production True
# If not explicitly set, automatically decided based on DEBUG
SESSION_COOKIE_SECURE = config('SESSION_COOKIE_SECURE', default=not DEBUG, cast=bool)
CSRF_COOKIE_SECURE = config('CSRF_COOKIE_SECURE', default=not DEBUG, cast=bool)



# Application definition

INSTALLED_APPS = [
    # Built-in Django applications
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Local applications
    'api',
    'kiosk',
    'iot',
    'eventboard',  # Must be before mgmt so Event models are available when mgmt/admin.py imports them
    'mgmt',
    'minecraft',
    'game',
    'map',
    'ranking',
    'leaderboard',
]

ASGI_APPLICATION = 'config.asgi.application'
try:
    import channels  # noqa: F401
    if 'channels' not in INSTALLED_APPS:
        INSTALLED_APPS.append('channels')
except Exception:
    pass

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    
    # Timezone middleware for admin interface (after SessionMiddleware to access cookies)
    'config.middleware.TimezoneMiddleware',
    
    # IMPORTANT for i18n/L10n
    'django.middleware.locale.LocaleMiddleware',
    
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    
    # Maintenance mode middleware (after AuthenticationMiddleware to check user.is_superuser)
    'mgmt.middleware_maintenance.MaintenanceModeMiddleware',
    
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    
    # Ensure LoggingConfig background thread is running in each worker
    'mgmt.middleware_logging_config.LoggingConfigMiddleware',
    
    # Request logging for performance analysis
    'mgmt.middleware_request_logging.RequestLoggingMiddleware',
]

ROOT_URLCONF = 'config.urls'  # Or your main URL configuration path

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [CODE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.i18n',
                'config.context_processors.languages',
                'config.context_processors.kiosk_update_intervals',
                'config.context_processors.project_version',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.0/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': DATA_DIR / 'db' / 'db.sqlite3',
        'OPTIONS': {
            'timeout': 30,  # Increase timeout to 30 seconds for high concurrency
        },
    }
}

# SQLite-specific optimizations for high concurrency
# These are applied via database connection signals
def configure_sqlite_connection(sender, connection, **kwargs):
    """Configure SQLite connection for better concurrency with retry mechanism."""
    if connection.vendor == 'sqlite':
        import time
        from django.db.utils import OperationalError
        
        # Retry mechanism for PRAGMA commands
        max_retries = 5
        base_delay = 0.01
        
        for attempt in range(max_retries):
            try:
                with connection.cursor() as cursor:
                    # Enable WAL mode (Write-Ahead Logging) for better concurrency
                    # WAL mode allows multiple readers and one writer simultaneously
                    cursor.execute("PRAGMA journal_mode=WAL;")
                    # Set busy timeout to 30 seconds (30000 milliseconds)
                    cursor.execute("PRAGMA busy_timeout=30000;")
                    # Optimize for concurrent reads (NORMAL is faster than FULL, still safe)
                    cursor.execute("PRAGMA synchronous=NORMAL;")
                    # Increase cache size for better performance (64MB)
                    cursor.execute("PRAGMA cache_size=-64000;")
                    # Set page size for better performance (if not already set)
                    try:
                        cursor.execute("PRAGMA page_size=4096;")
                    except:
                        pass  # Page size can only be set when database is empty
                # Success, break out of retry loop
                break
            except OperationalError as e:
                error_str = str(e).lower()
                if 'database is locked' in error_str or 'locked' in error_str:
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        time.sleep(delay)
                        continue
                    else:
                        # Log but don't fail - connection will still work, just not optimized
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.warning(
                            f"[configure_sqlite_connection] Could not configure SQLite PRAGMA settings "
                            f"after {max_retries} attempts. Connection will still work but may be slower."
                        )
                        break
                else:
                    # Not a lock error, re-raise
                    raise
            except Exception as e:
                # Other errors, log but don't fail
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(
                    f"[configure_sqlite_connection] Error configuring SQLite: {e}. "
                    f"Connection will still work."
                )
                break

# Connect the signal
from django.db.backends.signals import connection_created
connection_created.connect(configure_sqlite_connection)


# Cache configuration
# Use local memory cache for development (fast, but not shared across processes)
# For production with multiple Gunicorn workers, consider using Redis or Memcached
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'leaderboard-cache',
        'OPTIONS': {
            'MAX_ENTRIES': 1000,
        }
    }
}


# Password validation
# https://docs.djangoproject.com/en/5.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization (i18n) and Localization (l10n)
# https://docs.djangoproject.com/en/5.0/topics/i18n/

LANGUAGE_CODE = 'de'  # Fallback language (default: German)

TIME_ZONE = 'Europe/Berlin'
USE_I18N = True
USE_TZ = True

# Defines the supported languages (German and English)
LANGUAGES = [
    ('en', _('English')),
    ('de', _('Deutsch')),
]

# IMPORTANT: Defines where Django looks for translation files
# Both .po (source) and .mo (compiled) files are in the same directory
LOCALE_PATHS = [
    CODE_DIR / 'locale',  # Quell-Übersetzungen (.po) und kompilierte Übersetzungen (.mo)
]


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.0/ref/settings/#static-files

STATIC_URL = 'static/'

# STATIC_ROOT MUST BE AN ABSOLUTE PATH!
STATIC_ROOT = DATA_DIR / 'staticfiles'  # Für Apache

STATICFILES_DIRS = [
    CODE_DIR / 'project_static',  # Quell-Verzeichnis bleibt im Code
]


MEDIA_URL = '/media/'
MEDIA_ROOT = DATA_DIR / 'media'


# Default primary key field type
# https://docs.djangoproject.com/en/5.0/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# MCC CUSTOM SETTINGS
# Timeout for inactivity in minutes (devices go to sleep mode after 5 min)
MCC_SESSION_TIMEOUT_MINUTES = 5

# Version handling - read from version.txt or fallback to git describe
def get_project_version() -> str:
    """
    Get project version from version.txt file or fallback to git describe.
    
    Returns:
        Version string (e.g., "1.0.0" or "v1.0.0-5-gabc1234").
    """
    # Look for version.txt in repository root (parent of mcc-web/)
    repo_root = BASE_DIR.parent
    version_file = repo_root / 'version.txt'
    # Fallback to mcc-web/version.txt for backwards compatibility
    if not version_file.exists():
        version_file = BASE_DIR / 'version.txt'
    if version_file.exists():
        try:
            with open(version_file, 'r', encoding='utf-8') as f:
                version = f.read().strip()
                if version:
                    return version
        except Exception:
            pass
    
    # Fallback to git describe
    import subprocess
    try:
        result = subprocess.run(
            ['git', 'describe', '--tags', '--always', '--dirty'],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    
    return 'dev'

PROJECT_VERSION = get_project_version()

# Kiosk Leaderboard Update Intervals (in seconds)
# These control how often HTMX updates the different components
# Synchronized update intervals - all components update together after cronjob (runs every 60 seconds)
# This ensures Record-Chips, Group-Chips, and Banner-Groups show consistent data from HourlyMetric
MCC_KIOSK_TICKER_UPDATE_INTERVAL = config('MCC_KIOSK_TICKER_UPDATE_INTERVAL', default=60, cast=int)  # Ticker updates every 60 seconds (synchronized with cronjob)
MCC_KIOSK_BANNER_UPDATE_INTERVAL = config('MCC_KIOSK_BANNER_UPDATE_INTERVAL', default=60, cast=int)  # Banner updates every 60 seconds (synchronized with cronjob)
MCC_KIOSK_CONTENT_UPDATE_INTERVAL = config('MCC_KIOSK_CONTENT_UPDATE_INTERVAL', default=60, cast=int)  # Content (tiles) updates every 60 seconds (synchronized with cronjob)
MCC_KIOSK_FOOTER_UPDATE_INTERVAL = config('MCC_KIOSK_FOOTER_UPDATE_INTERVAL', default=60, cast=int)  # Footer updates every 60 seconds (synchronized with cronjob)

MCC_MINECRAFT_RCON_HOST = config('MCC_MINECRAFT_RCON_HOST', default='127.0.0.1')
MCC_MINECRAFT_RCON_PORT = config('MCC_MINECRAFT_RCON_PORT', default=25575, cast=int)
MCC_MINECRAFT_RCON_PASSWORD = config('MCC_MINECRAFT_RCON_PASSWORD', default='SECRET')
MCC_MINECRAFT_SCOREBOARD_COINS_TOTAL = config('MCC_MINECRAFT_SCOREBOARD_COINS_TOTAL', default='player_coins_total')
MCC_MINECRAFT_SCOREBOARD_COINS_SPENDABLE = config('MCC_MINECRAFT_SCOREBOARD_COINS_SPENDABLE', default='player_coins_spendable')
MCC_MINECRAFT_WORKER_POLL_INTERVAL = config('MCC_MINECRAFT_WORKER_POLL_INTERVAL', default=1, cast=int)  # Deprecated: Only used as fallback
MCC_MINECRAFT_WORKER_FALLBACK_POLL_INTERVAL = config('MCC_MINECRAFT_WORKER_FALLBACK_POLL_INTERVAL', default=30, cast=int)  # Fallback polling interval (seconds)
MCC_MINECRAFT_WORKER_SOCKET_TIMEOUT = config('MCC_MINECRAFT_WORKER_SOCKET_TIMEOUT', default=5.0, cast=float)  # Socket wait timeout (seconds)
MCC_MINECRAFT_RCON_HEALTH_INTERVAL = config('MCC_MINECRAFT_RCON_HEALTH_INTERVAL', default=30, cast=int)
MCC_MINECRAFT_SNAPSHOT_INTERVAL = config('MCC_MINECRAFT_SNAPSHOT_INTERVAL', default=60, cast=int)
MCC_MINECRAFT_SNAPSHOT_UPDATE_DB_SPENDABLE = config('MCC_MINECRAFT_SNAPSHOT_UPDATE_DB_SPENDABLE', default=True, cast=bool)
MCC_MINECRAFT_OUTBOX_DONE_TTL_DAYS = config('MCC_MINECRAFT_OUTBOX_DONE_TTL_DAYS', default=7, cast=int)
MCC_MINECRAFT_OUTBOX_FAILED_TTL_DAYS = config('MCC_MINECRAFT_OUTBOX_FAILED_TTL_DAYS', default=30, cast=int)
MCC_MINECRAFT_OUTBOX_MAX_EVENTS = config('MCC_MINECRAFT_OUTBOX_MAX_EVENTS', default=50000, cast=int)
MCC_MINECRAFT_WS_ENABLED = config('MCC_MINECRAFT_WS_ENABLED', default=False, cast=bool)
MCC_MINECRAFT_WS_SHARED_SECRET = config('MCC_MINECRAFT_WS_SHARED_SECRET', default='SECRET')
MCC_MINECRAFT_WS_ALLOWED_SERVER_IDS = config('MCC_MINECRAFT_WS_ALLOWED_SERVER_IDS', default='', cast=Csv())
DEFAULT_COIN_CONVERSION_FACTOR = config('DEFAULT_COIN_CONVERSION_FACTOR', default=100, cast=int)
MCC_APP_API_KEY = config('MCC_APP_API_KEY', default='MCC-APP-API-KEY-SECRET')
# Must point to the location where the file actually exists (e.g., static/game/sound/)
MCC_GAME_SOUND = BASE_DIR / 'game' / 'static' / 'game' / 'sound' / 'bonus-sound-with-bell.mp3'
MCC_LOGO_LEFT = 'game/images/MCC-Button-v3-300x300.png'
MCC_LOGO_RIGHT = 'game/images/MCC-Button-v2-300x300.png'
MCC_WINNER_PHOTO = 'game/images/MCC-Button-v3-300x300.png'

# Ensure logs directory exists
LOGS_DIR = DATA_DIR / 'logs'
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Health Check API Configuration
# API keys for external monitoring systems (Nagios, etc.)
# Can be a single key or comma-separated list
# Set in .env file: HEALTH_CHECK_API_KEYS=key1,key2,key3
# Or as single key: HEALTH_CHECK_API_KEYS=your-secret-api-key
HEALTH_CHECK_API_KEYS = config('HEALTH_CHECK_API_KEYS', default='', cast=Csv())

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            # The format you will see in the log
            'format': '[{levelname}] {asctime} {name}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        # App-specific file handlers - each app writes to its own log file
        'api_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(LOGS_DIR / 'api.log'),
            'maxBytes': 50 * 1024 * 1024,  # 50 MB
            'backupCount': 10,
            'formatter': 'verbose',
            'level': 'DEBUG',  # Handler level is DEBUG to receive all logs that pass logger level
        },
        'mgmt_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(LOGS_DIR / 'mgmt.log'),
            'maxBytes': 50 * 1024 * 1024,  # 50 MB
            'backupCount': 10,
            'formatter': 'verbose',
            'level': 'DEBUG',  # Handler level is DEBUG to receive all logs that pass logger level
        },
        'iot_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(LOGS_DIR / 'iot.log'),
            'maxBytes': 50 * 1024 * 1024,  # 50 MB
            'backupCount': 10,
            'formatter': 'verbose',
            'level': 'DEBUG',  # Handler level is DEBUG to receive all logs that pass logger level
        },
        'kiosk_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(LOGS_DIR / 'kiosk.log'),
            'maxBytes': 50 * 1024 * 1024,  # 50 MB
            'backupCount': 10,
            'formatter': 'verbose',
            'level': 'DEBUG',  # Handler level is DEBUG to receive all logs that pass logger level
        },
        'minecraft_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(LOGS_DIR / 'minecraft.log'),
            'maxBytes': 50 * 1024 * 1024,  # 50 MB
            'backupCount': 10,
            'formatter': 'verbose',
            'level': 'DEBUG',
        },
        'game_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(LOGS_DIR / 'game.log'),
            'maxBytes': 50 * 1024 * 1024,  # 50 MB
            'backupCount': 10,
            'formatter': 'verbose',
            'level': 'DEBUG',  # Handler level is DEBUG to receive all logs that pass logger level
        },
        'map_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(LOGS_DIR / 'map.log'),
            'maxBytes': 50 * 1024 * 1024,  # 50 MB
            'backupCount': 10,
            'formatter': 'verbose',
            'level': 'DEBUG',  # Handler level is DEBUG to receive all logs that pass logger level
        },
        'leaderboard_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(LOGS_DIR / 'leaderboard.log'),
            'maxBytes': 50 * 1024 * 1024,  # 50 MB
            'backupCount': 10,
            'formatter': 'verbose',
            'level': 'DEBUG',  # Handler level is DEBUG to receive all logs that pass logger level
        },
        # Django framework logs (only WARNING and above)
        'django_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(LOGS_DIR / 'django.log'),
            'maxBytes': 10 * 1024 * 1024,  # 10 MB
            'backupCount': 5,
            'formatter': 'verbose',
            'level': 'WARNING',
        },
    },
    'root': {
        # Root logger only handles Django framework logs and critical errors
        # NOT application logs - they go to their own files
        'handlers': ['django_file'],
        'level': 'WARNING',  # Only WARNING and above reach root logger (not DEBUG/INFO)
    },
    'loggers': {
        # Django framework logger - only WARNING and above
        'django': {
            'handlers': ['django_file'],
            'level': 'WARNING',
            'propagate': False,  # Don't propagate to root - handled separately
        },
        # API application logger - writes to api.log
        'api': {
            'handlers': ['api_file'],
            'level': 'INFO',  # Log INFO and above
            'propagate': False,  # CRITICAL: Don't propagate to root - prevents Gunicorn output
        },
        # Management application logger - writes to mgmt.log
        'mgmt': {
            'handlers': ['mgmt_file'],
            'level': 'INFO',  # Log INFO and above
            'propagate': False,  # CRITICAL: Don't propagate to root - prevents Gunicorn output
        },
        # Config application logger (includes middleware) - writes to mgmt.log
        'config': {
            'handlers': ['mgmt_file'],
            'level': 'DEBUG',  # Log DEBUG and above (for middleware debugging)
            'propagate': False,  # CRITICAL: Don't propagate to root - prevents Gunicorn output
        },
        # IoT application logger - writes to iot.log
        'iot': {
            'handlers': ['iot_file'],
            'level': 'INFO',  # Log INFO and above
            'propagate': False,  # CRITICAL: Don't propagate to root - prevents Gunicorn output
        },
        # Kiosk application logger - writes to kiosk.log
        'kiosk': {
            'handlers': ['kiosk_file'],
            'level': 'INFO',  # Log INFO and above
            'propagate': False,  # CRITICAL: Don't propagate to root - prevents Gunicorn output
        },
        'minecraft': {
            'handlers': ['minecraft_file'],
            'level': 'INFO',
            'propagate': False,
        },
        # Game application logger - writes to game.log
        'game': {
            'handlers': ['game_file'],
            'level': 'INFO',  # Log INFO and above
            'propagate': False,  # CRITICAL: Don't propagate to root - prevents Gunicorn output
        },
        # Map application logger - writes to map.log
        'map': {
            'handlers': ['map_file'],
            'level': 'INFO',  # Log INFO and above
            'propagate': False,  # CRITICAL: Don't propagate to root - prevents Gunicorn output
        },
        # Leaderboard application logger - writes to leaderboard.log
        'leaderboard': {
            'handlers': ['leaderboard_file'],
            'level': 'INFO',  # Log INFO and above
            'propagate': False,  # CRITICAL: Don't propagate to root - prevents Gunicorn output
        },
    }
}
