# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    0019_scheduled_jobs.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def seed_default_jobs(apps, schema_editor):
    """Create default jobs if missing (get_or_create by slug)."""
    ScheduledJob = apps.get_model("mgmt", "ScheduledJob")
    base = str(settings.BASE_DIR)
    app_dir = str(getattr(settings, "APP_DIR", settings.BASE_DIR))

    defaults = [
        {
            "slug": "mcc_worker",
            "name": "MCC Worker (Hourly Metrics)",
            "description": (
                "Speichert aktive Sessions in HourlyMetric und bereinigt "
                "abgelaufene Sessions."
            ),
            "enabled": True,
            "job_type": "management_command",
            "command": "mcc_worker",
            "arguments": "",
            "working_directory": "",
            "schedule_type": "interval",
            "interval_seconds": 60,
            "cron_expression": "",
            "timeout_seconds": 120,
            "allow_overlap": False,
            "sort_order": 10,
        },
        {
            "slug": "backup_mcc",
            "name": "MCC Datenbank-/Media-Backup",
            "description": (
                "Tägliches Backup via scripts/backup_mcc.sh (SSH/rsync). "
                "Argumente: optionaler Pfad zur .conf (Produktion oft "
                f"{app_dir}/backup_mcc.conf)."
            ),
            "enabled": True,
            "job_type": "shell",
            "command": "scripts/backup_mcc.sh",
            "arguments": f"{app_dir}/backup_mcc.conf",
            "working_directory": base,
            "schedule_type": "cron",
            "interval_seconds": None,
            "cron_expression": "0 22 * * *",
            "timeout_seconds": 7200,
            "allow_overlap": False,
            "sort_order": 20,
        },
        {
            "slug": "backup_minecraft",
            "name": "Minecraft Welt-Backup",
            "description": (
                "Stündliches Welt-Backup via scripts/backup_minecraft_world.sh "
                "(RCON flush + tar)."
            ),
            "enabled": True,
            "job_type": "shell",
            "command": "scripts/backup_minecraft_world.sh",
            "arguments": f"{base}/scripts/backup_minecraft_world.conf",
            "working_directory": base,
            "schedule_type": "cron",
            "interval_seconds": None,
            "cron_expression": "5 * * * *",
            "timeout_seconds": 3600,
            "allow_overlap": False,
            "sort_order": 30,
        },
    ]

    for data in defaults:
        slug = data.pop("slug")
        ScheduledJob.objects.get_or_create(slug=slug, defaults=data)


def unseed_default_jobs(apps, schema_editor):
    ScheduledJob = apps.get_model("mgmt", "ScheduledJob")
    ScheduledJob.objects.filter(
        slug__in=["mcc_worker", "backup_mcc", "backup_minecraft"]
    ).delete()


def grant_run_permission(apps, schema_editor):
    """Attach run_scheduledjob to known operator groups when present."""
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")
    ct = ContentType.objects.filter(app_label="mgmt", model="scheduledjob").first()
    if ct is None:
        return
    perm = Permission.objects.filter(content_type=ct, codename="run_scheduledjob").first()
    if perm is None:
        return
    for group_name in ("mcc_operator", "Operatoren"):
        group = Group.objects.filter(name=group_name).first()
        if group is not None:
            group.permissions.add(perm)


def revoke_run_permission(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")
    ct = ContentType.objects.filter(app_label="mgmt", model="scheduledjob").first()
    if ct is None:
        return
    perm = Permission.objects.filter(content_type=ct, codename="run_scheduledjob").first()
    if perm is None:
        return
    for group in Group.objects.filter(name__in=["mcc_operator", "Operatoren"]):
        group.permissions.remove(perm)


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("mgmt", "0018_gunicorn_bind_all_interfaces"),
    ]

    operations = [
        migrations.CreateModel(
            name="ScheduledJob",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(help_text="Anzeigename im Admin", max_length=120, verbose_name="Name")),
                (
                    "slug",
                    models.SlugField(
                        help_text="Stabiler technischer Schlüssel (z. B. mcc_worker)",
                        max_length=80,
                        unique=True,
                        verbose_name="Slug",
                    ),
                ),
                ("description", models.TextField(blank=True, verbose_name="Beschreibung")),
                (
                    "enabled",
                    models.BooleanField(
                        default=True,
                        help_text="Deaktivierte Jobs werden vom Scheduler ignoriert",
                        verbose_name="Aktiv",
                    ),
                ),
                (
                    "job_type",
                    models.CharField(
                        choices=[
                            ("management_command", "Django Management Command"),
                            ("shell", "Shell-Skript / Executable"),
                        ],
                        max_length=32,
                        verbose_name="Job-Typ",
                    ),
                ),
                (
                    "command",
                    models.CharField(
                        help_text=(
                            "Management-Command-Name (z. B. mcc_worker) oder Shell-Skript-Pfad "
                            "(absolut oder relativ zum Projektroot)"
                        ),
                        max_length=512,
                        verbose_name="Befehl / Pfad",
                    ),
                ),
                (
                    "arguments",
                    models.TextField(
                        blank=True,
                        help_text="Optionale Argumentzeile (wird mit shlex gesplittet)",
                        verbose_name="Argumente",
                    ),
                ),
                (
                    "working_directory",
                    models.CharField(
                        blank=True,
                        help_text="Leer = Projektroot (mcc-web)",
                        max_length=512,
                        verbose_name="Arbeitsverzeichnis",
                    ),
                ),
                (
                    "schedule_type",
                    models.CharField(
                        choices=[
                            ("interval", "Intervall (Sekunden)"),
                            ("cron", "Cron-Ausdruck"),
                        ],
                        default="interval",
                        max_length=16,
                        verbose_name="Zeitplan-Typ",
                    ),
                ),
                (
                    "interval_seconds",
                    models.PositiveIntegerField(
                        blank=True,
                        help_text="Nur bei Zeitplan-Typ „Intervall“",
                        null=True,
                        verbose_name="Intervall (Sekunden)",
                    ),
                ),
                (
                    "cron_expression",
                    models.CharField(
                        blank=True,
                        help_text="Fünf Felder: Minute Stunde Tag Monat Wochentag (z. B. 0 22 * * *)",
                        max_length=64,
                        verbose_name="Cron-Ausdruck",
                    ),
                ),
                (
                    "timeout_seconds",
                    models.PositiveIntegerField(default=3600, verbose_name="Timeout (Sekunden)"),
                ),
                (
                    "allow_overlap",
                    models.BooleanField(
                        default=False,
                        help_text="Wenn deaktiviert, wird ein neuer Lauf übersprungen solange einer läuft",
                        verbose_name="Überlappung erlauben",
                    ),
                ),
                (
                    "max_runtime_log_chars",
                    models.PositiveIntegerField(
                        default=20000,
                        help_text="Stdout/Stderr in der Historie werden auf diese Länge gekürzt",
                        verbose_name="Max. Log-Zeichen",
                    ),
                ),
                ("sort_order", models.PositiveIntegerField(default=100, verbose_name="Reihenfolge")),
                (
                    "last_started_at",
                    models.DateTimeField(blank=True, null=True, verbose_name="Zuletzt gestartet"),
                ),
                (
                    "last_finished_at",
                    models.DateTimeField(blank=True, null=True, verbose_name="Zuletzt beendet"),
                ),
                (
                    "last_status",
                    models.CharField(
                        choices=[
                            ("never", "Noch nie"),
                            ("ok", "OK"),
                            ("error", "Fehler"),
                            ("timeout", "Timeout"),
                            ("skipped", "Übersprungen"),
                            ("running", "Läuft"),
                        ],
                        default="never",
                        max_length=16,
                        verbose_name="Letzter Status",
                    ),
                ),
                ("last_message", models.TextField(blank=True, verbose_name="Letzte Meldung")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Zuletzt aktualisiert")),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="updated_scheduled_jobs",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Aktualisiert von",
                    ),
                ),
            ],
            options={
                "verbose_name": "Geplanter Job",
                "verbose_name_plural": "Geplante Jobs",
                "ordering": ["sort_order", "name"],
                "permissions": [("run_scheduledjob", "Can run scheduled jobs manually")],
            },
        ),
        migrations.CreateModel(
            name="ScheduledJobRun",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("started_at", models.DateTimeField(verbose_name="Gestartet")),
                ("finished_at", models.DateTimeField(blank=True, null=True, verbose_name="Beendet")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("ok", "OK"),
                            ("error", "Fehler"),
                            ("timeout", "Timeout"),
                            ("skipped", "Übersprungen"),
                            ("running", "Läuft"),
                        ],
                        default="running",
                        max_length=16,
                        verbose_name="Status",
                    ),
                ),
                ("exit_code", models.IntegerField(blank=True, null=True, verbose_name="Exit-Code")),
                (
                    "trigger",
                    models.CharField(
                        choices=[("scheduler", "Scheduler"), ("manual", "Manuell")],
                        default="scheduler",
                        max_length=16,
                        verbose_name="Auslöser",
                    ),
                ),
                ("stdout_excerpt", models.TextField(blank=True, verbose_name="Stdout (Auszug)")),
                ("stderr_excerpt", models.TextField(blank=True, verbose_name="Stderr (Auszug)")),
                ("message", models.TextField(blank=True, verbose_name="Meldung")),
                (
                    "job",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="runs",
                        to="mgmt.scheduledjob",
                        verbose_name="Job",
                    ),
                ),
                (
                    "triggered_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="triggered_scheduled_job_runs",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Ausgelöst von",
                    ),
                ),
            ],
            options={
                "verbose_name": "Job-Ausführung",
                "verbose_name_plural": "Job-Ausführungen",
                "ordering": ["-started_at"],
            },
        ),
        migrations.AddIndex(
            model_name="scheduledjobrun",
            index=models.Index(fields=["job", "-started_at"], name="mgmt_schedu_job_id_7c6a1e_idx"),
        ),
        migrations.AddIndex(
            model_name="scheduledjobrun",
            index=models.Index(fields=["status", "finished_at"], name="mgmt_schedu_status_9a2b4c_idx"),
        ),
        migrations.RunPython(seed_default_jobs, unseed_default_jobs),
        migrations.RunPython(grant_run_permission, revoke_run_permission),
    ]
