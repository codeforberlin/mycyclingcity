# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    run_backup_mcc.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

"""
Export MccBackupConfig to conf file and run scripts/backup_mcc.sh.

Usage:
    python manage.py run_backup_mcc
    python manage.py run_backup_mcc --dry-write-conf
"""

import os
import subprocess
import sys

from django.core.management.base import BaseCommand, CommandError

from mgmt.services.backup_config import (
    get_backup_script_path,
    write_backup_conf,
)


class Command(BaseCommand):
    help = "Write MCC backup conf from Admin settings and run backup_mcc.sh"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-write-conf",
            action="store_true",
            help="Only write the conf file; do not run the shell script",
        )

    def handle(self, *args, **options):
        conf_path = write_backup_conf()
        self.stdout.write(f"Wrote backup conf: {conf_path}")

        if options["dry_write_conf"]:
            return

        script = get_backup_script_path()
        if not script.is_file():
            raise CommandError(f"Backup script not found: {script}")
        if not os.access(script, os.X_OK):
            raise CommandError(f"Backup script is not executable: {script}")

        cmd = [str(script), str(conf_path)]
        self.stdout.write(f"Running: {' '.join(cmd)}")
        completed = subprocess.run(cmd, check=False)
        if completed.returncode != 0:
            sys.exit(completed.returncode)
