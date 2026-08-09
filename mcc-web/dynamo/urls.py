# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    urls.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

"""URL configuration for dynamo app."""

from django.urls import path

from . import views

app_name = 'dynamo'

urlpatterns = [
    path('', views.dynamo_page, name='dynamo_page'),
    path('api/live/', views.dynamo_live_api, name='dynamo_live_api'),
    path('partials/history/', views.dynamo_history_partial, name='dynamo_history_partial'),
]
