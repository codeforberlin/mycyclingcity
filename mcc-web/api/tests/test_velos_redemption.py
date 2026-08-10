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

    def test_partial_redeem_keeps_balance_and_session(self):
        leaf = GroupFactory(name='Leaf Partial')
        cyclist = CyclistFactory(velos_balance=500)
        cyclist.groups.set([leaf])
        device = DeviceFactory()
        CyclistDeviceCurrentMileage.objects.create(
            cyclist=cyclist,
            device=device,
            cumulative_mileage=Decimal('0.25000'),
        )

        result = redeem_cyclist_velos(cyclist, amount=200)

        assert result.success is True
        assert result.velos_redeemed == 200
        cyclist.refresh_from_db()
        assert cyclist.velos_balance == 300
        assert CyclistDeviceCurrentMileage.objects.filter(cyclist=cyclist).exists()

    def test_partial_redeem_last_amount_ends_session(self):
        leaf = GroupFactory(name='Leaf Final')
        cyclist = CyclistFactory(velos_balance=150)
        cyclist.groups.set([leaf])
        device = DeviceFactory()
        CyclistDeviceCurrentMileage.objects.create(
            cyclist=cyclist,
            device=device,
            cumulative_mileage=Decimal('0.10000'),
        )

        result = redeem_cyclist_velos(cyclist, amount=150)

        assert result.success is True
        cyclist.refresh_from_db()
        assert cyclist.velos_balance == 0
        assert not CyclistDeviceCurrentMileage.objects.filter(cyclist=cyclist).exists()

    def test_redeem_amount_exceeds_balance_fails(self):
        leaf = GroupFactory(name='Leaf Over')
        cyclist = CyclistFactory(velos_balance=80)
        cyclist.groups.set([leaf])

        result = redeem_cyclist_velos(cyclist, amount=100)

        assert result.success is False
        cyclist.refresh_from_db()
        assert cyclist.velos_balance == 80


@pytest.mark.unit
@pytest.mark.django_db
class TestVelosMinecraftPlayerSession:
    def test_redeem_creates_waitlist_entry(self):
        from api.services.velos_minecraft_redemption import redeem_velos_for_player_session
        from minecraft.models import MinecraftIntegrationConfig, MinecraftSessionWaitlistEntry

        MinecraftIntegrationConfig.get_config()
        leaf = GroupFactory(name='MC Leaf')
        cyclist = CyclistFactory(user_id='mc-player', velos_balance=400)
        cyclist.groups.set([leaf])

        result = redeem_velos_for_player_session(cyclist, 300, note='Counter MC')

        assert result.success is True
        assert result.velos_redeemed == 300
        assert result.waitlist_entry is not None
        entry = result.waitlist_entry
        assert entry.queue_type == MinecraftSessionWaitlistEntry.QUEUE_PLAYER
        assert entry.source == MinecraftSessionWaitlistEntry.SOURCE_VELOS_REDEEM
        assert entry.velos_cost == 300
        assert entry.duration_minutes == 15
        assert entry.guest_label == 'mc-player'
        assert entry.cyclist_id == cyclist.pk
        assert entry.velos_redemption_id == result.redemption.pk
        cyclist.refresh_from_db()
        assert cyclist.velos_balance == 100

    def test_redeem_below_min_fails_without_deduct(self):
        from api.services.velos_minecraft_redemption import redeem_velos_for_player_session
        from minecraft.models import MinecraftIntegrationConfig, MinecraftSessionWaitlistEntry

        config = MinecraftIntegrationConfig.get_config()
        config.player_min_velos = 300
        config.save()
        leaf = GroupFactory(name='MC Min Leaf')
        cyclist = CyclistFactory(user_id='mc-min', velos_balance=400)
        cyclist.groups.set([leaf])

        result = redeem_velos_for_player_session(cyclist, 200)

        assert result.success is False
        cyclist.refresh_from_db()
        assert cyclist.velos_balance == 400
        assert MinecraftSessionWaitlistEntry.objects.count() == 0

    def test_atomic_rollback_on_waitlist_failure(self):
        from unittest.mock import patch

        from api.services.velos_minecraft_redemption import redeem_velos_for_player_session
        from minecraft.models import MinecraftIntegrationConfig, MinecraftSessionWaitlistEntry
        from minecraft.services.waitlist_service import WaitlistError

        MinecraftIntegrationConfig.get_config()
        leaf = GroupFactory(name='MC Rollback Leaf')
        cyclist = CyclistFactory(user_id='mc-rollback', velos_balance=400)
        cyclist.groups.set([leaf])

        with patch(
            'api.services.velos_minecraft_redemption.add_waitlist_entry',
            side_effect=WaitlistError('waitlist failed'),
        ):
            result = redeem_velos_for_player_session(cyclist, 300)

        assert result.success is False
        cyclist.refresh_from_db()
        assert cyclist.velos_balance == 400
        assert cyclist.velos_redemptions.count() == 0
        assert MinecraftSessionWaitlistEntry.objects.count() == 0


@pytest.mark.unit
@pytest.mark.django_db
class TestVelosMinecraftBuilderSession:
    def test_redeem_creates_builder_waitlist_entry(self):
        from api.services.velos_minecraft_redemption import redeem_velos_for_builder_session
        from minecraft.models import MinecraftIntegrationConfig, MinecraftSessionWaitlistEntry

        config = MinecraftIntegrationConfig.get_config()
        config.player_velos_per_minute = 20
        config.player_min_velos = 300
        config.save()
        leaf = GroupFactory(name='MC Builder Leaf')
        cyclist = CyclistFactory(user_id='mc-builder', velos_balance=500)
        cyclist.groups.set([leaf])

        result = redeem_velos_for_builder_session(cyclist, 300, note='Counter Bau')

        assert result.success is True
        assert result.velos_redeemed == 300
        entry = result.waitlist_entry
        assert entry.queue_type == MinecraftSessionWaitlistEntry.QUEUE_BUILDER
        assert entry.source == MinecraftSessionWaitlistEntry.SOURCE_VELOS_REDEEM
        assert entry.velos_cost == 300
        assert entry.duration_minutes == 15
        assert entry.guest_label == 'mc-builder'
        cyclist.refresh_from_db()
        assert cyclist.velos_balance == 200

    def test_redeem_longer_session_scales_with_velos(self):
        from api.services.velos_minecraft_redemption import redeem_velos_for_builder_session
        from minecraft.models import MinecraftIntegrationConfig

        config = MinecraftIntegrationConfig.get_config()
        config.player_velos_per_minute = 20
        config.player_min_velos = 300
        config.save()
        leaf = GroupFactory(name='MC Builder Custom')
        cyclist = CyclistFactory(user_id='mc-builder-custom', velos_balance=700)
        cyclist.groups.set([leaf])

        result = redeem_velos_for_builder_session(cyclist, 600)

        assert result.success is True
        assert result.waitlist_entry.duration_minutes == 30

    def test_redeem_below_min_fails_without_deduct(self):
        from api.services.velos_minecraft_redemption import redeem_velos_for_builder_session
        from minecraft.models import MinecraftIntegrationConfig, MinecraftSessionWaitlistEntry

        config = MinecraftIntegrationConfig.get_config()
        config.player_min_velos = 300
        config.save()
        leaf = GroupFactory(name='MC Builder Min')
        cyclist = CyclistFactory(user_id='mc-builder-min', velos_balance=400)
        cyclist.groups.set([leaf])

        result = redeem_velos_for_builder_session(cyclist, 200)

        assert result.success is False
        cyclist.refresh_from_db()
        assert cyclist.velos_balance == 400
        assert MinecraftSessionWaitlistEntry.objects.count() == 0
