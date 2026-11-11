# Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
# SPDX-License-Identifier: AGPL-3.0-or-later

import pytest

from api.tests.conftest import CyclistFactory, GroupFactory


@pytest.mark.django_db
def test_group_save_velos_spendable_skips_missing_logo_file():
    group = GroupFactory(name="LogoMissingVelosSave")
    group.logo = "group_logos/nonexistent-broken-logo.png"
    group.save(update_fields=["logo"])
    group.velos_spendable = 5
    group.save(update_fields=["velos_spendable"])
    group.refresh_from_db()
    assert group.velos_spendable == 5


@pytest.mark.django_db
def test_cyclist_save_velos_balance_skips_missing_avatar_file():
    cyclist = CyclistFactory(user_id="avatar_missing_velos")
    cyclist.avatar = "player_avatars/nonexistent-broken-avatar.png"
    cyclist.save(update_fields=["avatar"])
    cyclist.velos_balance = 12
    cyclist.save(update_fields=["velos_balance"])
    cyclist.refresh_from_db()
    assert cyclist.velos_balance == 12
