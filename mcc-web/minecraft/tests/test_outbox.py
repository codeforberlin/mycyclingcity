# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

import pytest

from minecraft.models import MinecraftOutboxEvent
from minecraft.services.outbox import queue_group_velos_update, queue_full_sync


@pytest.mark.unit
@pytest.mark.django_db
class TestOutboxService:
    def test_queue_group_velos_update(self):
        event = queue_group_velos_update(
            player="team_alpha",
            velos_total=1000,
            velos_spendable=500,
            reason="test_reason",
        )

        assert event.event_type == MinecraftOutboxEvent.EVENT_UPDATE_GROUP_VELOS
        assert event.status == MinecraftOutboxEvent.STATUS_PENDING
        assert event.payload["player"] == "team_alpha"
        assert event.payload["velos_total"] == 1000
        assert event.payload["velos_spendable"] == 500
        assert event.payload["reason"] == "test_reason"
        assert event.payload["spendable_action"] == "set"
        assert "queued_at" in event.payload

    def test_queue_group_velos_update_with_delta(self):
        event = queue_group_velos_update(
            player="team_alpha",
            velos_total=1000,
            velos_spendable=500,
            reason="test_reason",
            spendable_action="add",
            spendable_delta=100,
        )

        assert event.payload["spendable_action"] == "add"
        assert event.payload["spendable_delta"] == 100

    def test_queue_full_sync(self):
        event = queue_full_sync(reason="test_sync")

        assert event.event_type == MinecraftOutboxEvent.EVENT_SYNC_ALL
        assert event.status == MinecraftOutboxEvent.STATUS_PENDING
        assert event.payload["reason"] == "test_sync"
        assert "queued_at" in event.payload
