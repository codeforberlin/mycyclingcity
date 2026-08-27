# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    models_scheduler.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

"""
Data-driven scheduled jobs for MCC background work (metrics worker, backups, …).

Jobs are managed via Django Admin; the OS only needs a single minute tick
(`manage.py run_scheduler`).
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _


class ScheduledJob(models.Model):
    """Definition of a periodic or manually runnable job."""

    JOB_TYPE_MANAGEMENT = "management_command"
    JOB_TYPE_SHELL = "shell"
    JOB_TYPE_CHOICES = [
        (JOB_TYPE_MANAGEMENT, _("Django Management Command")),
        (JOB_TYPE_SHELL, _("Shell-Skript / Executable")),
    ]

    SCHEDULE_INTERVAL = "interval"
    SCHEDULE_CRON = "cron"
    SCHEDULE_TYPE_CHOICES = [
        (SCHEDULE_INTERVAL, _("Intervall (Sekunden)")),
        (SCHEDULE_CRON, _("Cron-Ausdruck")),
    ]

    STATUS_NEVER = "never"
    STATUS_OK = "ok"
    STATUS_ERROR = "error"
    STATUS_TIMEOUT = "timeout"
    STATUS_SKIPPED = "skipped"
    STATUS_RUNNING = "running"
    STATUS_CHOICES = [
        (STATUS_NEVER, _("Noch nie")),
        (STATUS_OK, _("OK")),
        (STATUS_ERROR, _("Fehler")),
        (STATUS_TIMEOUT, _("Timeout")),
        (STATUS_SKIPPED, _("Übersprungen")),
        (STATUS_RUNNING, _("Läuft")),
    ]

    name = models.CharField(
        max_length=120,
        verbose_name=_("Name"),
        help_text=_("Anzeigename im Admin"),
    )
    slug = models.SlugField(
        max_length=80,
        unique=True,
        verbose_name=_("Slug"),
        help_text=_("Stabiler technischer Schlüssel (z. B. mcc_worker)"),
    )
    description = models.TextField(
        blank=True,
        verbose_name=_("Beschreibung"),
    )
    enabled = models.BooleanField(
        default=True,
        verbose_name=_("Aktiv"),
        help_text=_("Deaktivierte Jobs werden vom Scheduler ignoriert"),
    )
    job_type = models.CharField(
        max_length=32,
        choices=JOB_TYPE_CHOICES,
        verbose_name=_("Job-Typ"),
    )
    command = models.CharField(
        max_length=512,
        verbose_name=_("Befehl / Pfad"),
        help_text=_(
            "Management-Command-Name (z. B. mcc_worker) oder Shell-Skript-Pfad "
            "(absolut oder relativ zum Projektroot)"
        ),
    )
    arguments = models.TextField(
        blank=True,
        verbose_name=_("Argumente"),
        help_text=_("Optionale Argumentzeile (wird mit shlex gesplittet)"),
    )
    working_directory = models.CharField(
        max_length=512,
        blank=True,
        verbose_name=_("Arbeitsverzeichnis"),
        help_text=_("Leer = Projektroot (mcc-web)"),
    )
    schedule_type = models.CharField(
        max_length=16,
        choices=SCHEDULE_TYPE_CHOICES,
        default=SCHEDULE_INTERVAL,
        verbose_name=_("Zeitplan-Typ"),
    )
    interval_seconds = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Intervall (Sekunden)"),
        help_text=_("Nur bei Zeitplan-Typ „Intervall“"),
    )
    cron_expression = models.CharField(
        max_length=64,
        blank=True,
        verbose_name=_("Cron-Ausdruck"),
        help_text=_("Fünf Felder: Minute Stunde Tag Monat Wochentag (z. B. 0 22 * * *)"),
    )
    timeout_seconds = models.PositiveIntegerField(
        default=3600,
        verbose_name=_("Timeout (Sekunden)"),
    )
    allow_overlap = models.BooleanField(
        default=False,
        verbose_name=_("Überlappung erlauben"),
        help_text=_("Wenn deaktiviert, wird ein neuer Lauf übersprungen solange einer läuft"),
    )
    max_runtime_log_chars = models.PositiveIntegerField(
        default=20000,
        verbose_name=_("Max. Log-Zeichen"),
        help_text=_("Stdout/Stderr in der Historie werden auf diese Länge gekürzt"),
    )
    log_success_runs = models.BooleanField(
        default=False,
        verbose_name=_("Erfolgreiche Scheduler-Läufe protokollieren"),
        help_text=_(
            "Standard: aus. Erfolgreiche Tick-Läufe aktualisieren nur last_* und Zähler; "
            "Historie nur bei Fehler/Timeout/manuell (oder wenn hier aktiv)."
        ),
    )
    success_count = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Erfolge (Zähler)"),
    )
    error_count = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Fehler (Zähler)"),
    )
    skip_count = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Übersprungen (Zähler)"),
    )
    sort_order = models.PositiveIntegerField(
        default=100,
        verbose_name=_("Reihenfolge"),
    )
    last_started_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Zuletzt gestartet"),
    )
    last_finished_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Zuletzt beendet"),
    )
    last_status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_NEVER,
        verbose_name=_("Letzter Status"),
    )
    last_message = models.TextField(
        blank=True,
        verbose_name=_("Letzte Meldung"),
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Zuletzt aktualisiert"),
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_scheduled_jobs",
        verbose_name=_("Aktualisiert von"),
    )

    class Meta:
        verbose_name = _("Geplanter Job")
        verbose_name_plural = _("Geplante Jobs")
        ordering = ["sort_order", "name"]
        permissions = [
            ("run_scheduledjob", "Can run scheduled jobs manually"),
        ]

    def __str__(self):
        state = "on" if self.enabled else "off"
        return f"{self.name} ({self.slug}, {state})"

    def clean(self):
        super().clean()
        if self.schedule_type == self.SCHEDULE_INTERVAL:
            if not self.interval_seconds or self.interval_seconds < 1:
                raise ValidationError(
                    {"interval_seconds": _("Intervall muss mindestens 1 Sekunde sein.")}
                )
        elif self.schedule_type == self.SCHEDULE_CRON:
            expr = (self.cron_expression or "").strip()
            if not expr:
                raise ValidationError({"cron_expression": _("Cron-Ausdruck ist erforderlich.")})
            try:
                from croniter import croniter
            except ImportError as exc:
                raise ValidationError(
                    _("Paket croniter ist nicht installiert.")
                ) from exc
            if not croniter.is_valid(expr):
                raise ValidationError({"cron_expression": _("Ungültiger Cron-Ausdruck.")})
            self.cron_expression = expr

        if not (self.command or "").strip():
            raise ValidationError({"command": _("Befehl / Pfad ist erforderlich.")})

    def schedule_summary(self) -> str:
        if self.schedule_type == self.SCHEDULE_INTERVAL:
            return f"alle {self.interval_seconds}s"
        return self.cron_expression or "—"


class ScheduledJobRun(models.Model):
    """Append-only execution history for a scheduled job."""

    TRIGGER_SCHEDULER = "scheduler"
    TRIGGER_MANUAL = "manual"
    TRIGGER_CHOICES = [
        (TRIGGER_SCHEDULER, _("Scheduler")),
        (TRIGGER_MANUAL, _("Manuell")),
    ]

    STATUS_OK = ScheduledJob.STATUS_OK
    STATUS_ERROR = ScheduledJob.STATUS_ERROR
    STATUS_TIMEOUT = ScheduledJob.STATUS_TIMEOUT
    STATUS_SKIPPED = ScheduledJob.STATUS_SKIPPED
    STATUS_RUNNING = ScheduledJob.STATUS_RUNNING
    STATUS_CHOICES = [
        (STATUS_OK, _("OK")),
        (STATUS_ERROR, _("Fehler")),
        (STATUS_TIMEOUT, _("Timeout")),
        (STATUS_SKIPPED, _("Übersprungen")),
        (STATUS_RUNNING, _("Läuft")),
    ]

    job = models.ForeignKey(
        ScheduledJob,
        on_delete=models.CASCADE,
        related_name="runs",
        verbose_name=_("Job"),
    )
    started_at = models.DateTimeField(
        verbose_name=_("Gestartet"),
    )
    finished_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Beendet"),
    )
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_RUNNING,
        verbose_name=_("Status"),
    )
    exit_code = models.IntegerField(
        null=True,
        blank=True,
        verbose_name=_("Exit-Code"),
    )
    trigger = models.CharField(
        max_length=16,
        choices=TRIGGER_CHOICES,
        default=TRIGGER_SCHEDULER,
        verbose_name=_("Auslöser"),
    )
    stdout_excerpt = models.TextField(
        blank=True,
        verbose_name=_("Stdout (Auszug)"),
    )
    stderr_excerpt = models.TextField(
        blank=True,
        verbose_name=_("Stderr (Auszug)"),
    )
    message = models.TextField(
        blank=True,
        verbose_name=_("Meldung"),
    )
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="triggered_scheduled_job_runs",
        verbose_name=_("Ausgelöst von"),
    )

    class Meta:
        verbose_name = _("Job-Ausführung")
        verbose_name_plural = _("Job-Ausführungen")
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["job", "-started_at"]),
            models.Index(fields=["status", "finished_at"]),
        ]

    def __str__(self):
        return f"{self.job.slug} @ {self.started_at} [{self.status}]"
