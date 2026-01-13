# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    urls.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
"""
Project: MyCyclingCity
Generation: AI-based

URL configuration for kiosk app.
"""

from django.urls import path
from . import views

app_name = 'kiosk'

urlpatterns = [
    path('playlist/<str:uid>/', views.kiosk_playlist_page, name='kiosk_playlist_page'),
]

