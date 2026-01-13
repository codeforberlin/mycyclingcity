# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    apps.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
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
