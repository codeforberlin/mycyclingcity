# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from luanti.models import LuantiAccount, LuantiIntegrationConfig, LuantiSession
from luanti.services.session_control import (
    SessionError,
    account_time_step_minutes,
    clamp_duration_minutes,
    extend_session,
    join_payload,
    pause_session,
    reconcile_sessions_with_online_players,
    reduce_session,
    resolve_duration_minutes,
    resume_session,
    start_session,
)


@pytest.fixture
def account(db):
    return LuantiAccount.objects.create(
        login_name="Kid1",
        id_tag="Kid1",
        session_duration_minutes=30,
        session_duration_min_minutes=10,
        session_duration_max_minutes=60,
    )


@pytest.mark.django_db
def test_resolve_duration_clamps_to_account_bounds(account):
    account.session_duration_minutes = 5
    account.save(update_fields=["session_duration_minutes"])
    assert resolve_duration_minutes(account) == 10  # min floor

    account.session_duration_minutes = 999
    account.save(update_fields=["session_duration_minutes"])
    assert resolve_duration_minutes(account) == 60  # max ceiling


@pytest.mark.django_db
def test_account_time_step_uses_account_then_config(account, db):
    cfg = LuantiIntegrationConfig.get_config()
    cfg.session_add_minutes = 15
    cfg.save(update_fields=["session_add_minutes"])
    account.session_add_minutes = None
    account.save(update_fields=["session_add_minutes"])
    assert account_time_step_minutes(account) == 15
    account.session_add_minutes = 5
    account.save(update_fields=["session_add_minutes"])
    assert account_time_step_minutes(account) == 5
    session = start_session(account=account, duration=20)
    extend_session(session)  # default step from account = 5
    session.refresh_from_db()
    remaining = int((session.ends_at - session.timestamp_start).total_seconds() // 60)
    assert remaining == 25


@pytest.mark.django_db
def test_unlimited_skips_clamp(account):
    account.session_unlimited = True
    account.save(update_fields=["session_unlimited"])
    assert resolve_duration_minutes(account) == 0
    assert clamp_duration_minutes(account, 45) == 0


@pytest.mark.django_db
def test_pause_and_resume_preserves_remaining(account):
    session = start_session(account=account, duration=20)
    assert session.status == LuantiSession.STATUS_ACTIVE
    assert session.ends_at is not None
    before = session.ends_at

    pause_session(session)
    session.refresh_from_db()
    assert session.status == LuantiSession.STATUS_PAUSED
    assert session.ends_at is None
    assert session.remaining_seconds is not None
    assert session.remaining_seconds > 0

    # Time freeze: remaining should restore roughly
    remaining = session.remaining_seconds
    resume_session(session)
    session.refresh_from_db()
    assert session.status == LuantiSession.STATUS_ACTIVE
    assert session.ends_at is not None
    delta = abs((session.ends_at - timezone.now()).total_seconds() - remaining)
    assert delta < 3
    assert before > timezone.now()  # sanity


@pytest.mark.django_db
def test_join_while_paused_freezes_player(account):
    session = start_session(account=account, mode="play", duration=20)
    pause_session(session)
    payload = join_payload(account.login_name)
    assert payload["ok"] is True
    assert payload["paused"] is True
    assert payload["mode"] == "paused"
    assert payload["session_mode"] == "play"
    assert payload["privs"] == ["shout"]
    assert "fly" not in payload["privs"]
    assert "interact" not in payload["privs"]


@pytest.mark.django_db
def test_reduce_and_extend_session(account):
    session = start_session(account=account, duration=30)
    end1 = session.ends_at
    reduce_session(session, minutes=5)
    session.refresh_from_db()
    assert session.ends_at < end1
    extend_session(session, minutes=5)
    session.refresh_from_db()
    assert session.ends_at >= end1 - timedelta(seconds=2)


@pytest.mark.django_db
def test_extend_respects_max(account):
    session = start_session(account=account, duration=55)
    # max is 60 → can add at most ~5
    extend_session(session, minutes=30)
    session.refresh_from_db()
    cap = session.timestamp_start + timedelta(minutes=60)
    assert session.ends_at <= cap + timedelta(seconds=1)


@pytest.mark.django_db
def test_prepare_shutdown_force_ends_when_bridge_offline(account, monkeypatch):
    from luanti.services import session_control as sc

    session = start_session(account=account, duration=20)
    monkeypatch.setattr(
        "luanti.services.bridge_connection.bridge_is_online", lambda server_id=None: False
    )
    pushed = []

    def _push(msg):
        pushed.append(msg)
        return 1

    monkeypatch.setattr(
        "luanti.consumers.LuantiEventConsumer.push_to_all_sync", _push
    )
    result = sc.prepare_luanti_shutdown(wait_seconds=0)
    assert pushed == []
    assert result["bridge_online"] is False
    assert result["sessions_requested"] == 1
    assert account.login_name in result["forced_end"]
    session.refresh_from_db()
    assert session.status == LuantiSession.STATUS_FINISHED


@pytest.mark.django_db
def test_prepare_shutdown_waits_for_leave_when_bridge_online(account, monkeypatch):
    from luanti.services import session_control as sc

    session = start_session(account=account, duration=20)
    monkeypatch.setattr(
        "luanti.services.bridge_connection.bridge_is_online", lambda server_id=None: True
    )
    pushed = []

    def _push(msg):
        pushed.append(msg)
        # Simulate bridge leave shortly after kick command.
        if msg.get("type") in ("SAVE_LEAVE_ALL", "KICK_PLAYER"):
            sc.end_session(session, inventory_payload=[{"name": "mcl_core:dirt", "count": 3}])
        return 1

    monkeypatch.setattr(
        "luanti.consumers.LuantiEventConsumer.push_to_all_sync", _push
    )
    result = sc.prepare_luanti_shutdown(wait_seconds=2)
    assert any(m.get("type") == "SAVE_LEAVE_ALL" for m in pushed)
    assert result["ok"] is True
    assert result["forced_end"] == []
    session.refresh_from_db()
    assert session.status == LuantiSession.STATUS_FINISHED
    from luanti.models import LuantiPlayerInventory

    inv = LuantiPlayerInventory.objects.get(account=account, mode="play")
    assert inv.payload == [{"name": "mcl_core:dirt", "count": 3}]


@pytest.mark.django_db
def test_reconcile_ends_orphaned_paused_session(account):
    session = start_session(account=account, duration=20)
    pause_session(session)
    ended = reconcile_sessions_with_online_players([])
    assert len(ended) == 1
    session.refresh_from_db()
    assert session.status == LuantiSession.STATUS_FINISHED


@pytest.mark.django_db
def test_reconcile_keeps_online_player_session(account):
    session = start_session(account=account, duration=20)
    pause_session(session)
    ended = reconcile_sessions_with_online_players([account.login_name])
    assert ended == []
    session.refresh_from_db()
    assert session.status == LuantiSession.STATUS_PAUSED


@pytest.mark.django_db
def test_reconcile_skipped_without_player_list(account):
    session = start_session(account=account, duration=20)
    assert reconcile_sessions_with_online_players(None) == []
    session.refresh_from_db()
    assert session.is_open


@pytest.mark.django_db
def test_warn_expiring_sessions_once(account, monkeypatch):
    from luanti.services import session_control as sc

    cfg = LuantiIntegrationConfig.get_config()
    cfg.session_end_warning_seconds = 90
    cfg.save(update_fields=["session_end_warning_seconds"])
    session = start_session(account=account, duration=20)
    session.ends_at = timezone.now() + timedelta(seconds=45)
    session.save(update_fields=["ends_at"])
    pushed = []

    def _push(msg):
        pushed.append(msg)
        return 1

    monkeypatch.setattr("luanti.consumers.LuantiEventConsumer.push_to_all_sync", _push)
    warned = sc.warn_expiring_sessions()
    assert len(warned) == 1
    assert pushed[0]["type"] == "SESSION_END_WARNING"
    assert pushed[0]["player"] == account.login_name
    assert pushed[0]["minutes"] >= 1
    session.refresh_from_db()
    assert session.end_warning_sent_at is not None
    # Second call must not spam.
    assert sc.warn_expiring_sessions() == []


@pytest.mark.django_db
def test_warn_disabled_when_zero(account, monkeypatch):
    from luanti.services import session_control as sc

    cfg = LuantiIntegrationConfig.get_config()
    cfg.session_end_warning_seconds = 0
    cfg.save(update_fields=["session_end_warning_seconds"])
    session = start_session(account=account, duration=20)
    session.ends_at = timezone.now() + timedelta(seconds=10)
    session.save(update_fields=["ends_at"])
    monkeypatch.setattr(
        "luanti.consumers.LuantiEventConsumer.push_to_all_sync",
        lambda msg: 1,
    )
    assert sc.warn_expiring_sessions() == []


@pytest.mark.django_db
def test_extend_clears_end_warning(account):
    session = start_session(account=account, duration=20)
    session.end_warning_sent_at = timezone.now()
    session.save(update_fields=["end_warning_sent_at"])
    extend_session(session, minutes=5)
    session.refresh_from_db()
    assert session.end_warning_sent_at is None


@pytest.mark.django_db
def test_config_fallback_bounds(db):
    cfg = LuantiIntegrationConfig.get_config()
    cfg.session_min_minutes = 7
    cfg.session_max_minutes = 40
    cfg.save()
    acc = LuantiAccount.objects.create(login_name="Kid2", id_tag="Kid2")
    assert resolve_duration_minutes(acc) == 40  # default 45 clamped to max 40


@pytest.mark.django_db
def test_clear_account_inventory_bumps_revision_and_pushes(account, monkeypatch):
    from luanti.models import LuantiPlayerInventory
    from luanti.services.session_control import clear_account_inventory, get_or_create_inventory

    session = start_session(account=account, duration=20)
    inv = get_or_create_inventory(account, "play")
    inv.payload = [{"name": "mcl_core:dirt", "count": 5}]
    inv.revision = 3
    inv.save(update_fields=["payload", "revision"])
    pushed = []
    monkeypatch.setattr(
        "luanti.consumers.LuantiEventConsumer.push_to_all_sync",
        lambda msg: pushed.append(msg) or 1,
    )
    clear_account_inventory(inv)
    inv.refresh_from_db()
    assert inv.payload == []
    assert inv.revision == 4
    assert any(m.get("type") == "CLEAR_INVENTORY" for m in pushed)
    payload = join_payload(account.login_name)
    assert payload["inventory"] == []
    assert payload["inventory_revision"] == 4
    assert session.pk  # session still open
