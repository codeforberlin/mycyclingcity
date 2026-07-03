# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

import json
import pytest
from decimal import Decimal
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from api.models import CyclistDeviceCurrentMileage
from api.services.device_display import (
    DISPLAY_MODE_LIVE,
    DISPLAY_MODE_ROUND_FROZEN,
    build_device_display_api_payload,
    lock_device_display,
    unlock_device_display,
)
from api.tests.conftest import CyclistFactory, DeviceFactory, GroupFactory
from api.velos import calculate_session_velos, format_velos_de


@pytest.mark.unit
@pytest.mark.django_db
class TestDeviceDisplayLock:
    def test_build_payload_live_mode(self):
        group = GroupFactory()
        device = DeviceFactory(group=group)
        config = device.configuration
        config.wheel_size = 2300.0
        config.paedagogischer_bonus = 0.0
        config.save()
        cyclist = CyclistFactory(user_id='display-live-user')
        session = CyclistDeviceCurrentMileage.objects.create(
            cyclist=cyclist,
            device=device,
            cumulative_mileage=Decimal('0.25'),
            start_time=timezone.now(),
        )

        payload = build_device_display_api_payload(device, session)

        expected_velos = calculate_session_velos(session.cumulative_mileage, device)
        assert payload['display_mode'] == DISPLAY_MODE_LIVE
        assert payload['display_velos'] == expected_velos
        assert payload['display_velos_display'] == format_velos_de(expected_velos)
        assert payload['session_velos'] == expected_velos

    def test_build_payload_round_frozen(self):
        device = DeviceFactory()
        lock_device_display(device, 142)

        payload = build_device_display_api_payload(device)

        assert payload['display_mode'] == DISPLAY_MODE_ROUND_FROZEN
        assert payload['display_velos'] == 142
        assert payload['display_velos_display'] == '142'

    def test_boot_reason_unlocks_display(self, api_key):
        device = DeviceFactory()
        lock_device_display(device, 99)
        client = Client()
        response = client.post(
            reverse('device_heartbeat'),
            data=json.dumps({
                'device_id': device.name,
                'boot_reason': 'deep_sleep',
            }),
            content_type='application/json',
            HTTP_X_API_KEY=api_key,
        )
        assert response.status_code == 200
        data = response.json()
        assert data['display_mode'] == DISPLAY_MODE_LIVE
        device.configuration.refresh_from_db()
        assert device.configuration.display_velos_locked is False

    def test_update_data_round_frozen_while_session_grows(self, api_key, complete_test_scenario):
        cyclist = complete_test_scenario['cyclist']
        device = complete_test_scenario['device']
        lock_device_display(device, 50)
        client = Client()
        response = client.post(
            reverse('update_data'),
            data=json.dumps({
                'id_tag': cyclist.id_tag,
                'device_id': device.name,
                'distance': '0.5',
            }),
            content_type='application/json',
            HTTP_X_API_KEY=api_key,
        )
        assert response.status_code == 200
        data = response.json()
        assert data['display_mode'] == DISPLAY_MODE_ROUND_FROZEN
        assert data['display_velos'] == 50
        session = CyclistDeviceCurrentMileage.objects.get(cyclist=cyclist)
        live_velos = calculate_session_velos(session.cumulative_mileage, device)
        assert data['session_velos'] == live_velos
        assert live_velos != 50

    def test_update_data_returns_display_fields(self, api_key, complete_test_scenario):
        cyclist = complete_test_scenario['cyclist']
        device = complete_test_scenario['device']
        client = Client()
        response = client.post(
            reverse('update_data'),
            data=json.dumps({
                'id_tag': cyclist.id_tag,
                'device_id': device.name,
                'distance': '0.1',
            }),
            content_type='application/json',
            HTTP_X_API_KEY=api_key,
        )
        assert response.status_code == 200
        data = response.json()
        assert 'display_mode' in data
        assert 'display_velos' in data
        assert 'display_velos_display' in data

    def test_unlock_helper(self):
        device = DeviceFactory()
        lock_device_display(device, 10)
        assert unlock_device_display(device, reason='test') is True
        device.configuration.refresh_from_db()
        assert device.configuration.display_velos_locked is False
