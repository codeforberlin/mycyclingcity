"""
Project: MyCyclingCity
Generation: AI-based

Ranking application for MyCyclingCity.
Handles ranking tables and statistical lists.
"""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class RankingConfig(AppConfig):
    """Configuration for the ranking app."""
    
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ranking'
    verbose_name = _('Ranking')
