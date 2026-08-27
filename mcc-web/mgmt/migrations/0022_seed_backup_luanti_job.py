# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    0022_seed_backup_luanti_job.py
# @note    Seed ScheduledJob backup_luanti (Luanti world backup).

from django.conf import settings
from django.db import migrations


def seed_backup_luanti(apps, schema_editor):
    ScheduledJob = apps.get_model("mgmt", "ScheduledJob")
    base = str(settings.BASE_DIR)
    ScheduledJob.objects.get_or_create(
        slug="backup_luanti",
        defaults={
            "name": "Luanti Welt-Backup",
            "description": (
                "Stündliches Welt-Backup via scripts/backup_luanti_world.sh "
                "(SQLite .backup + tar; optional Server-Stop)."
            ),
            "enabled": True,
            "job_type": "shell",
            "command": "scripts/backup_luanti_world.sh",
            "arguments": f"{base}/scripts/backup_luanti_world.conf",
            "working_directory": base,
            "schedule_type": "cron",
            "interval_seconds": None,
            "cron_expression": "15 * * * *",
            "timeout_seconds": 3600,
            "allow_overlap": False,
            "sort_order": 35,
        },
    )


def unseed_backup_luanti(apps, schema_editor):
    ScheduledJob = apps.get_model("mgmt", "ScheduledJob")
    ScheduledJob.objects.filter(slug="backup_luanti").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("mgmt", "0021_scheduled_job_run_history_policy"),
    ]

    operations = [
        migrations.RunPython(seed_backup_luanti, unseed_backup_luanti),
    ]
