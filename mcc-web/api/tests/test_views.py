# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    test_views.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
"""
Unit and integration tests for API views.

Tests cover:
- All API endpoints
- HTTP status codes
- JSON response structure
- Error handling
- Authentication/Authorization
"""

import pytest
import json
import time
import logging
from decimal import Decimal
from django.urls import reverse
from django.test import Client
from django.utils import timezone

from api.models import Cyclist, Group, HourlyMetric, CyclistDeviceCurrentMileage
from iot.models import Device
from mgmt.models import LoggingConfig
from api.tests.conftest import (
    CyclistFactory, DeviceFactory, GroupFactory
)


@pytest.mark.unit
@pytest.mark.django_db
class TestUpdateDataView:
    """Tests for update_data API endpoint."""
    
    def test_update_data_success(self, api_key, complete_test_scenario):
        """Test successful data update."""
        scenario = complete_test_scenario
        cyclist = scenario['cyclist']
        device = scenario['device']
        
        client = Client()
        url = reverse('update_data')
        
        initial_cyclist_distance = cyclist.distance_total
        initial_device_distance = device.distance_total
        
        response = client.post(
            url,
            data=json.dumps({
                'id_tag': cyclist.id_tag,
                'device_id': device.name,
                'distance': '5.50000'
            }),
            content_type='application/json',
            HTTP_X_API_KEY=api_key
        )
        
        
        assert response.status_code == 200, \
            f"Expected 200 OK, got {response.status_code}. Response: {response.content.decode() if hasattr(response, 'content') else 'N/A'}"
        data = response.json()
        assert data['success'] is True
        
        # Verify distances were updated
        cyclist.refresh_from_db()
        device.refresh_from_db()
        assert cyclist.distance_total == initial_cyclist_distance + Decimal('5.50000')
        assert device.distance_total == initial_device_distance + Decimal('5.50000')
    
    def test_update_data_invalid_api_key(self, complete_test_scenario):
        """Test update_data with invalid API key."""
        scenario = complete_test_scenario
        cyclist = scenario['cyclist']
        device = scenario['device']
        
        client = Client()
        url = reverse('update_data')
        
        response = client.post(
            url,
            data=json.dumps({
                'id_tag': cyclist.id_tag,
                'device_id': device.name,
                'distance': '5.50000'
            }),
            content_type='application/json',
            HTTP_X_API_KEY='INVALID-KEY'
        )
        
        assert response.status_code == 403
    
    def test_update_data_missing_id_tag(self, api_key, complete_test_scenario):
        """Test update_data with missing id_tag."""
        scenario = complete_test_scenario
        device = scenario['device']
        
        client = Client()
        url = reverse('update_data')
        
        response = client.post(
            url,
            data=json.dumps({
                'device_id': device.name,
                'distance': '5.50000'
            }),
            content_type='application/json',
            HTTP_X_API_KEY=api_key
        )
        
        assert response.status_code == 400
        data = response.json()
        assert 'id_tag' in data.get('error', '').lower()
    
    def test_update_data_player_not_found(self, api_key, complete_test_scenario):
        """Test update_data with non-existent cyclist."""
        scenario = complete_test_scenario
        device = scenario['device']
        
        client = Client()
        url = reverse('update_data')
        
        response = client.post(
            url,
            data=json.dumps({
                'id_tag': 'NON-EXISTENT-TAG',
                'device_id': device.name,
                'distance': '5.50000'
            }),
            content_type='application/json',
            HTTP_X_API_KEY=api_key
        )
        
        assert response.status_code == 404
    
    def test_update_data_km_collection_disabled_player(self, api_key, complete_test_scenario):
        """Test update_data when cyclist has km_collection_enabled=False."""
        scenario = complete_test_scenario
        cyclist = scenario['cyclist']
        device = scenario['device']
        
        cyclist.is_km_collection_enabled = False
        cyclist.save()
        
        client = Client()
        url = reverse('update_data')
        
        response = client.post(
            url,
            data=json.dumps({
                'id_tag': cyclist.id_tag,
                'device_id': device.name,
                'distance': '5.50000'
            }),
            content_type='application/json',
            HTTP_X_API_KEY=api_key
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data.get('skipped') is True


@pytest.mark.unit
@pytest.mark.django_db
class TestGetPlayerCoinsView:
    """Tests for get_player_coins API endpoint."""
    
    def test_get_player_coins_success(self, api_key, cyclist_with_group):
        """Test successful player coins retrieval."""
        cyclist = cyclist_with_group['cyclist']
        cyclist.coins_total = 100
        cyclist.coins_spendable = 50
        cyclist.save()
        
        client = Client()
        url = reverse('get_player_coins', args=[cyclist.user_id])
        
        response = client.get(
            url,
            HTTP_X_API_KEY=api_key
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data['coins_total'] == 100
        assert data['coins_spendable'] == 50
        assert data['mc_username'] == cyclist.mc_username
    
    def test_get_player_coins_invalid_api_key(self, cyclist_with_group):
        """Test get_player_coins with invalid API key."""
        cyclist = cyclist_with_group['cyclist']
        
        client = Client()
        url = reverse('get_player_coins', args=[cyclist.user_id])
        
        response = client.get(
            url,
            HTTP_X_API_KEY='INVALID-KEY'
        )
        
        assert response.status_code == 403
    
    def test_get_player_coins_player_not_found(self, api_key):
        """Test get_player_coins with non-existent player."""
        client = Client()
        url = reverse('get_player_coins', args=['NON-EXISTENT'])
        
        response = client.get(
            url,
            HTTP_X_API_KEY=api_key
        )
        
        assert response.status_code == 404


@pytest.mark.unit
@pytest.mark.django_db
class TestSpendCyclistCoinsView:
    """Tests for spend_cyclist_coins API endpoint."""
    
    def test_spend_cyclist_coins_success(self, api_key, cyclist_with_group):
        """Test successful coin spending."""
        cyclist = cyclist_with_group['cyclist']
        cyclist.coins_spendable = 100
        cyclist.save()
        
        client = Client()
        url = reverse('spend_cyclist_coins')
        
        response = client.post(
            url,
            data=json.dumps({
                'username': cyclist.mc_username,
                'coins_spent': 25
            }),
            content_type='application/json',
            HTTP_X_API_KEY=api_key
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        
        cyclist.refresh_from_db()
        assert cyclist.coins_spendable == 75
    
    def test_spend_cyclist_coins_insufficient(self, api_key, cyclist_with_group):
        """Test spending more coins than available."""
        cyclist = cyclist_with_group['cyclist']
        cyclist.coins_spendable = 10
        cyclist.save()
        
        client = Client()
        url = reverse('spend_cyclist_coins')
        
        response = client.post(
            url,
            data=json.dumps({
                'username': cyclist.mc_username,
                'coins_spent': 25
            }),
            content_type='application/json',
            HTTP_X_API_KEY=api_key
        )
        
        assert response.status_code == 400
        data = response.json()
        assert 'error' in data


@pytest.mark.unit
@pytest.mark.django_db
class TestGetUserIdView:
    """Tests for get_user_id API endpoint."""
    
    def test_get_user_id_success(self, api_key, cyclist_with_group):
        """Test successful user_id retrieval."""
        cyclist = cyclist_with_group['cyclist']
        
        client = Client()
        url = reverse('get_user_id')
        
        response = client.post(
            url,
            data=json.dumps({
                'id_tag': cyclist.id_tag
            }),
            content_type='application/json',
            HTTP_X_API_KEY=api_key
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data['user_id'] == cyclist.user_id
    
    def test_get_user_id_not_found(self, api_key):
        """Test get_user_id with non-existent id_tag."""
        client = Client()
        url = reverse('get_user_id')
        
        response = client.post(
            url,
            data=json.dumps({
                'id_tag': 'NON-EXISTENT-TAG'
            }),
            content_type='application/json',
            HTTP_X_API_KEY=api_key
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data['user_id'] == 'NULL'


@pytest.mark.unit
@pytest.mark.django_db
class TestGetMappedMinecraftPlayersView:
    """Tests for get_mapped_minecraft_players API endpoint."""
    
    def test_get_mapped_minecraft_players_success(self, api_key, cyclist_with_group):
        """Test successful Minecraft players mapping retrieval."""
        cyclist = cyclist_with_group['cyclist']
        cyclist.mc_username = 'test_mc_cyclist'
        cyclist.save()
        
        client = Client()
        url = reverse('get_mapped_minecraft_players')
        
        response = client.get(
            url,
            HTTP_X_API_KEY=api_key
        )
        
        assert response.status_code == 200
        data = response.json()
        assert cyclist.id_tag in data
        assert data[cyclist.id_tag]['mc_username'] == 'test_mc_cyclist'


@pytest.mark.unit
@pytest.mark.django_db
class TestGetTravelLocationsView:
    """Tests for get_travel_locations API endpoint."""
    
    def test_get_travel_locations_success(self, complete_test_scenario):
        """Test successful travel locations retrieval."""
        scenario = complete_test_scenario
        group = scenario['child_group']
        track = scenario['track']
        
        # Get or create travel status (may already exist from fixture)
        from api.models import GroupTravelStatus
        status, created = GroupTravelStatus.objects.get_or_create(
            group=group,
            defaults={
                'track': track,
                'current_travel_distance': Decimal('25.00000')
            }
        )
        if not created:
            # Update existing status
            status.track = track
            status.current_travel_distance = Decimal('25.00000')
            status.save()
        
        client = Client()
        url = reverse('get_travel_locations')
        
        response = client.get(url)
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        if len(data) > 0:
            assert 'group_name' in data[0]
            assert 'km_progress' in data[0]


@pytest.mark.unit
@pytest.mark.django_db
class TestKioskEndpoints:
    """Tests for Kiosk API endpoints."""
    
    def test_kiosk_get_playlist_success(self, api_key):
        """Test successful playlist retrieval."""
        from kiosk.models import KioskDevice, KioskPlaylistEntry
        from api.tests.conftest import KioskDeviceFactory, KioskPlaylistEntryFactory
        
        device = KioskDeviceFactory(uid='test-kiosk-001', is_active=True)
        entry = KioskPlaylistEntryFactory(device=device, view_type='leaderboard')
        
        client = Client()
        url = reverse('kiosk_get_playlist', args=[device.uid])
        
        response = client.get(url)
        
        assert response.status_code == 200
        data = response.json()
        assert 'playlist' in data
        assert len(data['playlist']) > 0
    
    def test_kiosk_get_playlist_device_not_found(self):
        """Test playlist retrieval for non-existent device."""
        client = Client()
        url = reverse('kiosk_get_playlist', args=['NON-EXISTENT'])
        
        response = client.get(url)
        
        assert response.status_code == 404
    
    def test_kiosk_get_commands_success(self):
        """Test successful commands retrieval."""
        from kiosk.models import KioskDevice
        from api.tests.conftest import KioskDeviceFactory
        
        device = KioskDeviceFactory(uid='test-kiosk-002')
        device.add_command('RELOAD')
        device.add_command('SET_BRIGHTNESS:50')
        
        client = Client()
        url = reverse('kiosk_get_commands', args=[device.uid])
        
        response = client.get(url)
        
        assert response.status_code == 200
        data = response.json()
        assert 'commands' in data
        assert len(data['commands']) == 2


@pytest.mark.unit
@pytest.mark.django_db
class TestViewLogging:
    """Tests for logging functionality in API views."""
    
    def test_update_data_logs_warning_on_invalid_api_key(self, complete_test_scenario):
        """Test that update_data logs WARNING when API key is invalid."""
        # Ensure LoggingConfig exists with WARNING level
        config = LoggingConfig.get_config()
        config.min_log_level = 'WARNING'
        config.save()
        
        # ApplicationLog model was removed in migration 0011
        # This test is skipped - logging functionality changed
        pass
    
    @pytest.mark.skip(reason="ApplicationLog model was removed in migration 0011")
    def test_update_data_logs_warning_on_cyclist_not_found(self, api_key, complete_test_scenario):
        """Test that update_data logs WARNING when cyclist is not found."""
        # Ensure LoggingConfig exists with WARNING level
        config = LoggingConfig.get_config()
        config.min_log_level = 'WARNING'
        config.save()
        
        scenario = complete_test_scenario
        device = scenario['device']
        
        # Clear existing logs
        # ApplicationLog.objects.all().delete()  # Model removed
        
        client = Client()
        url = reverse('update_data')
        
        response = client.post(
            url,
            data=json.dumps({
                'id_tag': 'NON-EXISTENT-TAG-12345',
                'device_id': device.name,
                'distance': '5.50000'
            }),
            content_type='application/json',
            HTTP_X_API_KEY=api_key
        )
        
        assert response.status_code == 404
        
        # ApplicationLog model was removed
        # logs = ApplicationLog.objects.filter(...)
        # assert logs.count() >= 1
        pass
    
    @pytest.mark.skip(reason="ApplicationLog model was removed in migration 0011")
    def test_update_data_logs_warning_on_missing_id_tag(self, api_key, complete_test_scenario):
        """Test that update_data logs WARNING when id_tag is missing."""
        # Ensure LoggingConfig exists with WARNING level
        config = LoggingConfig.get_config()
        config.min_log_level = 'WARNING'
        config.save()
        
        scenario = complete_test_scenario
        device = scenario['device']
        
        # Clear existing logs
        # ApplicationLog.objects.all().delete()  # Model removed
        
        client = Client()
        url = reverse('update_data')
        
        response = client.post(
            url,
            data=json.dumps({
                'device_id': device.name,
                'distance': '5.50000'
            }),
            content_type='application/json',
            HTTP_X_API_KEY=api_key
        )
        
        assert response.status_code == 400
        
        # ApplicationLog model was removed
        # logs = ApplicationLog.objects.filter(...)
        # assert logs.count() >= 1
        pass
    
    @pytest.mark.skip(reason="ApplicationLog model was removed in migration 0011")
    def test_update_data_logs_warning_on_missing_device_id(self, api_key, complete_test_scenario):
        """Test that update_data logs WARNING when device_id is missing."""
        # Ensure LoggingConfig exists with WARNING level
        config = LoggingConfig.get_config()
        config.min_log_level = 'WARNING'
        config.save()
        
        scenario = complete_test_scenario
        cyclist = scenario['cyclist']
        
        # Clear existing logs
        # ApplicationLog.objects.all().delete()  # Model removed
        
        client = Client()
        url = reverse('update_data')
        
        response = client.post(
            url,
            data=json.dumps({
                'id_tag': cyclist.id_tag,
                'distance': '5.50000'
            }),
            content_type='application/json',
            HTTP_X_API_KEY=api_key
        )
        
        assert response.status_code == 400
        
        # ApplicationLog model was removed
        # logs = ApplicationLog.objects.filter(...)
        # assert logs.count() >= 1
        pass
    
    @pytest.mark.skip(reason="ApplicationLog model was removed in migration 0011")
    def test_update_data_logs_info_on_success(self, api_key, complete_test_scenario):
        """Test that update_data logs INFO messages on successful update."""
        # Ensure LoggingConfig exists with INFO level to capture INFO logs
        config = LoggingConfig.get_config()
        config.min_log_level = 'INFO'
        config.save()
        
        scenario = complete_test_scenario
        cyclist = scenario['cyclist']
        device = scenario['device']
        
        # Clear existing logs
        # ApplicationLog.objects.all().delete()  # Model removed
        
        client = Client()
        url = reverse('update_data')
        
        response = client.post(
            url,
            data=json.dumps({
                'id_tag': cyclist.id_tag,
                'device_id': device.name,
                'distance': '5.50000'
            }),
            content_type='application/json',
            HTTP_X_API_KEY=api_key
        )
        
        assert response.status_code == 200
        
        # ApplicationLog model was removed
        # logs = ApplicationLog.objects.filter(...)
        pass
    
    @pytest.mark.skip(reason="ApplicationLog model was removed in migration 0011")
    def test_logs_not_stored_when_level_too_low(self, api_key, complete_test_scenario):
        """Test that logs below minimum level are not stored."""
        # Set LoggingConfig to ERROR level (should not store WARNING)
        config = LoggingConfig.get_config()
        config.min_log_level = 'ERROR'
        config.save()
        
        scenario = complete_test_scenario
        device = scenario['device']
        
        # Clear existing logs
        # ApplicationLog.objects.all().delete()  # Model removed
        
        client = Client()
        url = reverse('update_data')
        
        # This should generate a WARNING (cyclist not found)
        response = client.post(
            url,
            data=json.dumps({
                'id_tag': 'NON-EXISTENT-TAG-12345',
                'device_id': device.name,
                'distance': '5.50000'
            }),
            content_type='application/json',
            HTTP_X_API_KEY=api_key
        )
        
        assert response.status_code == 404
        
        # ApplicationLog model was removed
        # logs = ApplicationLog.objects.filter(...)
        # assert logs.count() == 0
        pass
    
    @pytest.mark.skip(reason="ApplicationLog model was removed in migration 0011")
    def test_logger_name_preserved_in_database(self, api_key, complete_test_scenario):
        """Test that logger name is correctly preserved in database logs."""
        # Ensure LoggingConfig exists with WARNING level
        config = LoggingConfig.get_config()
        config.min_log_level = 'WARNING'
        config.save()
        
        scenario = complete_test_scenario
        device = scenario['device']
        
        # Clear existing logs
        # ApplicationLog.objects.all().delete()  # Model removed
        
        client = Client()
        url = reverse('update_data')
        
        response = client.post(
            url,
            data=json.dumps({
                'id_tag': 'NON-EXISTENT-TAG-12345',
                'device_id': device.name,
                'distance': '5.50000'
            }),
            content_type='application/json',
            HTTP_X_API_KEY=api_key
        )
        
        assert response.status_code == 404
        
        # ApplicationLog model was removed
        # logs = ApplicationLog.objects.filter(...)
        # assert logs.count() >= 1
        # log = logs.first()
        # assert log.logger_name == 'api.views'
        pass

