# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    urls.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
from django.urls import path
from minecraft.api_views import mcc_counter_scan
from minecraft.waitlist_views import minecraft_waitlist_public_display
from luanti.api_views import (
    luanti_arena_state,
    luanti_auth_check,
    luanti_counter_scan,
    luanti_heartbeat,
    luanti_inventory_sync,
    luanti_regions,
    luanti_session_join,
    luanti_session_leave,
    luanti_session_set_mode,
    luanti_shop_buy,
    luanti_shop_catalog,
    luanti_shop_registry,
    luanti_shop_sell,
    luanti_wallet_balance,
    luanti_wallet_withdraw,
    luanti_station_config,
)

from . import views

urlpatterns = [
    path('update-data', views.update_data, name='update_data'),
    path('get-user-id', views.get_user_id, name='get_user_id'),
    path('get-mapped-minecraft-players', views.get_mapped_minecraft_players, name='get_mapped_minecraft_players'),
    path('get-mapped-minecraft-cyclists', views.get_mapped_minecraft_cyclists, name='get_mapped_minecraft_cyclists'),
    path('mcc-counter/scan/', mcc_counter_scan, name='mcc_counter_scan'),
    path(
        'minecraft/waitlist/<str:token>/display/',
        minecraft_waitlist_public_display,
        name='minecraft_waitlist_public_display',
    ),

    # Luanti bridge
    path('luanti/heartbeat/', luanti_heartbeat, name='luanti_heartbeat'),
    path('luanti/auth/check/', luanti_auth_check, name='luanti_auth_check'),
    path('luanti/session/join/', luanti_session_join, name='luanti_session_join'),
    path('luanti/session/leave/', luanti_session_leave, name='luanti_session_leave'),
    path('luanti/session/set-mode/', luanti_session_set_mode, name='luanti_session_set_mode'),
    path('luanti/inventory/sync/', luanti_inventory_sync, name='luanti_inventory_sync'),
    path('luanti/shop/catalog/', luanti_shop_catalog, name='luanti_shop_catalog'),
    path('luanti/shop/registry/', luanti_shop_registry, name='luanti_shop_registry'),
    path('luanti/shop/buy/', luanti_shop_buy, name='luanti_shop_buy'),
    path('luanti/shop/sell/', luanti_shop_sell, name='luanti_shop_sell'),
    path('luanti/wallet/withdraw/', luanti_wallet_withdraw, name='luanti_wallet_withdraw'),
    path('luanti/wallet/balance/', luanti_wallet_balance, name='luanti_wallet_balance'),
    path('luanti/regions/', luanti_regions, name='luanti_regions'),
    path('luanti/arena/state/', luanti_arena_state, name='luanti_arena_state'),
    path('luanti/counter/scan/', luanti_counter_scan, name='luanti_counter_scan'),
    path('luanti/station/config/', luanti_station_config, name='luanti_station_config'),

    # New endpoints for the map system
    path('get-travel-locations', views.get_travel_locations, name='get_travel_locations'),
    
    # Kiosk management endpoints
    path('kiosk/<str:uid>/playlist', views.kiosk_get_playlist, name='kiosk_get_playlist'),
    path('kiosk/<str:uid>/commands', views.kiosk_get_commands, name='kiosk_get_commands'),
    
    # Distance/Mileage data endpoints
    path('get-cyclist-distance/<str:identifier>', views.get_cyclist_distance, name='get_cyclist_distance'),
    path('get-cyclist-velos/<str:identifier>', views.get_cyclist_velos, name='get_cyclist_velos'),
    path('redeem-cyclist-velos', views.redeem_cyclist_velos_api, name='redeem_cyclist_velos'),
    path('get-group-distance/<str:identifier>', views.get_group_distance, name='get_group_distance'),
    path('get-group-velos/<str:identifier>', views.get_group_velos, name='get_group_velos'),
    
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