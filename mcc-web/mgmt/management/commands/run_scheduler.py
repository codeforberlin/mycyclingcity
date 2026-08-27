# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    run_scheduler.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

"""
Minute-tick entrypoint for data-driven scheduled jobs.

Usage:
    python manage.py run_scheduler
    python manage.py run_scheduler --job mcc_worker
    python manage.py run_scheduler --job backup_mcc --force
"""

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from mgmt.models_scheduler import ScheduledJob, ScheduledJobRun
from mgmt.services.job_runner import execute_job, prune_job_runs, scheduler_lock
from mgmt.services.schedule_due import is_job_due


class Command(BaseCommand):
    help = "Run due ScheduledJob entries (OS cron should call this every minute)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--job",
            type=str,
            default=None,
            help="Only consider this job slug",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Run even if not due / disabled (manual-style)",
        )
        parser.add_argument(
            "--no-lock",
            action="store_true",
            help="Skip global scheduler lock (tests / debugging only)",
        )

    def handle(self, *args, **options):
        job_slug = options["job"]
        force = options["force"]
        use_lock = not options["no_lock"]
        now = timezone.now()

        if use_lock:
            with scheduler_lock(blocking=False) as acquired:
                if not acquired:
                    self.stdout.write(
                        self.style.WARNING(
                            "Another run_scheduler instance holds the lock; exiting."
                        )
                    )
                    return
                self._run_tick(job_slug=job_slug, force=force, now=now)
        else:
            self._run_tick(job_slug=job_slug, force=force, now=now)

    def _run_tick(self, *, job_slug, force, now):
        qs = ScheduledJob.objects.all().order_by("sort_order", "name")
        if job_slug:
            qs = qs.filter(slug=job_slug)
            if not qs.exists():
                raise CommandError(f"Unknown scheduled job slug: {job_slug}")

        if not force:
            qs = qs.filter(enabled=True)

        jobs = list(qs)
        if not jobs:
            self.stdout.write("No scheduled jobs to consider.")
            return

        ran = 0
        skipped = 0
        for job in jobs:
            if not force and not is_job_due(job, now=now):
                continue
            trigger = (
                ScheduledJobRun.TRIGGER_MANUAL
                if force
                else ScheduledJobRun.TRIGGER_SCHEDULER
            )
            self.stdout.write(f"Running job {job.slug} …")
            result = execute_job(job, trigger=trigger, force=force)
            if result.skipped:
                skipped += 1
                self.stdout.write(self.style.WARNING(f"  skipped: {result.message}"))
            elif result.status == ScheduledJob.STATUS_OK:
                ran += 1
                self.stdout.write(self.style.SUCCESS(f"  ok ({result.message})"))
            else:
                ran += 1
                self.stdout.write(
                    self.style.ERROR(f"  {result.status}: {result.message}")
                )

        pruned = prune_job_runs()
        self.stdout.write(
            self.style.NOTICE(
                f"Scheduler tick done at {now.isoformat()}: "
                f"executed={ran}, skipped_overlap={skipped}, pruned_runs={pruned}"
            )
        )
