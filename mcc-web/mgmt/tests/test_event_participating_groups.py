# Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    test_event_participating_groups.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

"""Saved event participant rows stay editable and deletable in admin."""

import re
from html.parser import HTMLParser

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from api.tests.conftest import EventFactory, GroupEventStatusFactory, GroupFactory
from eventboard.models import GroupEventStatus

User = get_user_model()


class _AdminFormParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.fields = {}
        self._select_name = None
        self._select_value = ""
        self._option_value = ""
        self._option_selected = False
        self._textarea_name = None
        self._textarea_data = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "input":
            name = attrs.get("name")
            if not name or attrs.get("type") in {"submit", "file", "button"}:
                return
            if attrs.get("type") == "checkbox":
                if "checked" in attrs:
                    self.fields[name] = attrs.get("value", "on")
                return
            self.fields[name] = attrs.get("value", "")
        elif tag == "select":
            self._select_name = attrs.get("name")
            self._select_value = ""
        elif tag == "option" and self._select_name:
            self._option_value = attrs.get("value", "")
            self._option_selected = "selected" in attrs
        elif tag == "textarea":
            self._textarea_name = attrs.get("name")
            self._textarea_data = []

    def handle_data(self, data):
        if self._textarea_name:
            self._textarea_data.append(data)

    def handle_endtag(self, tag):
        if tag == "option" and self._select_name and self._option_selected:
            self._select_value = self._option_value
        elif tag == "select" and self._select_name:
            self.fields[self._select_name] = self._select_value
            self._select_name = None
        elif tag == "textarea" and self._textarea_name:
            self.fields[self._textarea_name] = "".join(self._textarea_data)
            self._textarea_name = None


def _staff_client():
    user = User.objects.create_superuser(
        username="event-admin",
        email="event-admin@example.com",
        password="testpass123",
    )
    client = Client()
    client.force_login(user)
    return client


def _event_with_group():
    top = GroupFactory(name="Event Top School", parent=None)
    event = EventFactory(name="Editable Groups Event", top_group=top)
    assigned = GroupFactory(name="Class Already In", parent=top)
    other = GroupFactory(name="Class Not Yet In", parent=top)
    status = GroupEventStatusFactory(
        event=event,
        group=assigned,
        current_velos=12,
    )
    return event, status, assigned, other


def _change_page(client, event):
    url = reverse("admin:eventboard_event_change", args=[event.pk])
    response = client.get(url)
    assert response.status_code == 200
    return url, response.content.decode()


def _post_data(html):
    parser = _AdminFormParser()
    parser.feed(html)
    data = parser.fields
    data["_save"] = "Save"
    return data


def _row_prefix(html):
    match = re.search(r'name="([a-z0-9_]+)-0-group"', html)
    assert match, "participating group field missing"
    return match.group(1)


@pytest.mark.django_db
def test_saved_participating_group_select_stays_enabled():
    client = _staff_client()
    event, status, assigned, other = _event_with_group()
    _url, html = _change_page(client, event)
    prefix = _row_prefix(html)

    match = re.search(
        rf'<select[^>]*name="{prefix}-0-group"[^>]*>.*?</select>',
        html,
        re.S,
    )
    assert match, "participating group select missing"
    opening = match.group(0).split(">", 1)[0]
    assert "disabled" not in opening
    assert "readonly-group-field" not in html
    assert f'value="{assigned.pk}"' in match.group(0)
    assert f'value="{other.pk}"' in match.group(0)
    assert f'name="{prefix}-0-id" value="{status.pk}"' in html
    assert "firstCell.innerHTML" not in html


@pytest.mark.django_db
def test_saved_participating_group_can_be_changed():
    client = _staff_client()
    event, status, _assigned, other = _event_with_group()
    url, html = _change_page(client, event)
    prefix = _row_prefix(html)
    data = _post_data(html)
    data[f"{prefix}-0-group"] = str(other.pk)

    response = client.post(url, data)
    assert response.status_code == 302, response.content.decode()[:3000]

    status.refresh_from_db()
    assert status.group_id == other.pk
    assert status.current_velos == 12
    assert GroupEventStatus.objects.filter(event=event).count() == 1


@pytest.mark.django_db
def test_saved_participating_group_can_be_deleted():
    client = _staff_client()
    event, status, _assigned, _other = _event_with_group()
    url, html = _change_page(client, event)
    prefix = _row_prefix(html)
    data = _post_data(html)
    data[f"{prefix}-0-DELETE"] = "on"

    response = client.post(url, data)
    assert response.status_code == 302, response.content.decode()[:3000]
    assert not GroupEventStatus.objects.filter(pk=status.pk).exists()
    assert not GroupEventStatus.objects.filter(event=event).exists()
