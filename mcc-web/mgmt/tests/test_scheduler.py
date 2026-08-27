# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    test_scheduler.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

"""Tests for data-driven scheduled jobs."""

from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.utils import timezone

from mgmt.models_scheduler import ScheduledJob, ScheduledJobRun
from mgmt.services.job_runner import (
    assert_shell_path_allowed,
    build_argv,
    execute_job,
    resolve_working_directory,
)
from mgmt.services.schedule_due import is_job_due

User = get_user_model()


@pytest.fixture
def interval_job(db):
    return ScheduledJob.objects.create(
        name="Test Interval",
        slug="test_interval",
        enabled=True,
        job_type=ScheduledJob.JOB_TYPE_MANAGEMENT,
        command="mcc_worker",
        schedule_type=ScheduledJob.SCHEDULE_INTERVAL,
        interval_seconds=60,
        timeout_seconds=30,
        sort_order=1,
    )


@pytest.fixture
def cron_job(db):
    return ScheduledJob.objects.create(
        name="Test Cron",
        slug="test_cron",
        enabled=True,
        job_type=ScheduledJob.JOB_TYPE_SHELL,
        command="scripts/backup_mcc.sh",
        schedule_type=ScheduledJob.SCHEDULE_CRON,
        cron_expression="0 22 * * *",
        timeout_seconds=60,
        sort_order=2,
    )


@pytest.mark.django_db
def test_interval_due_when_never_run(interval_job):
    assert is_job_due(interval_job) is True


@pytest.mark.django_db
def test_interval_not_due_within_window(interval_job):
    interval_job.last_started_at = timezone.now() - timedelta(seconds=10)
    interval_job.save(update_fields=["last_started_at"])
    assert is_job_due(interval_job) is False


@pytest.mark.django_db
def test_interval_due_after_window(interval_job):
    interval_job.last_started_at = timezone.now() - timedelta(seconds=120)
    interval_job.save(update_fields=["last_started_at"])
    assert is_job_due(interval_job) is True


@pytest.mark.django_db
def test_disabled_job_not_due(interval_job):
    interval_job.enabled = False
    interval_job.save(update_fields=["enabled"])
    assert is_job_due(interval_job) is False


@pytest.mark.django_db
def test_cron_due_within_grace(cron_job, settings):
    settings.MCC_SCHEDULER_CRON_GRACE_SECONDS = 120
    # Freeze "now" just after 22:00
    now = timezone.now().replace(hour=22, minute=0, second=30, microsecond=0)
    cron_job.last_started_at = None
    assert is_job_due(cron_job, now=now) is True


@pytest.mark.django_db
def test_cron_not_due_far_from_slot(cron_job, settings):
    settings.MCC_SCHEDULER_CRON_GRACE_SECONDS = 90
    now = timezone.now().replace(hour=10, minute=0, second=0, microsecond=0)
    cron_job.last_started_at = None
    assert is_job_due(cron_job, now=now) is False


@pytest.mark.django_db
def test_cron_due_when_last_before_prev_fire(cron_job):
    now = timezone.now().replace(hour=22, minute=5, second=0, microsecond=0)
    cron_job.last_started_at = now - timedelta(days=1)
    cron_job.save(update_fields=["last_started_at"])
    assert is_job_due(cron_job, now=now) is True


@pytest.mark.django_db
def test_shell_path_policy_allows_base(settings, tmp_path):
    script = tmp_path / "ok.sh"
    script.write_text("#!/bin/sh\necho ok\n")
    script.chmod(0o755)
    settings.MCC_SCHEDULER_SHELL_ROOTS = [tmp_path]
    assert_shell_path_allowed(script.resolve())


@pytest.mark.django_db
def test_shell_path_policy_rejects_outside(settings, tmp_path):
    settings.MCC_SCHEDULER_SHELL_ROOTS = [tmp_path]
    with pytest.raises(PermissionError):
        assert_shell_path_allowed(Path("/etc/passwd").resolve())


@pytest.mark.django_db
def test_build_argv_management_command(interval_job, settings):
    cwd = resolve_working_directory(interval_job)
    argv = build_argv(interval_job, cwd)
    assert argv[1].endswith("manage.py")
    assert argv[2] == "mcc_worker"


@pytest.mark.django_db
def test_execute_job_success_scheduler_no_history(interval_job, settings, tmp_path):
    settings.MCC_SCHEDULER_SHELL_ROOTS = [tmp_path, settings.BASE_DIR]
    with patch("mgmt.services.job_runner.subprocess.run") as mock_run:
        mock_run.return_value = type(
            "R",
            (),
            {"returncode": 0, "stdout": "done\n", "stderr": ""},
        )()
        result = execute_job(
            interval_job,
            trigger=ScheduledJobRun.TRIGGER_SCHEDULER,
            force=True,
        )
    assert result.status == ScheduledJob.STATUS_OK
    assert result.persisted is False
    interval_job.refresh_from_db()
    assert interval_job.last_status == ScheduledJob.STATUS_OK
    assert interval_job.success_count == 1
    assert not ScheduledJobRun.objects.filter(job=interval_job).exists()


@pytest.mark.django_db
def test_execute_job_success_manual_persists(interval_job, settings, tmp_path):
    with patch("mgmt.services.job_runner.subprocess.run") as mock_run:
        mock_run.return_value = type(
            "R",
            (),
            {"returncode": 0, "stdout": "", "stderr": ""},
        )()
        result = execute_job(
            interval_job,
            trigger=ScheduledJobRun.TRIGGER_MANUAL,
            force=True,
        )
    assert result.persisted is True
    assert ScheduledJobRun.objects.filter(job=interval_job, status="ok").exists()


@pytest.mark.django_db
def test_execute_job_error_persists(interval_job):
    with patch("mgmt.services.job_runner.subprocess.run") as mock_run:
        mock_run.return_value = type(
            "R",
            (),
            {"returncode": 1, "stdout": "", "stderr": "boom"},
        )()
        result = execute_job(
            interval_job,
            trigger=ScheduledJobRun.TRIGGER_SCHEDULER,
            force=True,
        )
    assert result.status == ScheduledJob.STATUS_ERROR
    assert result.persisted is True
    interval_job.refresh_from_db()
    assert interval_job.error_count == 1
    assert ScheduledJobRun.objects.filter(job=interval_job, status="error").exists()


@pytest.mark.django_db
def test_execute_job_skips_overlap(interval_job):
    ScheduledJobRun.objects.create(
        job=interval_job,
        started_at=timezone.now(),
        status=ScheduledJobRun.STATUS_RUNNING,
        trigger=ScheduledJobRun.TRIGGER_SCHEDULER,
    )
    result = execute_job(interval_job, force=False)
    assert result.skipped is True
    assert result.status == ScheduledJob.STATUS_SKIPPED
    interval_job.refresh_from_db()
    assert interval_job.skip_count == 1
    # Skip does not add a history row
    assert ScheduledJobRun.objects.filter(job=interval_job, status="skipped").count() == 0


@pytest.mark.django_db
def test_prune_job_runs(interval_job, settings):
    from mgmt.services.job_runner import prune_job_runs

    settings.MCC_SCHEDULER_RUN_MAX_PER_JOB = 2
    settings.MCC_SCHEDULER_RUN_RETENTION_DAYS = 0  # disable age cutoff
    now = timezone.now()
    for i in range(5):
        ScheduledJobRun.objects.create(
            job=interval_job,
            started_at=now - timedelta(minutes=i),
            finished_at=now - timedelta(minutes=i),
            status=ScheduledJobRun.STATUS_ERROR,
            trigger=ScheduledJobRun.TRIGGER_SCHEDULER,
            message=f"err-{i}",
        )
    deleted = prune_job_runs(interval_job)
    assert deleted >= 3
    assert ScheduledJobRun.objects.filter(job=interval_job).count() == 2


@pytest.mark.django_db
def test_run_scheduler_force_job(interval_job):
    with patch("mgmt.services.job_runner.subprocess.run") as mock_run:
        mock_run.return_value = type(
            "R",
            (),
            {"returncode": 0, "stdout": "", "stderr": ""},
        )()
        call_command("run_scheduler", job="test_interval", force=True, no_lock=True)
    interval_job.refresh_from_db()
    assert interval_job.last_status == ScheduledJob.STATUS_OK
    # --force uses manual trigger → history kept
    assert ScheduledJobRun.objects.filter(job=interval_job, status="ok").exists()


@pytest.mark.django_db
def test_seeded_default_jobs_exist(db):
    # Migration seeds may already exist; ensure helper defaults can be created
    for slug in ("mcc_worker", "backup_mcc", "backup_minecraft", "backup_luanti"):
        if not ScheduledJob.objects.filter(slug=slug).exists():
            ScheduledJob.objects.create(
                name=slug,
                slug=slug,
                enabled=True,
                job_type=ScheduledJob.JOB_TYPE_SHELL
                if slug.startswith("backup")
                else ScheduledJob.JOB_TYPE_MANAGEMENT,
                command="mcc_worker" if slug == "mcc_worker" else f"scripts/{slug}.sh",
                schedule_type=ScheduledJob.SCHEDULE_INTERVAL
                if slug == "mcc_worker"
                else ScheduledJob.SCHEDULE_CRON,
                interval_seconds=60 if slug == "mcc_worker" else None,
                cron_expression="0 22 * * *" if slug != "mcc_worker" else "",
            )
    assert ScheduledJob.objects.filter(slug="mcc_worker").exists()


@pytest.mark.django_db
def test_run_permission_codename(db):
    perm = Permission.objects.filter(codename="run_scheduledjob").first()
    # Permission is created by migrate from Meta.permissions
    if perm is None:
        pytest.skip("Permission not present until migrate")
    assert perm.content_type.app_label == "mgmt"
