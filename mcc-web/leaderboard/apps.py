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
