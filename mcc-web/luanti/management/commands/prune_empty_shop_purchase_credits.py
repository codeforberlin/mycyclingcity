# Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.core.management.base import BaseCommand

from luanti.models import LuantiShopPurchaseCredit


class Command(BaseCommand):
    help = "Delete LuantiShopPurchaseCredit rows with quantity 0 (housekeeping)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report count only, do not delete.",
        )

    def handle(self, *args, **options):
        dry = bool(options.get("dry_run"))
        qs = LuantiShopPurchaseCredit.objects.filter(quantity=0)
        count = qs.count()
        if dry:
            self.stdout.write(f"Would delete {count} empty purchase-credit row(s).")
            return
        deleted, _ = qs.delete()
        self.stdout.write(
            self.style.SUCCESS(f"Deleted {deleted} empty purchase-credit row(s).")
        )
