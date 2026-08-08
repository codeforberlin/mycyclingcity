# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("minecraft", "0031_builder_session_active_hint"),
    ]

    operations = [
        migrations.AddField(
            model_name="minecraftteamregistration",
            name="ms_username",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                help_text=(
                    "Online-Gamertag am Velocity-Proxy (z. B. mccpc01). "
                    "Scoreboard bleibt mc_username; RCON/send und Bridge-Override nutzen diesen Login."
                ),
                max_length=32,
                verbose_name="Microsoft-Login",
            ),
        ),
        migrations.AddField(
            model_name="minecraftteamregistration",
            name="ms_uuid",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Optional; Inventar/Shop hängen an der UUID. Nach erstem Join ergänzbar.",
                max_length=36,
                verbose_name="Microsoft-UUID",
            ),
        ),
        migrations.AddField(
            model_name="minecraftteamregistration",
            name="prefer_gamemode",
            field=models.CharField(
                blank=True,
                default="",
                help_text=(
                    "Leer = Survival (Bau). Werte: survival, adventure, spectator. "
                    "Überschreibt „Spectator bevorzugen“, wenn gesetzt."
                ),
                max_length=16,
                verbose_name="Bevorzugter Spielmodus",
            ),
        ),
        migrations.AddField(
            model_name="minecraftplayaccount",
            name="ms_username",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                help_text="Online-Gamertag am Velocity-Proxy für RCON/send.",
                max_length=32,
                verbose_name="Microsoft-Login",
            ),
        ),
        migrations.AddField(
            model_name="minecraftplayaccount",
            name="ms_uuid",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Optional; Inventar hängt an der UUID.",
                max_length=36,
                verbose_name="Microsoft-UUID",
            ),
        ),
        migrations.AddField(
            model_name="minecraftplayaccount",
            name="prefer_gamemode",
            field=models.CharField(
                blank=True,
                default="",
                help_text=(
                    "Leer = Adventure (Spieler). Werte: survival, adventure, spectator. "
                    "Überschreibt „Spectator bevorzugen“, wenn gesetzt."
                ),
                max_length=16,
                verbose_name="Bevorzugter Spielmodus",
            ),
        ),
        migrations.AddField(
            model_name="mcsession",
            name="ms_username",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                help_text="Online-Spielername für RCON während der Session.",
                max_length=32,
                verbose_name="Microsoft-Login (Session)",
            ),
        ),
        migrations.AddField(
            model_name="mcsession",
            name="play_gamemode",
            field=models.CharField(
                choices=[
                    ("survival", "Survival"),
                    ("adventure", "Adventure"),
                    ("spectator", "Spectator"),
                ],
                db_default="adventure",
                default="adventure",
                help_text="Aktueller Gamemode der Session (survival / adventure / spectator).",
                max_length=16,
                verbose_name="Spielmodus",
            ),
        ),
        migrations.AlterField(
            model_name="mcsession",
            name="account_name",
            field=models.CharField(
                db_index=True,
                help_text="Interner Slot-/Team-Name (short_name oder Team-mc_username)",
                max_length=100,
                verbose_name="Account-Name",
            ),
        ),
        migrations.AlterField(
            model_name="mcsession",
            name="gamemode_spectator",
            field=models.BooleanField(
                db_default=False,
                default=False,
                help_text="Legacy-Flag; gespiegelt aus play_gamemode == spectator.",
                verbose_name="Spectator aktiv",
            ),
        ),
        migrations.AlterField(
            model_name="minecraftplayaccount",
            name="short_name",
            field=models.CharField(
                help_text="Internes Slot-Label (z. B. Arena1); Scoreboard/Warteliste.",
                max_length=32,
                unique=True,
                verbose_name="Kurzname / Login",
            ),
        ),
    ]
