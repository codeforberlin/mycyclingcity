# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    urls.py
# @author  Roland Rutz

#
"""
Project: MyCyclingCity
Generation: AI-based

URL configuration for ranking app.
"""

from django.urls import path
from . import views

app_name = 'ranking'

urlpatterns = [
    path('', views.ranking_page, name='ranking_page'),
    path('kiosk/', views.ranking_page, {'kiosk': True}, name='ranking_kiosk'),
]


