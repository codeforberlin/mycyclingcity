# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.core.management.base import BaseCommand, CommandError

from minecraft.services.playerdata_migrate import (
    MigrateDirection,
    account_diff_to_dict,
    diff_for_direction,
    run_migration,
)


class Command(BaseCommand):
    help = (
        "Migrate vanilla playerdata between online UUID, MS offline twin, "
        "and legacy AuthMe offline names (Kette → mccpc01)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--direction",
            required=True,
            choices=[d.value for d in MigrateDirection],
            help="online_to_offline | offline_to_online | legacy_to_twin",
        )
        parser.add_argument(
            "--execute",
            action="store_true",
            help="Actually copy files (default is dry-run).",
        )
        parser.add_argument(
            "--account",
            action="append",
            dest="accounts",
            default=[],
            help="Limit to account_ref (short_name / mc_username); repeatable.",
        )
        parser.add_argument(
            "--diff-only",
            action="store_true",
            help="Only print diff table, do not migrate.",
        )

    def handle(self, *args, **options):
        direction = MigrateDirection(options["direction"])
        if options["diff_only"]:
            for row in diff_for_direction(direction):
                data = account_diff_to_dict(row)
                self.stdout.write(
                    f"{data['kind']:7} {data['account_ref']:12} "
                    f"ms={data['ms_username']:12} overall={data['overall']} "
                    f"warn={','.join(data['warnings']) or '-'}"
                )
            return

        dry_run = not options["execute"]
        refs = set(options["accounts"] or []) or None
        result = run_migration(
            direction,
            dry_run=dry_run,
            account_refs=refs,
        )
        mode = "DRY-RUN" if dry_run else "EXECUTE"
        self.stdout.write(
            self.style.NOTICE(
                f"{mode} direction={result.direction} accounts={len(result.rows)} "
                f"backup={result.backup_dir}"
            )
        )
        for row in result.rows:
            status = "ok" if row.get("ok") else "FAIL"
            copied = sum(1 for f in row.get("files") or [] if f.get("copied"))
            self.stdout.write(
                f"  [{status}] {row.get('account_ref')} → files_touched={copied} "
                f"({row.get('detail', '')})"
            )
        if result.errors:
            for err in result.errors:
                self.stderr.write(self.style.ERROR(err))
            raise CommandError(f"{len(result.errors)} error(s)")
        self.stdout.write(self.style.SUCCESS("Done."))
