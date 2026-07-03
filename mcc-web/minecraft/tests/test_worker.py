# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

import pytest
from unittest.mock import patch

from minecraft.models import MinecraftOutboxEvent
from minecraft.services.worker import process_next_event
from api.tests.conftest import GroupFactory


@pytest.mark.unit
@pytest.mark.django_db
class TestWorkerService:
    @patch('minecraft.services.worker.rcon_client')
    @patch('minecraft.services.worker.ensure_group_velos_scoreboards')
    def test_process_update_group_velos_event(self, mock_ensure, mock_rcon):
        mock_ensure.return_value = None
        mock_rcon.set_player_score.return_value = None

        event = MinecraftOutboxEvent.objects.create(
            event_type=MinecraftOutboxEvent.EVENT_UPDATE_GROUP_VELOS,
            payload={
                "player": "team_alpha",
                "velos_total": 1000,
                "velos_spendable": 500,
                "reason": "test",
            },
        )

        with patch('minecraft.services.worker.rcon_client', mock_rcon):
            result = process_next_event()

        assert result is True
        event.refresh_from_db()
        assert event.status == MinecraftOutboxEvent.STATUS_DONE
        assert mock_rcon.set_player_score.call_count == 2

    @patch('minecraft.services.worker.rcon_client')
    @patch('minecraft.services.worker.ensure_group_velos_scoreboards')
    def test_process_update_group_velos_with_add_action(self, mock_ensure, mock_rcon):
        mock_ensure.return_value = None
        mock_rcon.set_player_score.return_value = None
        mock_rcon.add_player_score.return_value = None

        event = MinecraftOutboxEvent.objects.create(
            event_type=MinecraftOutboxEvent.EVENT_UPDATE_GROUP_VELOS,
            payload={
                "player": "team_alpha",
                "velos_total": 1000,
                "velos_spendable": 500,
                "spendable_action": "add",
                "spendable_delta": 100,
                "reason": "test",
            },
        )

        with patch('minecraft.services.worker.rcon_client', mock_rcon):
            result = process_next_event()

        assert result is True
        event.refresh_from_db()
        assert event.status == MinecraftOutboxEvent.STATUS_DONE
        assert mock_rcon.set_player_score.call_count == 1
        assert mock_rcon.add_player_score.call_count == 1

    @patch('minecraft.services.worker.rcon_client')
    @patch('minecraft.services.worker.ensure_group_velos_scoreboards')
    def test_process_sync_all_event(self, mock_ensure, mock_rcon):
        mock_ensure.return_value = None
        mock_rcon.set_player_score.return_value = None

        GroupFactory(name='Team A', mc_username='team_a', velos_total=1000, velos_spendable=500)
        GroupFactory(name='Team B', mc_username='team_b', velos_total=2000, velos_spendable=1000)

        event = MinecraftOutboxEvent.objects.create(
            event_type=MinecraftOutboxEvent.EVENT_SYNC_ALL,
            payload={"reason": "test_sync"},
        )

        with patch('minecraft.services.worker.rcon_client', mock_rcon):
            result = process_next_event()

        assert result is True
        event.refresh_from_db()
        assert event.status == MinecraftOutboxEvent.STATUS_DONE
        assert mock_rcon.set_player_score.call_count == 4

    def test_process_next_event_no_pending(self):
        result = process_next_event()
        assert result is False

    @patch('minecraft.services.worker.rcon_client')
    @patch('minecraft.services.worker.ensure_group_velos_scoreboards')
    def test_process_update_group_velos_missing_player(self, mock_ensure, mock_rcon):
        event = MinecraftOutboxEvent.objects.create(
            event_type=MinecraftOutboxEvent.EVENT_UPDATE_GROUP_VELOS,
            payload={
                "velos_total": 1000,
                "velos_spendable": 500,
            },
        )

        with patch('minecraft.services.worker.rcon_client', mock_rcon):
            result = process_next_event()

        assert result is True
        event.refresh_from_db()
        assert event.status == MinecraftOutboxEvent.STATUS_FAILED
        assert "Missing player" in event.last_error

    def test_process_deprecated_player_coins_event_is_skipped(self):
        event = MinecraftOutboxEvent.objects.create(
            event_type=MinecraftOutboxEvent.EVENT_UPDATE_PLAYER_COINS,
            payload={"player": "legacy", "coins_total": 1, "coins_spendable": 1},
        )

        result = process_next_event()

        assert result is True
        event.refresh_from_db()
        assert event.status == MinecraftOutboxEvent.STATUS_DONE
