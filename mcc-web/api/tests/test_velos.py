# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

import pytest
from decimal import Decimal
from django.utils import timezone

from api.velos import (
    FKM_BASE_MM,
    PAEDAGOGICAL_BONUS,
    build_session_velos_api_payload,
    calculate_velos,
    calculate_velos_for_device,
    format_velos_de,
    get_fkm_factor,
    get_fkm_factor_for_device,
    track_reference_velos,
)
from api.tests.conftest import DeviceFactory


@pytest.mark.unit
class TestVelosCalculation:
    def test_fkm_factor_29_inch_no_bonus(self):
        factor = get_fkm_factor(2300, 0.0)
        assert factor == pytest.approx(1.0)

    def test_fkm_factor_20_inch_with_bonus(self):
        factor = get_fkm_factor(1600, PAEDAGOGICAL_BONUS)
        assert factor == pytest.approx(FKM_BASE_MM / 1600 + PAEDAGOGICAL_BONUS)

    def test_calculate_velos_one_km_29_inch(self):
        assert calculate_velos(1, 1.0) == 100

    def test_calculate_velos_fractional_km_truncates(self):
        assert calculate_velos(Decimal('0.005'), 1.0) == 0
        assert calculate_velos(Decimal('0.015'), 1.0) == 1

    def test_fairness_smaller_wheel_more_velos(self):
        km = Decimal('1.0')
        velos_29 = calculate_velos(km, get_fkm_factor(2300, 0.0))
        velos_20 = calculate_velos(km, get_fkm_factor(1600, PAEDAGOGICAL_BONUS))
        assert velos_20 > velos_29

    def test_track_reference_velos(self):
        assert track_reference_velos(10) == 1000


@pytest.mark.unit
@pytest.mark.django_db
class TestVelosDevice:
    def test_calculate_velos_for_device_uses_bonus(self):
        device = DeviceFactory()
        config = device.configuration
        config.wheel_size = 1600.0
        config.paedagogischer_bonus = PAEDAGOGICAL_BONUS
        config.save()

        expected = calculate_velos(1, get_fkm_factor_for_device(device))
        assert calculate_velos_for_device(1, device) == expected


@pytest.mark.unit
@pytest.mark.django_db
class TestHourlyMetricVelos:
    def test_save_computes_velos_from_distance_km(self):
        device = DeviceFactory()
        config = device.configuration
        config.wheel_size = 2300.0
        config.paedagogischer_bonus = 0.0
        config.save()

        from api.models import HourlyMetric
        from api.tests.conftest import CyclistFactory, GroupFactory

        metric = HourlyMetric(
            device=device,
            cyclist=CyclistFactory(),
            timestamp=timezone.now(),
            distance_km=Decimal('1.00000'),
            group_at_time=GroupFactory(),
        )
        metric.save()
        assert metric.velos == 100


@pytest.mark.unit
class TestFormatVelosDe:
    def test_format_zero(self):
        assert format_velos_de(0) == "0"

    def test_format_thousands(self):
        assert format_velos_de(4520) == "4.520"


@pytest.mark.unit
@pytest.mark.django_db
class TestSessionVelosApiPayload:
    def test_build_session_velos_api_payload(self):
        from api.models import CyclistDeviceCurrentMileage
        from api.tests.conftest import CyclistFactory

        device = DeviceFactory()
        config = device.configuration
        config.wheel_size = 2300.0
        config.paedagogischer_bonus = 0.0
        config.save()
        cyclist = CyclistFactory()
        session = CyclistDeviceCurrentMileage.objects.create(
            cyclist=cyclist,
            device=device,
            cumulative_mileage=Decimal('1.00000'),
        )

        payload = build_session_velos_api_payload(session, device)

        assert payload['session_velos'] == 100
        assert payload['session_velos_display'] == '100'
        assert payload['session_epoch'] == session.start_time.isoformat()
        assert payload['session_km'] == '1.00000'
