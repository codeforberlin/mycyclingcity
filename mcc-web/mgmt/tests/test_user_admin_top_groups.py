# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for User admin TOP-group display."""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from api.tests.conftest import GroupFactory
from mgmt.admin import _managed_top_groups_for_user

User = get_user_model()


@pytest.mark.django_db
def test_managed_top_groups_resolves_leaf_to_top():
    top = GroupFactory(name="Alpha TOP", parent=None)
    leaf = GroupFactory(name="Leaf", parent=top)
    user = User.objects.create_user(username="op1", password="x")
    leaf.managers.add(user)

    tops = _managed_top_groups_for_user(user)
    assert [g.pk for g in tops] == [top.pk]


@pytest.mark.django_db
def test_managed_top_groups_dedupes_multiple_assignments():
    top = GroupFactory(name="Beta TOP", parent=None)
    leaf = GroupFactory(name="Leaf B", parent=top)
    user = User.objects.create_user(username="op2", password="x")
    top.managers.add(user)
    leaf.managers.add(user)

    tops = _managed_top_groups_for_user(user)
    assert [g.pk for g in tops] == [top.pk]


@pytest.mark.django_db
def test_user_changelist_shows_top_groups(client):
    top_a = GroupFactory(name="Campus A", parent=None)
    top_b = GroupFactory(name="Campus B", parent=None)
    user = User.objects.create_user(username="op3", password="x", is_staff=True)
    top_a.managers.add(user)
    top_b.managers.add(user)

    admin = User.objects.create_superuser(username="su", password="x", email="su@example.com")
    client.force_login(admin)
    resp = client.get(reverse("admin:auth_user_changelist"))
    assert resp.status_code == 200
    body = resp.content.decode("utf-8")
    assert "Campus A" in body
    assert "Campus B" in body
    assert "TOP-Gruppen" in body


@pytest.mark.django_db
def test_user_change_form_shows_top_groups_section(client):
    top = GroupFactory(name="Campus C", parent=None)
    user = User.objects.create_user(username="op4", password="x", is_staff=True)
    top.managers.add(user)

    admin = User.objects.create_superuser(username="su2", password="x", email="su2@example.com")
    client.force_login(admin)
    resp = client.get(reverse("admin:auth_user_change", args=[user.pk]))
    assert resp.status_code == 200
    body = resp.content.decode("utf-8")
    assert "Campus C" in body
    assert "TOP-Gruppen" in body
