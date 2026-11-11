# Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.core.management.base import BaseCommand
from django.db import transaction

from luanti.models import LuantiPlanBlock
from luanti.services.plan import _grant_materialize_purchase_credit


class Command(BaseCommand):
    help = "Book shop purchase credit for materialized plan blocks (one-time / idempotent)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Count blocks only, do not update credits.",
        )

    def handle(self, *args, **options):
        dry = bool(options.get("dry_run"))
        qs = LuantiPlanBlock.objects.filter(
            status=LuantiPlanBlock.STATUS_MATERIALIZED,
            purchase_credit_granted=False,
        ).order_by("id")
        total = qs.count()
        if dry:
            self.stdout.write(f"Would grant purchase credit for {total} materialized block(s).")
            return
        granted = 0
        with transaction.atomic():
            for block in qs.select_for_update():
                before = block.purchase_credit_granted
                _grant_materialize_purchase_credit(
                    block=block,
                    fallback_login=block.placed_by or "",
                )
                block.refresh_from_db(fields=["purchase_credit_granted"])
                if block.purchase_credit_granted and not before:
                    granted += 1
        self.stdout.write(
            self.style.SUCCESS(f"Purchase credit granted for {granted} of {total} block(s).")
        )
