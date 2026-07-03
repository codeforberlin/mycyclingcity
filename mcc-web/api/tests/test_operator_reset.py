# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for operator RFID tag reset via get_user_id."""

import json
import pytest
from decimal import Decimal
from django.urls import reverse
from django.test import Client

from api.models import Cyclist, CyclistDeviceCurrentMileage
from api.tests.conftest import CyclistFactory, DeviceFactory, GroupFactory
from iot.models import DeviceConfiguration


@pytest.mark.unit
@pytest.mark.django_db
class TestOperatorReset:
    def test_operator_resets_guest_to_default(self, api_key, db):
        group = GroupFactory()
        default = CyclistFactory(user_id='Kette', id_tag='default-tag')
        guest = CyclistFactory(user_id='Gast', id_tag='guest-tag')
        operator = CyclistFactory(user_id='Op', id_tag='op-tag', is_operator_tag=True)
        device = DeviceFactory(name='Counter-1', group=group)
        DeviceConfiguration.objects.filter(device=device).update(default_id_tag=default.id_tag)

        CyclistDeviceCurrentMileage.objects.create(
            cyclist=guest,
            device=device,
            cumulative_mileage=Decimal('1.00000'),
        )

        client = Client()
        response = client.post(
            reverse('get_user_id'),
            data=json.dumps({
                'id_tag': operator.id_tag,
                'device_id': device.name,
                'current_id_tag': guest.id_tag,
            }),
            content_type='application/json',
            HTTP_X_API_KEY=api_key,
        )

        assert response.status_code == 200
        data = response.json()
        assert data['is_operator_tag'] is True
        assert data['action'] == 'reset_to_default'
        assert data['default_id_tag'] == default.id_tag
        assert data['default_user_id'] == 'Kette'
        assert not CyclistDeviceCurrentMileage.objects.filter(device=device).exists()

    def test_operator_noop_when_already_default(self, api_key, db):
        group = GroupFactory()
        default = CyclistFactory(user_id='Kette', id_tag='default-tag')
        operator = CyclistFactory(user_id='Op', id_tag='op-tag', is_operator_tag=True)
        device = DeviceFactory(name='Counter-2', group=group)
        DeviceConfiguration.objects.filter(device=device).update(default_id_tag=default.id_tag)

        CyclistDeviceCurrentMileage.objects.create(
            cyclist=default,
            device=device,
            cumulative_mileage=Decimal('0.10000'),
        )

        client = Client()
        response = client.post(
            reverse('get_user_id'),
            data=json.dumps({
                'id_tag': operator.id_tag,
                'device_id': device.name,
                'current_id_tag': default.id_tag,
            }),
            content_type='application/json',
            HTTP_X_API_KEY=api_key,
        )

        assert response.status_code == 200
        data = response.json()
        assert data['action'] == 'noop'
        assert CyclistDeviceCurrentMileage.objects.filter(device=device).exists()
