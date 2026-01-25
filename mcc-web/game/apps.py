# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    apps.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class GameConfig(AppConfig):  # <-- This is the expected name
    default_auto_field = 'django.db.models.BigAutoField'
    
    # Standard label
    name = 'game'
    
    verbose_name = _('MCC Spiel-Interface')
    
    def ready(self):
        """Import admin modules when app is ready."""
        from django.contrib import admin
        from django.contrib.sessions.models import Session
        
        # Import signals to register them
        from . import signals  # noqa: F401
        
        # Unregister default Session admin if registered
        if admin.site.is_registered(Session):
            admin.site.unregister(Session)
        
        # Register our custom GameSessionAdmin
        from .session_admin import GameSessionAdmin
        admin.site.register(Session, GameSessionAdmin)
        
        # NOTE: We don't change app_label here anymore because it causes issues
        # during migrations when Django tries to validate models.
        # The Session model will still appear under 'game' app in admin
        # because we register it with GameSessionAdmin, but the app_label
        # remains 'sessions' to avoid migration issues.
        # Session._meta.app_label = 'game'  # Disabled to fix migration issues
        Session._meta.verbose_name = _('Spielsitzung')
        Session._meta.verbose_name_plural = _('Spielsitzungen')

