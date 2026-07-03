# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

import pytest
from decimal import Decimal

from api.models import CyclistDeviceCurrentMileage, HourlyMetric
from api.services.velos_redemption import redeem_cyclist_velos
from api.tests.conftest import CyclistFactory, DeviceFactory, GroupFactory, HourlyMetricFactory


@pytest.mark.unit
@pytest.mark.django_db
class TestVelosRedemption:
    def test_redeem_clears_balance_and_ends_session(self):
        leaf = GroupFactory(name='Leaf Class')
        cyclist = CyclistFactory(velos_balance=320)
        cyclist.groups.set([leaf])
        device = DeviceFactory()
        CyclistDeviceCurrentMileage.objects.create(
            cyclist=cyclist,
            device=device,
            cumulative_mileage=Decimal('0.50000'),
        )

        result = redeem_cyclist_velos(cyclist, note='Wuhlis')

        assert result.success is True
        assert result.velos_redeemed == 320
        cyclist.refresh_from_db()
        assert cyclist.velos_balance == 0
        assert not CyclistDeviceCurrentMileage.objects.filter(cyclist=cyclist).exists()
        assert cyclist.velos_redemptions.count() == 1

    def test_redeem_does_not_change_hourly_metric(self):
        leaf = GroupFactory(name='Leaf B')
        cyclist = CyclistFactory(velos_balance=100)
        cyclist.groups.set([leaf])
        device = DeviceFactory()
        metric = HourlyMetricFactory(
            cyclist=cyclist,
            device=device,
            distance_km=Decimal('1.00000'),
            group_at_time=leaf,
        )
        original_velos = metric.velos
        original_km = metric.distance_km

        redeem_cyclist_velos(cyclist)

        metric.refresh_from_db()
        assert metric.velos == original_velos
        assert metric.distance_km == original_km

    def test_redeem_zero_balance_fails(self):
        cyclist = CyclistFactory(velos_balance=0)
        result = redeem_cyclist_velos(cyclist)
        assert result.success is False
