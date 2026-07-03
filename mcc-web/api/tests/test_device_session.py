# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for device session end helpers (FEZitty game workflow)."""

import pytest
from decimal import Decimal

from api.models import Cyclist, CyclistDeviceCurrentMileage
from api.services.device_session import (
    end_cyclist_device_session,
    end_device_session_for_device,
    end_game_round_device_sessions,
)
from api.tests.conftest import CyclistFactory, DeviceFactory, GroupFactory
from iot.models import DeviceConfiguration


@pytest.mark.unit
@pytest.mark.django_db
class TestEndCyclistDeviceSession:
    def test_ends_active_session(self, db):
        cyclist = CyclistFactory()
        device = DeviceFactory()
        CyclistDeviceCurrentMileage.objects.create(
            cyclist=cyclist,
            device=device,
            cumulative_mileage=Decimal('1.50000'),
        )
        assert end_cyclist_device_session(cyclist, reason='test') is True
        assert not CyclistDeviceCurrentMileage.objects.filter(cyclist=cyclist).exists()

    def test_no_session_returns_false(self, db):
        cyclist = CyclistFactory()
        assert end_cyclist_device_session(cyclist) is False


@pytest.mark.unit
@pytest.mark.django_db
class TestEndGameRoundDeviceSessions:
    def test_ends_configured_cyclist_sessions(self, db):
        group = GroupFactory()
        default = CyclistFactory(user_id='Kette')
        guest = CyclistFactory(user_id='Gast1')
        device = DeviceFactory(name='Counter-A', group=group)
        DeviceConfiguration.objects.filter(device=device).update(default_id_tag=default.id_tag)

        CyclistDeviceCurrentMileage.objects.create(
            cyclist=default,
            device=device,
            cumulative_mileage=Decimal('2.00000'),
        )

        result = end_game_round_device_sessions(
            {'Counter-A': 'Kette'},
            reason='game_round_start',
        )
        assert default.id in result.ended_cyclist_ids
        assert not CyclistDeviceCurrentMileage.objects.filter(device=device).exists()

    def test_skips_standalone_cyclist_on_device(self, db):
        group = GroupFactory()
        default = CyclistFactory(user_id='Kette')
        standalone = CyclistFactory(user_id='Standalone')
        device = DeviceFactory(name='Counter-B', group=group)
        DeviceConfiguration.objects.filter(device=device).update(default_id_tag=default.id_tag)

        CyclistDeviceCurrentMileage.objects.create(
            cyclist=standalone,
            device=device,
            cumulative_mileage=Decimal('3.00000'),
        )

        result = end_game_round_device_sessions(
            {'Counter-B': 'Kette'},
            reason='game_round_start',
        )
        assert device.name in result.skipped_device_names
        assert CyclistDeviceCurrentMileage.objects.filter(device=device).exists()


@pytest.mark.unit
@pytest.mark.django_db
class TestEndDeviceSessionForDevice:
    def test_ends_session_on_device(self, db):
        cyclist = CyclistFactory()
        device = DeviceFactory()
        CyclistDeviceCurrentMileage.objects.create(
            cyclist=cyclist,
            device=device,
            cumulative_mileage=Decimal('0.50000'),
        )
        ended = end_device_session_for_device(device, reason='operator_reset')
        assert ended == cyclist
        assert not CyclistDeviceCurrentMileage.objects.filter(device=device).exists()
