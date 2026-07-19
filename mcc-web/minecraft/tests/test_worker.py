# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

import pytest
from unittest.mock import patch

from minecraft.models import MinecraftOutboxEvent, MinecraftTeamRegistration
from minecraft.services.worker import process_next_event
from minecraft.services.team_registration import register_group_for_minecraft
from api.tests.conftest import GroupFactory


@pytest.mark.unit
@pytest.mark.django_db
class TestWorkerService:
    @patch('minecraft.services.worker.ensure_team_scoreboard_objective')
    @patch('minecraft.services.worker.set_team_spendable_score')
    def test_process_update_team_velos_event(self, mock_set, mock_ensure):
        mock_ensure.return_value = "team_velos_spendable"

        event = MinecraftOutboxEvent.objects.create(
            event_type=MinecraftOutboxEvent.EVENT_UPDATE_TEAM_VELOS,
            payload={
                "player": "team_alpha",
                "velos_spendable": 500,
                "reason": "test",
            },
        )

        result = process_next_event()

        assert result is True
        event.refresh_from_db()
        assert event.status == MinecraftOutboxEvent.STATUS_DONE
        mock_set.assert_called_once_with("team_alpha", 500)

    @patch('minecraft.services.worker.ensure_team_scoreboard_objective')
    @patch('minecraft.services.worker.set_team_spendable_score')
    @patch('minecraft.services.worker.add_team_spendable_score')
    def test_process_update_team_velos_with_add_action(self, mock_add, mock_set, mock_ensure):
        mock_ensure.return_value = "team_velos_spendable"

        event = MinecraftOutboxEvent.objects.create(
            event_type=MinecraftOutboxEvent.EVENT_UPDATE_TEAM_VELOS,
            payload={
                "player": "team_alpha",
                "velos_spendable": 500,
                "spendable_action": "add",
                "spendable_delta": 100,
                "reason": "test",
            },
        )

        result = process_next_event()

        assert result is True
        event.refresh_from_db()
        assert event.status == MinecraftOutboxEvent.STATUS_DONE
        mock_set.assert_not_called()
        mock_add.assert_called_once_with("team_alpha", 100)

    @patch('minecraft.services.worker.sync_all_registered_teams')
    def test_process_sync_registered_teams_event(self, mock_sync):
        mock_sync.return_value = 2

        event = MinecraftOutboxEvent.objects.create(
            event_type=MinecraftOutboxEvent.EVENT_SYNC_REGISTERED_TEAMS,
            payload={"reason": "test_sync"},
        )

        result = process_next_event()

        assert result is True
        event.refresh_from_db()
        assert event.status == MinecraftOutboxEvent.STATUS_DONE
        mock_sync.assert_called_once()

    @patch('minecraft.services.worker.sync_all_registered_teams')
    def test_process_legacy_sync_all_event(self, mock_sync):
        mock_sync.return_value = 1

        event = MinecraftOutboxEvent.objects.create(
            event_type=MinecraftOutboxEvent.EVENT_SYNC_ALL,
            payload={"reason": "test_sync"},
        )

        result = process_next_event()

        assert result is True
        mock_sync.assert_called_once()

    def test_process_next_event_no_pending(self):
        result = process_next_event()
        assert result is False

    @patch('minecraft.services.worker.ensure_team_scoreboard_objective')
    def test_process_update_team_velos_missing_player(self, mock_ensure):
        event = MinecraftOutboxEvent.objects.create(
            event_type=MinecraftOutboxEvent.EVENT_UPDATE_TEAM_VELOS,
            payload={"velos_spendable": 500},
        )

        result = process_next_event()

        assert result is True
        event.refresh_from_db()
        assert event.status == MinecraftOutboxEvent.STATUS_FAILED
        assert "Missing player" in event.last_error

    @patch('minecraft.services.worker.ensure_team_scoreboard_objective')
    @patch('minecraft.services.worker.add_team_spendable_score')
    def test_transient_rcon_error_keeps_event_pending(self, mock_add, mock_ensure):
        mock_ensure.return_value = "team_velos_spendable"
        mock_add.side_effect = OSError(111, "Connection refused")

        event = MinecraftOutboxEvent.objects.create(
            event_type=MinecraftOutboxEvent.EVENT_UPDATE_TEAM_VELOS,
            payload={
                "player": "team_alpha",
                "velos_spendable": 500,
                "spendable_action": "add",
                "spendable_delta": 10,
                "reason": "db_update",
            },
        )

        result = process_next_event()

        assert result is True
        event.refresh_from_db()
        assert event.status == MinecraftOutboxEvent.STATUS_PENDING
        assert "Connection refused" in event.last_error
        assert event.processed_at is not None
        assert event.attempts == 1

    def test_requeue_transient_failed_events(self):
        from minecraft.services.worker import requeue_transient_failed_events

        keep = MinecraftOutboxEvent.objects.create(
            event_type=MinecraftOutboxEvent.EVENT_UPDATE_TEAM_VELOS,
            payload={"player": "a", "velos_spendable": 1},
            status=MinecraftOutboxEvent.STATUS_FAILED,
            last_error="Missing player in payload",
        )
        retry = MinecraftOutboxEvent.objects.create(
            event_type=MinecraftOutboxEvent.EVENT_UPDATE_TEAM_VELOS,
            payload={"player": "b", "velos_spendable": 1},
            status=MinecraftOutboxEvent.STATUS_FAILED,
            last_error="[Errno 111] Connection refused",
        )

        n = requeue_transient_failed_events(limit=50)
        assert n == 1
        keep.refresh_from_db()
        retry.refresh_from_db()
        assert keep.status == MinecraftOutboxEvent.STATUS_FAILED
        assert retry.status == MinecraftOutboxEvent.STATUS_PENDING
        assert retry.processed_at is None

    def test_process_deprecated_player_coins_event_is_skipped(self):
        event = MinecraftOutboxEvent.objects.create(
            event_type=MinecraftOutboxEvent.EVENT_UPDATE_PLAYER_COINS,
            payload={"player": "legacy", "coins_total": 1, "coins_spendable": 1},
        )

        result = process_next_event()

        assert result is True
        event.refresh_from_db()
        assert event.status == MinecraftOutboxEvent.STATUS_DONE

    @patch('minecraft.services.worker.register_team_on_server')
    def test_process_register_team_event(self, mock_register):
        group = GroupFactory(name='Team A', mc_username='team_a', velos_spendable=250)
        registration = register_group_for_minecraft(group)
        MinecraftOutboxEvent.objects.filter(
            event_type=MinecraftOutboxEvent.EVENT_REGISTER_TEAM
        ).delete()

        event = MinecraftOutboxEvent.objects.create(
            event_type=MinecraftOutboxEvent.EVENT_REGISTER_TEAM,
            payload={"registration_id": registration.id},
        )

        result = process_next_event()

        assert result is True
        mock_register.assert_called_once()

    @patch('minecraft.services.worker.unregister_team_on_server')
    def test_process_unregister_team_event(self, mock_unregister):
        event = MinecraftOutboxEvent.objects.create(
            event_type=MinecraftOutboxEvent.EVENT_UNREGISTER_TEAM,
            payload={"player": "team_alpha"},
        )

        result = process_next_event()

        assert result is True
        mock_unregister.assert_called_once_with("team_alpha")

    @patch('minecraft.services.worker._handle_update_team_velos')
    def test_process_legacy_update_group_velos_event(self, mock_handler):
        event = MinecraftOutboxEvent.objects.create(
            event_type=MinecraftOutboxEvent.EVENT_UPDATE_GROUP_VELOS,
            payload={"player": "team_alpha", "velos_spendable": 100},
        )

        result = process_next_event()

        assert result is True
        mock_handler.assert_called_once()
