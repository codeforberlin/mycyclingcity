# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    test_dynamo_earn.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

"""Tests for dynamo energy ingest on distance updates."""

from decimal import Decimal

import pytest
from django.utils import timezone

from api.models import CyclistDeviceCurrentMileage, HourlyMetric
from api.services.dynamo_earn import apply_dynamo_earn
from api.tests.conftest import CyclistFactory, DeviceFactory, GroupFactory
from dynamo.models import DynamoDisplaySettings


@pytest.mark.django_db
class TestDynamoEarn:
    def test_apply_dynamo_earn_updates_session_and_metric(self):
        DynamoDisplaySettings.get_settings()
        leaf = GroupFactory(name='EarnLeaf')
        device = DeviceFactory()
        # Ensure 60s interval and known wheel size
        device.configuration.send_interval_seconds = 60
        device.configuration.wheel_size = 2075.0
        device.configuration.save()

        cyclist = CyclistFactory()
        cyclist.groups.add(leaf)
        session = CyclistDeviceCurrentMileage.objects.create(
            cyclist=cyclist,
            device=device,
            cumulative_mileage=Decimal('0.25000'),
        )

        # 0.25 km / 60 s → 15 km/h → 3 W → 0.05 Wh
        energy = apply_dynamo_earn(session, device, Decimal('0.25000'))
        session.save()

        assert energy == Decimal('0.05000')
        assert session.last_power_w == pytest.approx(3.0)
        assert session.session_energy_wh == Decimal('0.05000')
        assert session.last_rpm > 0

        metric = HourlyMetric.objects.get(
            cyclist=cyclist,
            device=device,
            timestamp=timezone.now().replace(minute=0, second=0, microsecond=0),
        )
        assert metric.energy_wh == Decimal('0.05000')

    def test_zero_distance_skipped(self):
        device = DeviceFactory()
        cyclist = CyclistFactory()
        session = CyclistDeviceCurrentMileage.objects.create(
            cyclist=cyclist,
            device=device,
            cumulative_mileage=Decimal('0'),
        )
        energy = apply_dynamo_earn(session, device, Decimal('0'))
        assert energy == Decimal('0.00000')
        assert HourlyMetric.objects.count() == 0
