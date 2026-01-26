# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    urls.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
import os
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.conf.urls.i18n import i18n_patterns
from django.views.generic import RedirectView
from config import views as config_views
from config.views import set_language, privacy_policy, maintenance_page
from mgmt.health_check_api import health_check_api

# Language switcher and API endpoints must be outside i18n_patterns
urlpatterns = [
    path('i18n/setlang/', set_language, name='set_language'),
    # Health check endpoint (for monitoring/load balancers)
    path('health/', config_views.health_check, name='health_check'),
    # Health check API endpoint (for external monitoring systems with API key)
    path('api/health/', health_check_api, name='health_check_api'),
    # Maintenance page (must be outside i18n_patterns to work with middleware redirect)
    path('maintenance.html', maintenance_page, name='maintenance_page'),
    # API endpoints (no language prefix needed)
    path('api/', include('api.urls')),       # MCC-DB logic
    # cath empty path and redirect to /de/map/
    path('', RedirectView.as_view(url='/de/map/', permanent=True)),
]

# URL patterns with language prefix (e.g., /en/, /de/)
urlpatterns += i18n_patterns(
    path('admin/', admin.site.urls),  # Django Admin

    # Our consolidated apps
    path('game/', include('game.urls')),         # Kilometer challenge
    path('map/', include('map.urls')),          # Live map (OSM/Leaflet only)
    path('ranking/', include('ranking.urls')),   # Ranking tables
    path('leaderboard/', include('leaderboard.urls')),  # Leaderboard tiles
    path('kiosk/', include('kiosk.urls')),      # Kiosk device management

    # Privacy policy
    path('privacy/', privacy_policy, name='privacy_policy'),
)

# IMPORTANT CORRECTION: Only in DEBUG mode!
# These lines tell Django to serve static files through the Python process.
# Remove THESE LINES as soon as you are in actual production!
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

    # If you also need files from app directories in debug mode (which is the case for Admin)
    from django.contrib.staticfiles.urls import staticfiles_urlpatterns
    urlpatterns += staticfiles_urlpatterns()
