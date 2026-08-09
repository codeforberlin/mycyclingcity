# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    apps.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

"""Dynamo energy visualization application."""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class DynamoConfig(AppConfig):
    """Configuration for the dynamo (virtual hub dynamo) app."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'dynamo'
    verbose_name = _('Dynamo')
