# mcc/game/apps.py

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class GameConfig(AppConfig):  # <-- This is the expected name
    # Fixes the models.W042 warning
    default_auto_field = 'django.db.models.BigAutoField'
    
    # Standard label
    name = 'game'
    
    verbose_name = _('MCC Game Interface')

