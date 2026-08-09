# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    views.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

"""Views for the public dynamo energy visualization."""

import json
from typing import Optional

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _

from dynamo.models import DynamoDisplaySettings
from dynamo.physics import CHARGER_PROFILE_DIRECT, normalize_charger_profile
from dynamo.services import build_live_payload, resolve_top_group_filter


def _parse_ride_stats_flag(request: HttpRequest) -> Optional[bool]:
    """Parse ?ride_stats=0|1|true|false; None means use admin default."""
    raw = request.GET.get('ride_stats')
    if raw is None or raw == '':
        return None
    value = raw.strip().lower()
    if value in ('1', 'true', 'yes', 'on'):
        return True
    if value in ('0', 'false', 'no', 'off'):
        return False
    return None


def _parse_charger_profile(request: HttpRequest) -> str:
    """Parse ?charger=direct|simple|standard|optimized."""
    return normalize_charger_profile(request.GET.get('charger') or CHARGER_PROFILE_DIRECT)


def dynamo_page(request: HttpRequest) -> HttpResponse:
    """
    Public dynamo energy display.

    Query parameters:
    - group: TOP or leaf group name (case-insensitive); scopes history + live data
    - period: session|day|week|year
    - view: all|cyclist — scope totals/batteries/appliances to all riders or one cyclist
    - cyclist: id_tag when view=cyclist
    - ride_stats: 1|0 to show/hide session Velos and km on cyclist tiles
    - charger: direct|simple|standard|optimized (profi usable-power model)
    - compare: 1 to open the charger comparison panel (otherwise hidden)
    """
    group_name = request.GET.get('group')
    filter_group, _group_ids = resolve_top_group_filter(group_name)
    settings_obj = DynamoDisplaySettings.get_settings()
    ride_stats = _parse_ride_stats_flag(request)
    charger = _parse_charger_profile(request)
    payload = build_live_payload(
        group_name,
        show_cyclist_ride_stats=ride_stats,
        charger_profile=charger,
    )

    is_kiosk = (
        request.GET.get('kiosk') == 'true'
        or 'kiosk/playlist' in request.META.get('HTTP_REFERER', '')
    )

    context = {
        'title': _('Dynamo – Energie aus dem Rad'),
        'current_filter': filter_group.name if filter_group else group_name,
        'filter_group': filter_group,
        'update_interval_seconds': settings_obj.update_interval_seconds,
        'is_kiosk': is_kiosk,
        'show_cyclist_ride_stats': payload['show_cyclist_ride_stats'],
        'enable_charger_compare': payload['enable_charger_compare'],
        'charger_profile': payload['charger_profile'],
        'initial_data_json': mark_safe(json.dumps(payload)),
    }
    return render(request, 'dynamo/dynamo_page.html', context)


def dynamo_live_api(request: HttpRequest) -> JsonResponse:
    """JSON live payload for polling (HTMX/fetch)."""
    group_name = request.GET.get('group')
    ride_stats = _parse_ride_stats_flag(request)
    charger = _parse_charger_profile(request)
    payload = build_live_payload(
        group_name,
        show_cyclist_ride_stats=ride_stats,
        charger_profile=charger,
    )
    return JsonResponse(payload)


def dynamo_history_partial(request: HttpRequest) -> HttpResponse:
    """HTML partial for day/week history charts."""
    group_name = request.GET.get('group')
    payload = build_live_payload(group_name)
    return render(
        request,
        'dynamo/partials/history.html',
        {
            'history': payload['history'],
            'totals': payload['totals'],
            'current_filter': payload.get('filter_group'),
        },
    )
