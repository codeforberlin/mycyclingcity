# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    0020_mcc_backup_config.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def seed_backup_config_and_job(apps, schema_editor):
    MccBackupConfig = apps.get_model("mgmt", "MccBackupConfig")
    ScheduledJob = apps.get_model("mgmt", "ScheduledJob")

    config, _ = MccBackupConfig.objects.get_or_create(
        pk=1,
        defaults={
            "ssh_host": "cbm-srv2",
            "ssh_user": "mccweb",
            "ssh_port": 22,
            "ssh_key": "",
            "remote_backup_dir": "/home/mccweb/backup",
            "retention_days": 30,
        },
    )
    # Ensure known production values if row already existed empty/TODO
    updated = False
    if config.ssh_host in ("", "backup.example.com"):
        config.ssh_host = "cbm-srv2"
        updated = True
    if config.ssh_user in ("", "backup-user", "TODO_BACKUP_USER"):
        config.ssh_user = "mccweb"
        updated = True
    if not config.remote_backup_dir or "TODO" in config.remote_backup_dir:
        config.remote_backup_dir = "/home/mccweb/backup"
        updated = True
    if updated:
        config.save()

    job = ScheduledJob.objects.filter(slug="backup_mcc").first()
    if job is not None:
        job.job_type = "management_command"
        job.command = "run_backup_mcc"
        job.arguments = ""
        job.working_directory = ""
        job.enabled = True
        job.timeout_seconds = 7200
        job.save()


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("mgmt", "0019_scheduled_jobs"),
    ]

    operations = [
        migrations.CreateModel(
            name="MccBackupConfig",
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
                (
                    "ssh_host",
                    models.CharField(
                        default="cbm-srv2",
                        help_text="Hostname oder IP des Backup-Servers",
                        max_length=255,
                        verbose_name="SSH-Host",
                    ),
                ),
                (
                    "ssh_user",
                    models.CharField(
                        default="mccweb",
                        max_length=128,
                        verbose_name="SSH-Benutzer",
                    ),
                ),
                (
                    "ssh_port",
                    models.PositiveIntegerField(default=22, verbose_name="SSH-Port"),
                ),
                (
                    "ssh_key",
                    models.CharField(
                        blank=True,
                        help_text="Optionaler Pfad zum Private Key (leer = SSH-Default)",
                        max_length=512,
                        verbose_name="SSH-Private-Key",
                    ),
                ),
                (
                    "remote_backup_dir",
                    models.CharField(
                        default="/home/mccweb/backup",
                        help_text=(
                            "Zielverzeichnis auf dem Remote-Server "
                            "(Unterordner backups/ und media/ werden verwendet)"
                        ),
                        max_length=512,
                        verbose_name="Remote-Backup-Verzeichnis",
                    ),
                ),
                (
                    "retention_days",
                    models.PositiveIntegerField(
                        default=30,
                        help_text="Aufbewahrung lokaler DB-Kopien unter /data/var/mcc/backups",
                        verbose_name="Lokale Retention (Tage)",
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="Zuletzt aktualisiert"),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="updated_mcc_backup_configs",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Aktualisiert von",
                    ),
                ),
            ],
            options={
                "verbose_name": "MCC Backup-Konfiguration",
                "verbose_name_plural": "MCC Backup-Konfiguration",
            },
        ),
        migrations.RunPython(seed_backup_config_and_job, noop_reverse),
    ]
