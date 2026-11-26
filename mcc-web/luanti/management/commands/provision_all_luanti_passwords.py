# Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.core.management.base import BaseCommand

from luanti.models import LuantiAccount
from luanti.services.passwords import bulk_provision_account_passwords


class Command(BaseCommand):
    help = (
        "Re-enqueue SET_PASSWORD for all active Luanti accounts that have a login_password "
        "(recovery after world restore or bridge outage)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--include-inactive",
            action="store_true",
            help="Also provision accounts marked inactive.",
        )
        parser.add_argument(
            "--only-unprovisioned",
            action="store_true",
            help="Skip accounts already marked password_provisioned in Django.",
        )

    def handle(self, *args, **options):
        qs = LuantiAccount.objects.exclude(login_password="")
        if not options["include_inactive"]:
            qs = qs.filter(is_active=True)
        if options["only_unprovisioned"]:
            qs = qs.filter(password_provisioned=False)
        result = bulk_provision_account_passwords(
            qs.order_by("login_name"),
            only_unprovisioned=options["only_unprovisioned"],
        )
        for name in result.queued_login_names:
            self.stdout.write(f"queued SET_PASSWORD for {name}")
        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Queued {result.queued} account(s). "
                f"Skipped: no_password={result.skipped_no_password}, "
                f"already_ok={result.skipped_already_provisioned}."
            )
        )