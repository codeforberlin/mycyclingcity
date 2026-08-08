# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    test_mcc_counter_scan.py
# @note    Tests for POST /api/mcc-counter/scan/ RFID play-session API.

import json
from datetime import timedelta
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from minecraft.models import MCSession, MinecraftPlayAccount
from minecraft.services.session_control import (
    AccountAlreadyActiveError,
    RconSequenceError,
    SessionControlError,
)


@pytest.fixture
def api_key(settings):
    key = "TEST-API-KEY-12345"
    settings.MCC_APP_API_KEY = key
    return key


@pytest.fixture
def play_account(db):
    return MinecraftPlayAccount.objects.create(
        id_tag="RFID-AA-01",
        short_name="Arena1",
        display_name="Arena 1",
        sort_order=1,
    )


def _post_scan(client, api_key, payload):
    return client.post(
        reverse("mcc_counter_scan"),
        data=json.dumps(payload),
        content_type="application/json",
        HTTP_X_API_KEY=api_key,
    )


@pytest.mark.unit
@pytest.mark.django_db
class TestMccCounterScan:
    def test_missing_api_key(self, play_account):
        client = Client()
        response = client.post(
            reverse("mcc_counter_scan"),
            data=json.dumps({"token": "Arena1"}),
            content_type="application/json",
        )
        assert response.status_code == 403
        assert response.json()["ok"] is False
        assert response.json()["error"] == "invalid_api_key"

    def test_invalid_api_key(self, api_key, play_account):
        client = Client()
        response = client.post(
            reverse("mcc_counter_scan"),
            data=json.dumps({"token": "Arena1"}),
            content_type="application/json",
            HTTP_X_API_KEY="INVALID-KEY",
        )
        assert response.status_code == 403
        assert response.json()["error"] == "invalid_api_key"

    def test_missing_token(self, api_key, play_account):
        client = Client()
        response = _post_scan(client, api_key, {})
        assert response.status_code == 400
        assert response.json() == {"ok": False, "error": "missing_token"}

    def test_empty_token(self, api_key, play_account):
        client = Client()
        response = _post_scan(client, api_key, {"token": "  "})
        assert response.status_code == 400
        assert response.json()["error"] == "missing_token"

    def test_unknown_token(self, api_key, play_account):
        client = Client()
        response = _post_scan(client, api_key, {"token": "Missing"})
        assert response.status_code == 404
        data = response.json()
        assert data["ok"] is False
        assert data["error"] == "unknown_token"

    @patch("minecraft.api_views.start_player_session")
    def test_success_by_short_name(self, mock_start, api_key, play_account):
        ends = timezone.now() + timedelta(minutes=15)
        session = MagicMock()
        session.account_name = "Arena1"
        session.session_id = uuid4()
        session.ends_at = ends
        session.duration_minutes = 15
        mock_start.return_value = session

        client = Client()
        response = _post_scan(client, api_key, {"token": "Arena1"})
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["account"] == "Arena1"
        assert data["session_id"] == str(session.session_id)
        assert data["ends_at"] == ends.isoformat()
        assert data["duration_minutes"] == 15
        mock_start.assert_called_once_with("Arena1", source=MCSession.SOURCE_RFID)

    @patch("minecraft.api_views.start_player_session")
    def test_success_by_id_tag_alias(self, mock_start, api_key, play_account):
        ends = timezone.now() + timedelta(minutes=15)
        session = MagicMock()
        session.account_name = "Arena1"
        session.session_id = uuid4()
        session.ends_at = ends
        session.duration_minutes = 15
        mock_start.return_value = session

        client = Client()
        response = _post_scan(client, api_key, {"id_tag": "RFID-AA-01"})
        assert response.status_code == 200
        assert response.json()["account"] == "Arena1"
        mock_start.assert_called_once_with("RFID-AA-01", source=MCSession.SOURCE_RFID)

    @patch("minecraft.api_views.start_player_session")
    def test_already_active(self, mock_start, api_key, play_account):
        mock_start.side_effect = AccountAlreadyActiveError("Session already active for Arena1")
        client = Client()
        response = _post_scan(client, api_key, {"token": "Arena1"})
        assert response.status_code == 409
        data = response.json()
        assert data == {
            "ok": False,
            "error": "already_active",
            "account": "Arena1",
        }

    @patch("minecraft.api_views.start_player_session")
    def test_rcon_failed(self, mock_start, api_key, play_account):
        mock_start.side_effect = RconSequenceError("connection refused")
        client = Client()
        response = _post_scan(client, api_key, {"rfid": "Arena1"})
        assert response.status_code == 502
        data = response.json()
        assert data["ok"] is False
        assert data["error"] == "rcon_failed"
        assert "connection refused" in data["detail"]

    @patch("minecraft.api_views.start_player_session")
    def test_other_session_control_error(self, mock_start, api_key, play_account):
        mock_start.side_effect = SessionControlError(
            "duration must be >= 1",
            code="invalid_duration",
        )
        client = Client()
        response = _post_scan(client, api_key, {"token": "Arena1"})
        assert response.status_code == 400
        data = response.json()
        assert data["ok"] is False
        assert data["error"] == "invalid_duration"
