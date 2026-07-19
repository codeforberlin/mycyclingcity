# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import ipaddress

from django.conf import settings

LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
ALL_INTERFACE_BINDS = frozenset({"0.0.0.0", "::"})


def _is_ip_address(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def _is_private_ip(host: str) -> bool:
    if not _is_ip_address(host):
        return False
    return ipaddress.ip_address(host).is_private


def _public_allowed_hosts(allowed_hosts: list[str] | tuple[str, ...]) -> list[str]:
    hosts: list[str] = []
    for host in allowed_hosts:
        normalized = host.strip()
        if not normalized or normalized in LOCAL_HOSTS:
            continue
        hosts.append(normalized)
    return hosts


def _partition_hosts(candidates: list[str]) -> tuple[list[str], list[str], list[str]]:
    private_ips: list[str] = []
    other_ips: list[str] = []
    dns_names: list[str] = []
    for host in candidates:
        if _is_private_ip(host):
            private_ips.append(host)
        elif _is_ip_address(host):
            other_ips.append(host)
        else:
            dns_names.append(host)
    return private_ips, other_ips, dns_names


def resolve_ws_url_host(bind_host: str | None, allowed_hosts: list[str] | tuple[str, ...]) -> str:
    """
    Host for MCC-Bridge WebSocket config.

    MCC_MINECRAFT_WS_BIND_HOST is only Daphne's listen address. Public DNS from
    ALLOWED_HOSTS must not be used when Daphne binds to loopback only.
    """
    public_override = getattr(settings, "MCC_MINECRAFT_WS_PUBLIC_HOST", "") or ""
    public_override = public_override.strip()
    if public_override:
        return public_override

    bind_host = (bind_host or "").strip()
    if bind_host and bind_host not in LOCAL_HOSTS and bind_host not in ALL_INTERFACE_BINDS:
        return bind_host

    private_ips, other_ips, dns_names = _partition_hosts(_public_allowed_hosts(allowed_hosts))

    if bind_host in LOCAL_HOSTS:
        if private_ips:
            return private_ips[0]
        return "127.0.0.1"

    if private_ips:
        return private_ips[0]
    if other_ips:
        return other_ips[0]
    if dns_names:
        return dns_names[0]

    return "127.0.0.1"


def build_ws_events_url() -> str:
    """WebSocket URL for MCC-Bridge plugin configuration."""
    host = resolve_ws_url_host(
        settings.MCC_MINECRAFT_WS_BIND_HOST,
        settings.ALLOWED_HOSTS,
    )
    port = settings.MCC_MINECRAFT_WS_PORT or 8002
    return f"ws://{host}:{port}/ws/minecraft/events"
