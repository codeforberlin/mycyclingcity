# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

import pytest
from django.test import override_settings

from minecraft.services.ws_url import build_ws_events_url, resolve_ws_url_host


@pytest.mark.unit
class TestWsUrl:
    def test_loopback_bind_uses_private_ip_from_allowed_hosts(self):
        host = resolve_ws_url_host(
            "127.0.0.1",
            ["mycyclingcity.net", "127.0.0.1", "192.168.90.2"],
        )
        assert host == "192.168.90.2"

    def test_loopback_bind_without_lan_ip_uses_localhost(self):
        host = resolve_ws_url_host(
            "127.0.0.1",
            ["mycyclingcity.net", "127.0.0.1"],
        )
        assert host == "127.0.0.1"

    def test_all_interfaces_bind_uses_private_ip(self):
        host = resolve_ws_url_host(
            "0.0.0.0",
            ["mycyclingcity.de", "192.168.90.2"],
        )
        assert host == "192.168.90.2"

    def test_all_interfaces_bind_falls_back_to_dns(self):
        host = resolve_ws_url_host(
            "0.0.0.0",
            ["mycyclingcity.de", "127.0.0.1"],
        )
        assert host == "mycyclingcity.de"

    def test_public_bind_uses_bind_host(self):
        host = resolve_ws_url_host(
            "192.168.90.2",
            ["mycyclingcity.de"],
        )
        assert host == "192.168.90.2"

    @override_settings(
        MCC_MINECRAFT_WS_BIND_HOST="127.0.0.1",
        MCC_MINECRAFT_WS_PORT=8002,
        ALLOWED_HOSTS=["mycyclingcity.net", "127.0.0.1"],
        MCC_MINECRAFT_WS_PUBLIC_HOST="",
    )
    def test_build_ws_events_url_loopback_without_lan_ip(self):
        assert build_ws_events_url() == "ws://127.0.0.1:8002/ws/minecraft/events"

    @override_settings(
        MCC_MINECRAFT_WS_BIND_HOST="127.0.0.1",
        MCC_MINECRAFT_WS_PORT=8002,
        ALLOWED_HOSTS=["mycyclingcity.de", "127.0.0.1", "192.168.90.2"],
        MCC_MINECRAFT_WS_PUBLIC_HOST="",
    )
    def test_build_ws_events_url_loopback_with_lan_ip(self):
        assert build_ws_events_url() == "ws://192.168.90.2:8002/ws/minecraft/events"

    @override_settings(
        MCC_MINECRAFT_WS_BIND_HOST="127.0.0.1",
        MCC_MINECRAFT_WS_PORT=8002,
        ALLOWED_HOSTS=["mycyclingcity.de"],
        MCC_MINECRAFT_WS_PUBLIC_HOST="10.0.0.5",
    )
    def test_public_host_override(self):
        assert build_ws_events_url() == "ws://10.0.0.5:8002/ws/minecraft/events"
