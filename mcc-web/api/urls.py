# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    urls.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
from django.urls import path
from . import views

urlpatterns = [
    path('update-data', views.update_data, name='update_data'),
    path('get-user-id', views.get_user_id, name='get_user_id'),
    path('get-player-coins/<str:username>', views.get_player_coins, name='get_player_coins'),
    path('get-cyclist-coins/<str:username>', views.get_cyclist_coins, name='get_cyclist_coins'),
    path('spend-cyclist-coins', views.spend_cyclist_coins, name='spend_cyclist_coins'),
    path('get-mapped-minecraft-players', views.get_mapped_minecraft_players, name='get_mapped_minecraft_players'),
    path('get-mapped-minecraft-cyclists', views.get_mapped_minecraft_cyclists, name='get_mapped_minecraft_cyclists'),
    
    # New endpoints for the map system
    path('get-travel-locations', views.get_travel_locations, name='get_travel_locations'),
    
    # Kiosk management endpoints
    path('kiosk/<str:uid>/playlist', views.kiosk_get_playlist, name='kiosk_get_playlist'),
    path('kiosk/<str:uid>/commands', views.kiosk_get_commands, name='kiosk_get_commands'),
    
    # Distance/Mileage data endpoints
    path('get-cyclist-distance/<str:identifier>', views.get_cyclist_distance, name='get_cyclist_distance'),
    path('get-group-distance/<str:identifier>', views.get_group_distance, name='get_group_distance'),
    
    # Leaderboard endpoints
    path('get-leaderboard/cyclists', views.get_leaderboard_cyclists, name='get_leaderboard_cyclists'),
    path('get-leaderboard/groups', views.get_leaderboard_groups, name='get_leaderboard_groups'),
    
    # Active cyclists endpoint
    path('get-active-cyclists', views.get_active_cyclists, name='get_active_cyclists'),
    
    # List endpoints
    path('list-cyclists', views.list_cyclists, name='list_cyclists'),
    path('list-groups', views.list_groups, name='list_groups'),
    
    # Milestones and statistics
    path('get-milestones', views.get_milestones, name='get_milestones'),
    path('get-statistics', views.get_statistics, name='get_statistics'),
    path('get-group-rewards', views.get_group_rewards, name='get_group_rewards'),
    path('redeem-milestone-reward', views.redeem_milestone_reward, name='redeem_milestone_reward'),
    
    # Device management endpoints
    path('device/config/report', views.device_config_report, name='device_config_report'),
    path('device/config/fetch', views.device_config_fetch, name='device_config_fetch'),
    path('device/firmware/download', views.device_firmware_download, name='device_firmware_download'),
    path('device/firmware/info', views.device_firmware_info, name='device_firmware_info'),
    path('device/heartbeat', views.device_heartbeat, name='device_heartbeat'),
]