"""
Project: MyCyclingCity
Generation: AI-based

Leaderboard application for MyCyclingCity.
Handles animated high-score tiles and leaderboard displays.
"""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class LeaderboardConfig(AppConfig):
    """Configuration for the leaderboard app."""
    
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'leaderboard'
    verbose_name = _('Leaderboard')
