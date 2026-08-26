# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.db import migrations


def add_watch_to_allowed_modes(apps, schema_editor):
    LuantiAccount = apps.get_model("luanti", "LuantiAccount")
    for account in LuantiAccount.objects.all():
        modes = list(account.allowed_modes or [])
        if not modes:
            # Empty already resolves to play+build+watch after model change.
            continue
        if "watch" not in modes:
            modes.append("watch")
            account.allowed_modes = modes
            account.save(update_fields=["allowed_modes"])


def remove_watch_from_allowed_modes(apps, schema_editor):
    LuantiAccount = apps.get_model("luanti", "LuantiAccount")
    for account in LuantiAccount.objects.all():
        modes = list(account.allowed_modes or [])
        if "watch" in modes:
            modes = [m for m in modes if m != "watch"]
            account.allowed_modes = modes
            account.save(update_fields=["allowed_modes"])


class Migration(migrations.Migration):

    dependencies = [
        ("luanti", "0010_session_pause_and_duration_bounds"),
    ]

    operations = [
        migrations.RunPython(add_watch_to_allowed_modes, remove_watch_from_allowed_modes),
    ]
