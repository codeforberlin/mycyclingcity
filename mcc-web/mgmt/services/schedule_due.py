# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    schedule_due.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

"""Helpers to decide whether a ScheduledJob is due."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from django.conf import settings
from django.utils import timezone

if TYPE_CHECKING:
    from mgmt.models_scheduler import ScheduledJob


def _aware_now(now: datetime | None = None) -> datetime:
    if now is None:
        return timezone.now()
    if timezone.is_naive(now):
        return timezone.make_aware(now, timezone.get_current_timezone())
    return now


def is_job_due(job: ScheduledJob, now: datetime | None = None) -> bool:
    """
    Return True if ``job`` should run at ``now``.

    Interval jobs run immediately when never started, then every N seconds.
    Cron jobs run when the previous fire time is newer than ``last_started_at``.
    On first enable, cron jobs only fire if the previous slot is within the
    configured grace window (avoids running all daily jobs on first tick).
    """
    now = _aware_now(now)
    if not job.enabled:
        return False

    if job.schedule_type == job.SCHEDULE_INTERVAL:
        return _is_interval_due(job, now)
    if job.schedule_type == job.SCHEDULE_CRON:
        return _is_cron_due(job, now)
    return False


def _is_interval_due(job: ScheduledJob, now: datetime) -> bool:
    interval = job.interval_seconds or 0
    if interval < 1:
        return False
    if job.last_started_at is None:
        return True
    elapsed = (now - job.last_started_at).total_seconds()
    return elapsed >= interval


def _is_cron_due(job: ScheduledJob, now: datetime) -> bool:
    expr = (job.cron_expression or "").strip()
    if not expr:
        return False
    try:
        from croniter import croniter
    except ImportError:
        return False
    if not croniter.is_valid(expr):
        return False

    # croniter works with naive or aware; keep timezone of ``now``.
    itr = croniter(expr, now)
    prev_fire = itr.get_prev(datetime)
    if timezone.is_aware(now) and timezone.is_naive(prev_fire):
        prev_fire = timezone.make_aware(prev_fire, timezone.get_current_timezone())
    elif timezone.is_naive(now) and timezone.is_aware(prev_fire):
        prev_fire = timezone.make_naive(prev_fire, timezone.get_current_timezone())

    grace = getattr(settings, "MCC_SCHEDULER_CRON_GRACE_SECONDS", 90)
    if job.last_started_at is None:
        return (now - prev_fire) <= timedelta(seconds=grace)

    return job.last_started_at < prev_fire
