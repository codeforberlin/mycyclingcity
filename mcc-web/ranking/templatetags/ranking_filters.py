"""
Project: MyCyclingCity
Generation: AI-based

Template tags for ranking app.
Reuses format_km_de from api.utils via map_filters for now.
"""

from django import template
from map.templatetags.map_filters import format_km_de, format_km_de_tag

register = template.Library()

# Reuse format_km_de from map_filters
register.filter('format_km_de', format_km_de)
register.simple_tag(takes_context=True)(format_km_de_tag)


