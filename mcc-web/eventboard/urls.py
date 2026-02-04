# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    urls.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

from django.urls import path
from . import views

app_name = 'eventboard'

urlpatterns = [
    path('', views.eventboard_page, name='eventboard_page'),
    path('api/data/', views.eventboard_api, name='eventboard_api'),
    path('api/selection/', views.eventboard_selection_api, name='eventboard_selection_api'),
    path('ticker/', views.eventboard_ticker, name='eventboard_ticker'),
]
