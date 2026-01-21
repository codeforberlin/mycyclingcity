# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    urls.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
from django.urls import path
from . import views

app_name = 'game'

urlpatterns = [
    path('', views.game_page, name='game_page'),
    
    # GameRoom Views
    path('room/create', views.create_room, name='create_room'),
    path('room/join', views.join_room, name='join_room'),
    path('room/<str:room_code>/', views.room_page, name='room_page'),
    path('room/<str:room_code>/qr', views.generate_qr_code, name='room_qr_code'),
    path('room/leave', views.leave_room, name='leave_room'),
    path('room/end', views.end_room, name='end_room'),
    path('room/transfer-master', views.transfer_master, name='transfer_master'),
    
    # HTMX Views
    path('htmx/assignments', views.handle_assignment_form, name='handle_assignment_form'),
    path('htmx/results', views.render_results_table, name='render_results_table'),
    path('htmx/target-km', views.render_target_km_display, name='render_target_km_display'),
    path('htmx/sync-session', views.sync_session_endpoint, name='sync_session_endpoint'),
    path('htmx/game-buttons', views.render_game_buttons, name='render_game_buttons'),
    path('htmx/filtered-cyclists', views.get_filtered_cyclists, name='get_filtered_cyclists'),
    path('htmx/subgroups', views.get_subgroups, name='get_subgroups'),
    path('htmx/filtered-devices', views.get_filtered_devices, name='get_filtered_devices'),

    # API Views
    path('api/game/cyclists', views.get_game_players, name='get_game_players'),
    path('api/game/devices', views.get_game_devices, name='get_game_devices'),
    path('api/game/start', views.start_game, name='start_game'),
    path('api/game/data', views.get_game_data, name='get_game_data'),
    path('api/session/end', views.end_session, name='end_session'), # NEU
    path('api/sound/goal_reached', views.serve_goal_sound, name='serve_goal_sound'),
    path('api/game/images', views.get_game_images, name='get_game_images'),
]