# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    admin_session_init.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
"""
This module ensures that the GameSessionAdmin is registered when Django starts.
Import this in the game app's __init__.py or apps.py to register the admin.
"""

# Import to trigger registration
from .session_admin import GameSessionAdmin  # noqa: F401
