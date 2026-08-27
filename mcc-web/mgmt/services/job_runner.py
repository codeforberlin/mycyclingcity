# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    job_runner.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

"""Execute ScheduledJob definitions (management commands or shell scripts)."""

from __future__ import annotations

import fcntl
import logging
import os
import shlex
import subprocess
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Iterator, Optional

from django.conf import settings
from django.core.management import get_commands
from django.db.models import F
from django.utils import timezone

from mgmt.models_scheduler import ScheduledJob, ScheduledJobRun

logger = logging.getLogger(__name__)


@dataclass
class JobRunResult:
    status: str
    exit_code: Optional[int] = None
    message: str = ""
    stdout_excerpt: str = ""
    stderr_excerpt: str = ""
    skipped: bool = False
    persisted: bool = False


def _truncate(text: str, max_chars: int) -> str:
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    half = max_chars // 2
    return text[:half] + "\n… [truncated] …\n" + text[-half:]


def get_shell_allowed_roots() -> list[Path]:
    roots = getattr(settings, "MCC_SCHEDULER_SHELL_ROOTS", None)
    if not roots:
        roots = [
            settings.BASE_DIR,
            getattr(settings, "APP_DIR", settings.BASE_DIR),
            getattr(settings, "DATA_DIR", settings.BASE_DIR),
        ]
    resolved = []
    for root in roots:
        try:
            resolved.append(Path(root).resolve())
        except OSError:
            continue
    return resolved


def resolve_working_directory(job: ScheduledJob) -> Path:
    if job.working_directory and job.working_directory.strip():
        cwd = Path(job.working_directory.strip())
        if not cwd.is_absolute():
            cwd = Path(settings.BASE_DIR) / cwd
        return cwd.resolve()
    return Path(settings.BASE_DIR).resolve()


def resolve_shell_command_path(command: str, cwd: Path) -> Path:
    path = Path(command.strip())
    if not path.is_absolute():
        path = cwd / path
    return path.resolve()


def assert_shell_path_allowed(command_path: Path) -> None:
    roots = get_shell_allowed_roots()
    for root in roots:
        try:
            command_path.relative_to(root)
            return
        except ValueError:
            continue
    raise PermissionError(
        f"Shell command path {command_path} is outside allowed roots: "
        + ", ".join(str(r) for r in roots)
    )


def build_argv(job: ScheduledJob, cwd: Path) -> list[str]:
    args = shlex.split(job.arguments or "", posix=True)
    if job.job_type == ScheduledJob.JOB_TYPE_MANAGEMENT:
        command_name = job.command.strip()
        known = get_commands()
        if command_name not in known:
            raise ValueError(f"Unknown management command: {command_name}")
        manage_py = Path(settings.BASE_DIR) / "manage.py"
        return [sys.executable, str(manage_py), command_name, *args]

    if job.job_type == ScheduledJob.JOB_TYPE_SHELL:
        command_path = resolve_shell_command_path(job.command, cwd)
        assert_shell_path_allowed(command_path)
        if not command_path.exists():
            raise FileNotFoundError(f"Shell command not found: {command_path}")
        if not os.access(command_path, os.X_OK):
            raise PermissionError(f"Shell command is not executable: {command_path}")
        return [str(command_path), *args]

    raise ValueError(f"Unsupported job_type: {job.job_type}")


@contextmanager
def scheduler_lock(blocking: bool = False) -> Iterator[bool]:
    """
    Process-wide file lock for run_scheduler ticks.

    Yields True if lock acquired, False otherwise (non-blocking miss).
    """
    lock_path = Path(
        getattr(
            settings,
            "MCC_SCHEDULER_LOCK_PATH",
            str(Path(settings.DATA_DIR) / "tmp" / "mcc_scheduler.lock"),
        )
    )
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(lock_path, "a+", encoding="utf-8")
    acquired = False
    try:
        flags = fcntl.LOCK_EX
        if not blocking:
            flags |= fcntl.LOCK_NB
        try:
            fcntl.flock(fh.fileno(), flags)
            acquired = True
        except BlockingIOError:
            acquired = False
        yield acquired
    finally:
        if acquired:
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        fh.close()


def should_persist_run(
    *,
    job: ScheduledJob,
    trigger: str,
    status: str,
) -> bool:
    """
    Persist history for failures, timeouts, manual runs, or when log_success_runs.

    Successful scheduler ticks only update last_* + counters by default.
    """
    if status in (
        ScheduledJob.STATUS_ERROR,
        ScheduledJob.STATUS_TIMEOUT,
    ):
        return True
    if status == ScheduledJob.STATUS_SKIPPED:
        return False
    if trigger == ScheduledJobRun.TRIGGER_MANUAL:
        return True
    if status == ScheduledJob.STATUS_OK and job.log_success_runs:
        return True
    return False


def prune_job_runs(job: ScheduledJob | None = None) -> int:
    """
    Drop old / excess ScheduledJobRun rows.

    Returns number of deleted rows.
    """
    retention_days = int(getattr(settings, "MCC_SCHEDULER_RUN_RETENTION_DAYS", 30))
    max_per_job = int(getattr(settings, "MCC_SCHEDULER_RUN_MAX_PER_JOB", 50))
    deleted = 0
    now = timezone.now()

    jobs = [job] if job is not None else list(ScheduledJob.objects.all())
    for j in jobs:
        qs = ScheduledJobRun.objects.filter(job=j)
        if retention_days > 0:
            cutoff = now - timedelta(days=retention_days)
            deleted += qs.filter(started_at__lt=cutoff).delete()[0]
            qs = ScheduledJobRun.objects.filter(job=j)
        if max_per_job > 0:
            keep_ids = list(
                qs.order_by("-started_at").values_list("id", flat=True)[:max_per_job]
            )
            if keep_ids:
                deleted += qs.exclude(id__in=keep_ids).delete()[0]
            else:
                deleted += qs.delete()[0]
    return deleted


def mark_stale_runs(job: ScheduledJob, now=None) -> int:
    """
    Close unfinished runs that exceeded timeout (+ grace).

    Returns number of runs marked as timeout.
    """
    now = now or timezone.now()
    grace = getattr(settings, "MCC_SCHEDULER_STALE_GRACE_SECONDS", 60)
    cutoff = now - timedelta(seconds=job.timeout_seconds + grace)
    stale = ScheduledJobRun.objects.filter(
        job=job,
        status=ScheduledJobRun.STATUS_RUNNING,
        finished_at__isnull=True,
        started_at__lt=cutoff,
    )
    count = 0
    for run in stale:
        run.status = ScheduledJobRun.STATUS_TIMEOUT
        run.finished_at = now
        run.message = "Marked stale: exceeded timeout without finish"
        run.save(update_fields=["status", "finished_at", "message"])
        count += 1
        ScheduledJob.objects.filter(pk=job.pk).update(error_count=F("error_count") + 1)
    if count and job.last_status == ScheduledJob.STATUS_RUNNING:
        job.last_status = ScheduledJob.STATUS_TIMEOUT
        job.last_finished_at = now
        job.last_message = "Previous run marked stale (timeout)"
        job.save(update_fields=["last_status", "last_finished_at", "last_message"])
        job.refresh_from_db(fields=["error_count"])
    return count


def has_active_run(job: ScheduledJob) -> bool:
    return ScheduledJobRun.objects.filter(
        job=job,
        status=ScheduledJobRun.STATUS_RUNNING,
        finished_at__isnull=True,
    ).exists()


def execute_job(
    job: ScheduledJob,
    *,
    trigger: str = ScheduledJobRun.TRIGGER_SCHEDULER,
    user=None,
    force: bool = False,
) -> JobRunResult:
    """
    Run one job; update last_* / counters; persist history only when useful.

    If ``force`` is False and overlap is not allowed while a run is active,
    the job is skipped (counter only, no history row).
    """
    now = timezone.now()
    mark_stale_runs(job, now=now)

    if not force and not job.allow_overlap and has_active_run(job):
        result = JobRunResult(
            status=ScheduledJob.STATUS_SKIPPED,
            message="Skipped: previous run still active",
            skipped=True,
        )
        _record_skip(job, result, started_at=now)
        return result

    if not job.enabled and trigger == ScheduledJobRun.TRIGGER_SCHEDULER and not force:
        return JobRunResult(
            status=ScheduledJob.STATUS_SKIPPED,
            message="Skipped: job disabled",
            skipped=True,
        )

    # Always create a RUNNING row for overlap detection; may be deleted if not persisted.
    run = ScheduledJobRun.objects.create(
        job=job,
        started_at=now,
        status=ScheduledJobRun.STATUS_RUNNING,
        trigger=trigger,
        triggered_by=user if getattr(user, "is_authenticated", False) else None,
    )
    job.last_started_at = now
    job.last_status = ScheduledJob.STATUS_RUNNING
    job.last_message = ""
    job.save(update_fields=["last_started_at", "last_status", "last_message"])

    max_chars = job.max_runtime_log_chars or 20000
    try:
        cwd = resolve_working_directory(job)
        argv = build_argv(job, cwd)
    except Exception as exc:
        return _finalize_run(
            job,
            run,
            JobRunResult(
                status=ScheduledJob.STATUS_ERROR,
                exit_code=None,
                message=str(exc),
            ),
            trigger=trigger,
            max_chars=max_chars,
        )

    logger.info("Starting scheduled job %s: %s", job.slug, " ".join(argv))
    try:
        completed = subprocess.run(
            argv,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=job.timeout_seconds,
            env=os.environ.copy(),
            check=False,
        )
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        if completed.returncode == 0:
            result = JobRunResult(
                status=ScheduledJob.STATUS_OK,
                exit_code=completed.returncode,
                message="OK",
                stdout_excerpt=stdout,
                stderr_excerpt=stderr,
            )
        else:
            result = JobRunResult(
                status=ScheduledJob.STATUS_ERROR,
                exit_code=completed.returncode,
                message=f"Exit code {completed.returncode}",
                stdout_excerpt=stdout,
                stderr_excerpt=stderr,
            )
        return _finalize_run(
            job, run, result, trigger=trigger, max_chars=max_chars
        )
    except subprocess.TimeoutExpired as exc:
        stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        stderr = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
        result = JobRunResult(
            status=ScheduledJob.STATUS_TIMEOUT,
            exit_code=None,
            message=f"Timeout after {job.timeout_seconds}s",
            stdout_excerpt=stdout,
            stderr_excerpt=stderr,
        )
        return _finalize_run(
            job, run, result, trigger=trigger, max_chars=max_chars
        )
    except Exception as exc:
        logger.exception("Scheduled job %s failed", job.slug)
        result = JobRunResult(
            status=ScheduledJob.STATUS_ERROR,
            message=str(exc),
        )
        return _finalize_run(
            job, run, result, trigger=trigger, max_chars=max_chars
        )


def _record_skip(job: ScheduledJob, result: JobRunResult, *, started_at) -> None:
    # No history row for skips — counters + last_* only.
    ScheduledJob.objects.filter(pk=job.pk).update(skip_count=F("skip_count") + 1)
    job.last_status = ScheduledJob.STATUS_SKIPPED
    job.last_finished_at = started_at
    job.last_message = result.message
    job.save(update_fields=["last_status", "last_finished_at", "last_message"])
    job.refresh_from_db(fields=["skip_count"])


def _finalize_run(
    job: ScheduledJob,
    run: ScheduledJobRun,
    result: JobRunResult,
    *,
    trigger: str,
    max_chars: int,
) -> JobRunResult:
    finished = timezone.now()
    persist = should_persist_run(job=job, trigger=trigger, status=result.status)

    if result.status == ScheduledJob.STATUS_OK:
        ScheduledJob.objects.filter(pk=job.pk).update(
            success_count=F("success_count") + 1
        )
    elif result.status in (ScheduledJob.STATUS_ERROR, ScheduledJob.STATUS_TIMEOUT):
        ScheduledJob.objects.filter(pk=job.pk).update(
            error_count=F("error_count") + 1
        )

    job.last_finished_at = finished
    job.last_status = result.status
    job.last_message = result.message
    job.save(update_fields=["last_finished_at", "last_status", "last_message"])
    job.refresh_from_db(fields=["success_count", "error_count", "skip_count"])

    stdout = _truncate(result.stdout_excerpt or "", max_chars)
    stderr = _truncate(result.stderr_excerpt or "", max_chars)
    result.stdout_excerpt = stdout
    result.stderr_excerpt = stderr

    if persist:
        run.finished_at = finished
        run.status = result.status
        run.exit_code = result.exit_code
        run.message = result.message
        run.stdout_excerpt = stdout
        run.stderr_excerpt = stderr
        run.save(
            update_fields=[
                "finished_at",
                "status",
                "exit_code",
                "message",
                "stdout_excerpt",
                "stderr_excerpt",
            ]
        )
        result.persisted = True
        prune_job_runs(job)
    else:
        run.delete()
        result.persisted = False

    return result
