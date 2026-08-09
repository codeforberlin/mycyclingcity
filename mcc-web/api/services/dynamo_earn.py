# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Apply virtual hub-dynamo energy earnings on device distance updates.

from __future__ import annotations

from decimal import Decimal
from typing import Union

from django.db.models import F
from django.utils import timezone

from api.models import HourlyMetric
from api.velos import get_radumfang_mm
from config.logger_utils import get_logger
from dynamo.physics import (
    DEFAULT_POWER_CAP_W,
    DEFAULT_POWER_CURVE,
    compute_interval_energy,
    parse_power_curve,
    resolve_interval_seconds,
)

logger = get_logger(__name__)


def _load_dynamo_curve_and_cap():
    """Load power curve and cap from DynamoDisplaySettings when available."""
    try:
        from dynamo.models import DynamoDisplaySettings

        settings_obj = DynamoDisplaySettings.get_settings()
        curve = parse_power_curve(settings_obj.power_curve or [])
        cap = float(settings_obj.power_cap_w or DEFAULT_POWER_CAP_W)
        return curve, cap
    except Exception:
        return DEFAULT_POWER_CURVE, DEFAULT_POWER_CAP_W


def _device_send_interval_s(device) -> float:
    try:
        return float(device.configuration.send_interval_seconds)
    except Exception:
        return 60.0


def apply_dynamo_earn(
    session,
    device,
    distance_delta: Union[Decimal, float, int],
    *,
    previous_last_activity=None,
) -> Decimal:
    """
    Credit virtual dynamo energy for one distance update.

    Updates session power/RPM/energy fields and increments HourlyMetric.energy_wh
    for the current hour. Returns Wh credited (0 if skipped).
    """
    if distance_delta is None or distance_delta <= 0:
        return Decimal('0.00000')

    if getattr(device, 'is_operator_box', False):
        logger.debug("[apply_dynamo_earn] Skipping operator box device %s", device.name)
        return Decimal('0.00000')

    configured_interval = _device_send_interval_s(device)
    elapsed_s = None
    if previous_last_activity is not None:
        elapsed_s = (timezone.now() - previous_last_activity).total_seconds()

    interval_s = resolve_interval_seconds(configured_interval, elapsed_s)
    wheel_mm = get_radumfang_mm(device)
    curve, power_cap = _load_dynamo_curve_and_cap()

    metrics = compute_interval_energy(
        distance_delta,
        interval_s,
        wheel_mm,
        curve=curve,
        power_cap_w=power_cap,
    )
    energy_wh = Decimal(str(round(metrics.energy_wh, 5)))
    if energy_wh <= 0:
        session.last_power_w = 0.0
        session.last_rpm = 0.0
        session.last_speed_kmh = 0.0
        return Decimal('0.00000')

    session.session_energy_wh = (session.session_energy_wh or Decimal('0')) + energy_wh
    session.last_power_w = float(metrics.power_w)
    session.last_rpm = float(metrics.rpm)
    session.last_speed_kmh = float(metrics.speed_kmh)

    _add_energy_to_hourly_metric(session, device, energy_wh)

    logger.debug(
        "[apply_dynamo_earn] +%s Wh for %s (%.2f W, %.0f rpm)",
        energy_wh,
        session.cyclist.id_tag,
        metrics.power_w,
        metrics.rpm,
    )
    return energy_wh


def _add_energy_to_hourly_metric(session, device, energy_wh: Decimal) -> None:
    """Increment HourlyMetric.energy_wh for the current hour (create if needed)."""
    now = timezone.now()
    hour_timestamp = now.replace(minute=0, second=0, microsecond=0)
    primary_group = session.cyclist.groups.first()

    metric, created = HourlyMetric.objects.get_or_create(
        cyclist=session.cyclist,
        device=device,
        timestamp=hour_timestamp,
        defaults={
            'distance_km': Decimal('0.00000'),
            'group_at_time': primary_group,
            'energy_wh': energy_wh,
            'last_session_start_time': session.start_time,
            'last_session_distance_km': session.cumulative_mileage,
        },
    )
    if created:
        return

    HourlyMetric.objects.filter(pk=metric.pk).update(
        energy_wh=F('energy_wh') + energy_wh,
    )
