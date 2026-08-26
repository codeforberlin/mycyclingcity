# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class LuantiAppConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "luanti"
    verbose_name = _("Luanti")
