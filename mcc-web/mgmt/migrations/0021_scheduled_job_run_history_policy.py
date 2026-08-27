# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    0021_scheduled_job_run_history_policy.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

from django.db import migrations, models


def purge_routine_success_runs(apps, schema_editor):
    """Remove historical OK+scheduler rows that would no longer be stored."""
    ScheduledJobRun = apps.get_model("mgmt", "ScheduledJobRun")
    ScheduledJobRun.objects.filter(status="ok", trigger="scheduler").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("mgmt", "0020_mcc_backup_config"),
    ]

    operations = [
        migrations.AddField(
            model_name="scheduledjob",
            name="log_success_runs",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Standard: aus. Erfolgreiche Tick-Läufe aktualisieren nur last_* und Zähler; "
                    "Historie nur bei Fehler/Timeout/manuell (oder wenn hier aktiv)."
                ),
                verbose_name="Erfolgreiche Scheduler-Läufe protokollieren",
            ),
        ),
        migrations.AddField(
            model_name="scheduledjob",
            name="success_count",
            field=models.PositiveIntegerField(default=0, verbose_name="Erfolge (Zähler)"),
        ),
        migrations.AddField(
            model_name="scheduledjob",
            name="error_count",
            field=models.PositiveIntegerField(default=0, verbose_name="Fehler (Zähler)"),
        ),
        migrations.AddField(
            model_name="scheduledjob",
            name="skip_count",
            field=models.PositiveIntegerField(
                default=0, verbose_name="Übersprungen (Zähler)"
            ),
        ),
        migrations.RunPython(purge_routine_success_runs, migrations.RunPython.noop),
    ]
