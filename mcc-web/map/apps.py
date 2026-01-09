"""
Project: MyCyclingCity
Generation: AI-based

Map application configuration for MyCyclingCity.
Handles OSM/Leaflet map visualization only.
"""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class MapConfig(AppConfig):
    """
    Configuration for the map app.
    
    This app handles only OSM/Leaflet map visualization.
    Ranking and leaderboard functionality has been moved to separate apps.
    """
    
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'map'
    verbose_name = _('MCC Live Map')
