# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

import pytest

from api.tests.conftest import GroupFactory
from minecraft.models import MinecraftOutboxEvent, MinecraftTeamRegistration
from minecraft.services.team_registration import (
    active_registrations,
    deactivate_registration,
    pending_team_candidates,
    register_group_for_minecraft,
    should_sync_group_to_minecraft,
)


@pytest.mark.unit
@pytest.mark.django_db
class TestTeamRegistration:
    def test_pending_candidates_excludes_registered(self):
        pending = GroupFactory(name='Pending', mc_username='pending_team')
        registered = GroupFactory(name='Registered', mc_username='registered_team')
        register_group_for_minecraft(registered)
        MinecraftOutboxEvent.objects.all().delete()

        pending_ids = set(pending_team_candidates().values_list('id', flat=True))
        assert pending.id in pending_ids
        assert registered.id not in pending_ids

    def test_register_group_creates_registration_and_queues_event(self):
        group = GroupFactory(name='Team', mc_username='team_x')
        registration = register_group_for_minecraft(group)

        assert registration.is_active is True
        assert registration.was_ever_registered is True
        assert MinecraftTeamRegistration.objects.filter(group=group).exists()
        assert MinecraftOutboxEvent.objects.filter(
            event_type=MinecraftOutboxEvent.EVENT_REGISTER_TEAM,
            payload__registration_id=registration.id,
        ).exists()

    def test_should_sync_only_for_active_registration(self):
        group = GroupFactory(name='Team', mc_username='team_x')
        assert should_sync_group_to_minecraft(group) is False

        registration = register_group_for_minecraft(group)
        MinecraftOutboxEvent.objects.all().delete()
        assert should_sync_group_to_minecraft(group) is True

        deactivate_registration(registration, reason="test")
        MinecraftOutboxEvent.objects.all().delete()
        assert should_sync_group_to_minecraft(group) is False

    def test_deactivate_queues_unregister(self):
        group = GroupFactory(name='Team', mc_username='team_x')
        registration = register_group_for_minecraft(group)
        MinecraftOutboxEvent.objects.all().delete()

        deactivate_registration(registration, reason="test_hide")

        registration.refresh_from_db()
        assert registration.is_active is False
        assert MinecraftOutboxEvent.objects.filter(
            event_type=MinecraftOutboxEvent.EVENT_UNREGISTER_TEAM,
            payload__player='team_x',
        ).exists()

    def test_active_registrations_only_visible_groups(self):
        visible = GroupFactory(name='Visible', mc_username='visible_team')
        hidden = GroupFactory(name='Hidden', mc_username='hidden_team', is_visible=False)
        register_group_for_minecraft(visible)
        MinecraftTeamRegistration.objects.create(
            group=hidden,
            mc_username='hidden_team',
            is_active=True,
            was_ever_registered=True,
        )

        active_names = set(active_registrations().values_list('mc_username', flat=True))
        assert 'visible_team' in active_names
        assert 'hidden_team' not in active_names
