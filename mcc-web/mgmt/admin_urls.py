# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    admin_urls.py
# @author  Roland Rutz

#
from django.urls import path
from . import admin_views

app_name = 'mgmt'

urlpatterns = [
    path('', admin_views.bulk_create_school, name='bulk_create_school'),
    path('preview/', admin_views.bulk_create_school_preview, name='bulk_create_school_preview'),
]

