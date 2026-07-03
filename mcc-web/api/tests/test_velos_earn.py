# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

import json
import pytest
from decimal import Decimal
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from api.models import HourlyMetric
from api.services.velos_earn import apply_velos_earn
from api.services.velos_redemption import redeem_cyclist_velos
from api.tests.conftest import CyclistFactory, DeviceFactory, GroupFactory
from api.velos import calculate_velos_for_device
from minecraft.models import MinecraftOutboxEvent


@pytest.mark.unit
@pytest.mark.django_db
class TestApplyVelosEarn:
    def test_credits_balance_and_group_ledger(self):
        leaf_group = GroupFactory(name='Leaf')
        cyclist = CyclistFactory()
        cyclist.groups.add(leaf_group)
        device = DeviceFactory(group=leaf_group)
        config = device.configuration
        config.wheel_size = 2300.0
        config.paedagogischer_bonus = 0.0
        config.save()

        delta = apply_velos_earn(cyclist, device, Decimal('2.0'))
        assert delta == 200

        cyclist.save()
        cyclist.refresh_from_db()
        leaf_group.refresh_from_db()
        assert cyclist.velos_balance == 200
        assert leaf_group.velos_total == 200
        assert leaf_group.velos_spendable == 200

    def test_skips_operator_box(self):
        leaf_group = GroupFactory(name='Leaf')
        cyclist = CyclistFactory()
        cyclist.groups.add(leaf_group)
        device = DeviceFactory(group=leaf_group, is_operator_box=True)

        assert apply_velos_earn(cyclist, device, Decimal('1.0')) == 0
        cyclist.refresh_from_db()
        leaf_group.refresh_from_db()
        assert cyclist.velos_balance == 0
        assert leaf_group.velos_total == 0

    def test_queues_minecraft_for_group_mc_username(self):
        leaf_group = GroupFactory(name='Leaf', mc_username='team_alpha')
        cyclist = CyclistFactory()
        cyclist.groups.add(leaf_group)
        device = DeviceFactory(group=leaf_group)
        config = device.configuration
        config.wheel_size = 2300.0
        config.paedagogischer_bonus = 0.0
        config.save()

        apply_velos_earn(cyclist, device, Decimal('1.0'))

        event = MinecraftOutboxEvent.objects.filter(
            event_type=MinecraftOutboxEvent.EVENT_UPDATE_GROUP_VELOS,
        ).first()
        assert event is not None
        assert event.payload['player'] == 'team_alpha'
        assert event.payload['velos_total'] == 100
        assert event.payload['spendable_delta'] == 100


@pytest.mark.unit
@pytest.mark.django_db
class TestUpdateDataVelosIntegration:
    def _setup(self):
        leaf_group = GroupFactory(name='Class 1a')
        cyclist = CyclistFactory(id_tag='velos-integration-tag')
        cyclist.groups.add(leaf_group)
        device = DeviceFactory(name='velos-integration-device', group=leaf_group)
        config = device.configuration
        config.wheel_size = 2300.0
        config.paedagogischer_bonus = 0.0
        config.save()
        return cyclist, device, leaf_group

    def test_update_data_increases_velos_balance_and_ledger(self, api_key):
        cyclist, device, child_group = self._setup()

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
        expected_velos = calculate_velos_for_device(Decimal('1.0'), device)

        cyclist.refresh_from_db()
        child_group.refresh_from_db()
        assert cyclist.velos_balance == expected_velos
        assert child_group.velos_total == expected_velos
        assert child_group.velos_spendable == expected_velos

    def test_redemption_does_not_change_hourly_metric_velos(self, api_key):
        cyclist, device, child_group = self._setup()

        client = Client()
        client.post(
            reverse('update_data'),
            data=json.dumps({
                'id_tag': cyclist.id_tag,
                'device_id': device.name,
                'distance': '1.00000',
            }),
            content_type='application/json',
            HTTP_X_API_KEY=api_key,
        )

        metric = HourlyMetric.objects.create(
            cyclist=cyclist,
            device=device,
            timestamp=timezone.now(),
            distance_km=Decimal('0.50000'),
            group_at_time=child_group,
        )
        metric_velos_before = metric.velos

        redeem_cyclist_velos(cyclist)

        cyclist.refresh_from_db()
        assert cyclist.velos_balance == 0

        metric.refresh_from_db()
        assert metric.velos == metric_velos_before

        child_group.refresh_from_db()
        assert child_group.velos_total > 0
