# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_csrf_failure_returns_json_for_ajax(client):
    client.handler.enforce_csrf_checks = True
    url = reverse("admin:minecraft_builder_sessions") + "?format=json"
    response = client.post(
        url,
        {"action": "start", "account": "Dynamo"},
        HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        HTTP_ACCEPT="application/json",
    )
    assert response.status_code == 403
    assert response.headers.get("Content-Type", "").startswith("application/json")
    data = response.json()
    assert data["ok"] is False
    assert "CSRF" in data["message"]


@pytest.mark.django_db
def test_csrf_failure_html_for_normal_browser_post(client):
    client.handler.enforce_csrf_checks = True
    url = reverse("admin:minecraft_builder_sessions")
    response = client.post(url, {"action": "start", "account": "Dynamo"})
    assert response.status_code == 403
    assert b"CSRF" in response.content or b"Forbidden" in response.content
    assert not response.headers.get("Content-Type", "").startswith("application/json")
