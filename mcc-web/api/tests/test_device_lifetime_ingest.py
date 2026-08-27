# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import json
from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse


@pytest.mark.django_db
def test_update_data_increments_device_lifetime(api_key, complete_test_scenario):
    scenario = complete_test_scenario
    cyclist = scenario["cyclist"]
    device = scenario["device"]
    device.distance_total = Decimal("1.00000")
    device.distance_lifetime_km = Decimal("50.00000")
    device.save(update_fields=["distance_total", "distance_lifetime_km"])

    client = Client()
    resp = client.post(
        reverse("update_data"),
        data=json.dumps(
            {
                "id_tag": cyclist.id_tag,
                "device_id": device.name,
                "distance": "2.00000",
            }
        ),
        content_type="application/json",
        HTTP_X_API_KEY=api_key,
    )
    assert resp.status_code == 200, resp.content.decode()
    device.refresh_from_db()
    assert device.distance_total == Decimal("3.00000")
    assert device.distance_lifetime_km == Decimal("52.00000")
