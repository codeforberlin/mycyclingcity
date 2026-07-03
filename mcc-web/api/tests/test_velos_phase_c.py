# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

import json
import pytest
from decimal import Decimal
from django.test import Client
from django.urls import reverse

from eventboard.models import Event, GroupEventStatus
from api.tests.conftest import CyclistFactory, DeviceFactory, GroupFactory


@pytest.mark.unit
@pytest.mark.django_db
class TestEventboardVelosOnUpdate:
    def test_update_data_increases_event_velos(self, api_key):
        parent = GroupFactory(name='School')
        leaf = GroupFactory(name='Class 1a', parent=parent)
        cyclist = CyclistFactory(id_tag='event-velos-tag')
        cyclist.groups.add(leaf)
        device = DeviceFactory(name='event-velos-device', group=leaf)
        config = device.configuration
        config.wheel_size = 2300.0
        config.paedagogischer_bonus = 0.0
        config.save()

        event = Event.objects.create(
            name='Velos Event',
            top_group=parent,
            target_velos=1000,
            is_active=True,
        )
        GroupEventStatus.objects.create(group=parent, event=event, current_velos=0)

        client = Client()
        response = client.post(
            reverse('update_data'),
            data=json.dumps({
                'id_tag': cyclist.id_tag,
                'device_id': device.name,
                'distance': '1.00000',
            }),
            content_type='application/json',
            HTTP_X_API_KEY=api_key,
        )

        assert response.status_code == 200
        status = GroupEventStatus.objects.get(group=parent, event=event)
        assert status.current_velos == 100
