# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

import pytest
from decimal import Decimal

from eventboard.utils import get_session_velos_for_cyclist
from api.tests.conftest import CyclistFactory, DeviceFactory, CyclistDeviceCurrentMileageFactory


@pytest.mark.unit
@pytest.mark.django_db
class TestSessionVelosHelper:
    def test_returns_zero_without_session(self):
        cyclist = CyclistFactory()
        assert get_session_velos_for_cyclist(cyclist) == 0

    def test_calculates_velos_from_session_distance(self):
        cyclist = CyclistFactory()
        device = DeviceFactory()
        config = device.configuration
        config.wheel_size = 2300.0
        config.paedagogischer_bonus = 0.0
        config.save()
        CyclistDeviceCurrentMileageFactory(
            cyclist=cyclist,
            device=device,
            cumulative_mileage=Decimal('2.50000'),
        )
        assert get_session_velos_for_cyclist(cyclist) == 250
