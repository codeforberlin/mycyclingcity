# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    apps.py
# @author  Roland Rutz

#
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class IotConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'iot'
    verbose_name = _('IOT Management')
