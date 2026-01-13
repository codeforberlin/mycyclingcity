# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    settings.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
import os
from pathlib import Path
from django.utils.translation import gettext_lazy as _
from decouple import config, Csv

BASE_DIR = Path(__file__).resolve().parent.parent

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
    'mgmt',
    'game',
    'map',
    'ranking',
    'leaderboard',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',

    # IMPORTANT for i18n/L10n
    'django.middleware.locale.LocaleMiddleware',

    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'  # Or your main URL configuration path

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
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
        'NAME': BASE_DIR / 'db.sqlite3',
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

TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Defines the supported languages (German and English)
LANGUAGES = [
    ('en', _('English')),
    ('de', _('Deutsch')),
]

# IMPORTANT: Defines where Django looks for translation files
LOCALE_PATHS = [
    BASE_DIR / 'locale',
]


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.0/ref/settings/#static-files

STATIC_URL = 'static/'

# STATIC_ROOT MUST BE AN ABSOLUTE PATH!
STATIC_ROOT = BASE_DIR / 'staticfiles'

STATICFILES_DIRS = [
    BASE_DIR / 'project_static',
]


MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')


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
            cwd=BASE_DIR,
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

MCC_MINECRAFT_URL = config('MCC_MINECRAFT_URL', default='http://127.0.0.1:5003/update-player-coins')
MCC_MINECRAFT_API_KEY = config('MCC_MINECRAFT_API_KEY', default='SECRET')
DEFAULT_COIN_CONVERSION_FACTOR = config('DEFAULT_COIN_CONVERSION_FACTOR', default=100, cast=int)
MCC_APP_API_KEY = config('MCC_APP_API_KEY', default='MCC-APP-API-KEY-SECRET')
# Must point to the location where the file actually exists (e.g., static/game/sound/)
MCC_GAME_SOUND = BASE_DIR / 'game' / 'static' / 'game' / 'sound' / 'bonus-sound-with-bell.mp3'
MCC_LOGO_LEFT = 'game/images/MCC-Button-v3-300x300.png'
MCC_LOGO_RIGHT = 'game/images/MCC-Button-v2-300x300.png'
MCC_WINNER_PHOTO = 'game/images/MCC-Button-v3-300x300.png'

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
        # Defines that logs are sent to the console
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',  # <-- IMPORTANT: Here you set the global minimum level
    },
    'loggers': {
        # 'django' is the built-in logger for Django internal messages
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': True,
        },
        # Configures the logger for your API app to also log DEBUG messages
        'api': {
            'handlers': ['console'],
            # Set this to 'DEBUG' to see your detailed views.py messages
            'level': 'DEBUG',
            'propagate': False,
        },
    }
}
