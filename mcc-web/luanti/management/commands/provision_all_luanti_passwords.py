# Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.core.management.base import BaseCommand

from luanti.models import LuantiAccount
from luanti.services.passwords import provision_account_password


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

    def handle(self, *args, **options):
        qs = LuantiAccount.objects.exclude(login_password="")
        if not options["include_inactive"]:
            qs = qs.filter(is_active=True)
        count = 0
        for account in qs.order_by("login_name"):
            provision_account_password(account, account.login_password)
            count += 1
            self.stdout.write(f"queued SET_PASSWORD for {account.login_name}")
        self.stdout.write(self.style.SUCCESS(f"Done. Queued {count} account(s)."))
