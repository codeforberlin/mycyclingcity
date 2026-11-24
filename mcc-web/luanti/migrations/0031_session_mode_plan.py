# Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.db import migrations, models


def add_plan_to_allowed_modes(apps, schema_editor):
    LuantiAccount = apps.get_model("luanti", "LuantiAccount")
    for account in LuantiAccount.objects.all():
        modes = list(account.allowed_modes or [])
        if not modes:
            continue
        if "plan" not in modes:
            modes.append("plan")
            account.allowed_modes = modes
            account.save(update_fields=["allowed_modes"])


def remove_plan_from_allowed_modes(apps, schema_editor):
    LuantiAccount = apps.get_model("luanti", "LuantiAccount")
    for account in LuantiAccount.objects.all():
        modes = list(account.allowed_modes or [])
        if "plan" in modes:
            account.allowed_modes = [m for m in modes if m != "plan"]
            account.save(update_fields=["allowed_modes"])


class Migration(migrations.Migration):

    dependencies = [
        ("luanti", "0030_region_plan_live_convert"),
    ]

    operations = [
        migrations.AlterField(
            model_name="luantiaccount",
            name="default_mode",
            field=models.CharField(
                choices=[
                    ("play", "Spielen"),
                    ("plan", "Planung"),
                    ("build", "Bauen"),
                    ("watch", "Zuschauen"),
                ],
                default="play",
                max_length=16,
                verbose_name="Standard-Modus",
            ),
        ),
        migrations.AlterField(
            model_name="luantisession",
            name="mode",
            field=models.CharField(
                choices=[
                    ("play", "Spielen"),
                    ("plan", "Planung"),
                    ("build", "Bauen"),
                    ("watch", "Zuschauen"),
                ],
                default="play",
                max_length=16,
                verbose_name="Modus",
            ),
        ),
        migrations.AlterField(
            model_name="luantiplayerinventory",
            name="mode",
            field=models.CharField(
                choices=[
                    ("play", "Spielen"),
                    ("plan", "Planung"),
                    ("build", "Bauen"),
                ],
                max_length=16,
                verbose_name="Modus",
            ),
        ),
        migrations.RunPython(add_plan_to_allowed_modes, remove_plan_from_allowed_modes),
    ]