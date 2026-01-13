# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    urls.py
# @author  Roland Rutz

#
"""
Project: MyCyclingCity
Generation: AI-based

URL configuration for map app - OSM/Leaflet map only.
"""

from django.urls import path
from . import views

app_name = 'map'

urlpatterns = [
    path('', views.map_page, name='map_page'),
    path('ticker/', views.map_ticker, name='map_ticker'),
    # Map API endpoints
    path('api/group-avatars/', views.get_group_avatars, name='get_group_avatars'),
    path('api/new-milestones/', views.get_new_milestones, name='get_new_milestones'),
    path('api/all-milestones-status/', views.get_all_milestones_status, name='get_all_milestones_status'),
]