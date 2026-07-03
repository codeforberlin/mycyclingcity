# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Persist CyclistDeviceCurrentMileage to HourlyMetric before session end.
# Logic aligned with mcc_worker.cleanup_expired_sessions.

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from django.db.models import Sum
from django.utils import timezone

from api.models import CyclistDeviceCurrentMileage, HourlyMetric
from config.logger_utils import get_logger

logger = get_logger(__name__)


def persist_session_to_hourly_metric(
    sess: CyclistDeviceCurrentMileage,
    *,
    reference_time: Optional[timezone.datetime] = None,
) -> bool:
    """
    Write session distance to HourlyMetric if applicable.

    Returns True if a metric was created or updated.
    """
    if not sess.cumulative_mileage or sess.cumulative_mileage <= 0:
        return False

    ref = reference_time or sess.last_activity or timezone.now()
    primary_group = sess.cyclist.groups.first()
    hour_timestamp = ref.replace(minute=0, second=0, microsecond=0)

    existing_metric = HourlyMetric.objects.filter(
        cyclist=sess.cyclist,
        device=sess.device,
        timestamp=hour_timestamp,
    ).first()

    session_start_hour = sess.start_time.replace(minute=0, second=0, microsecond=0)
    session_started_in_current_hour = session_start_hour == hour_timestamp

    if session_started_in_current_hour:
        hourly_distance = sess.cumulative_mileage
    else:
        mileage_at_hour_start = HourlyMetric.objects.filter(
            cyclist=sess.cyclist,
            device=sess.device,
            timestamp__lt=hour_timestamp,
        ).aggregate(total=Sum('distance_km'))['total'] or Decimal('0.00000')

        mileage_at_session_start = HourlyMetric.objects.filter(
            cyclist=sess.cyclist,
            device=sess.device,
            timestamp__lt=session_start_hour,
        ).aggregate(total=Sum('distance_km'))['total'] or Decimal('0.00000')

        total_distance_now = mileage_at_session_start + sess.cumulative_mileage
        hourly_distance = total_distance_now - mileage_at_hour_start

    if existing_metric and session_started_in_current_hour:
        session_already_processed = (
            existing_metric.last_session_start_time is not None
            and sess.start_time == existing_metric.last_session_start_time
        )

        if hourly_distance < existing_metric.distance_km:
            if session_already_processed:
                return False
            existing_metric.distance_km += hourly_distance
            existing_metric.last_session_start_time = sess.start_time
            existing_metric.last_session_distance_km = hourly_distance
            existing_metric.save()
            return True

        if hourly_distance > existing_metric.distance_km:
            if session_already_processed:
                if existing_metric.last_session_distance_km is not None:
                    distance_delta = hourly_distance - existing_metric.last_session_distance_km
                else:
                    distance_delta = hourly_distance - existing_metric.distance_km
                existing_metric.distance_km += distance_delta
                existing_metric.last_session_distance_km = hourly_distance
                existing_metric.last_session_start_time = sess.start_time
                existing_metric.save()
                return True
            existing_metric.distance_km = hourly_distance
            existing_metric.last_session_start_time = sess.start_time
            existing_metric.last_session_distance_km = hourly_distance
            existing_metric.save()
            return True

        if session_already_processed:
            if (
                existing_metric.last_session_distance_km is not None
                and hourly_distance > existing_metric.last_session_distance_km
            ):
                distance_delta = hourly_distance - existing_metric.last_session_distance_km
                existing_metric.distance_km += distance_delta
                existing_metric.last_session_distance_km = hourly_distance
                existing_metric.save()
                return True
            return False

        existing_metric.last_session_start_time = sess.start_time
        existing_metric.last_session_distance_km = hourly_distance
        existing_metric.save()
        return False

    if existing_metric and not session_started_in_current_hour:
        if hourly_distance <= existing_metric.distance_km:
            return False

    if hourly_distance <= 0:
        logger.warning(
            "Hourly distance is %s for session %s, skipping flush",
            hourly_distance,
            sess.cyclist.user_id,
        )
        return False

    if existing_metric:
        if hourly_distance > existing_metric.distance_km:
            existing_metric.distance_km = hourly_distance
            existing_metric.last_session_start_time = sess.start_time
            existing_metric.last_session_distance_km = hourly_distance
            existing_metric.save()
            return True
        return False

    HourlyMetric.objects.create(
        cyclist=sess.cyclist,
        device=sess.device,
        timestamp=hour_timestamp,
        distance_km=hourly_distance,
        group_at_time=primary_group,
        last_session_start_time=sess.start_time,
        last_session_distance_km=hourly_distance,
    )
    return True
