# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("minecraft", "0036_auth_failover_playerdata"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="minecraftintegrationconfig",
            options={
                "permissions": [
                    ("access_minecraft_control", "Control öffnen"),
                    ("access_minecraft_city", "Stadtsteuerung öffnen"),
                    ("access_minecraft_shop", "Shop-Betrieb öffnen"),
                    ("run_free_rcon", "Freie RCON-Befehle senden"),
                    ("manage_player_sessions", "Spieler-Sessions verwalten"),
                    ("manage_builder_sessions", "Builder-Sessions verwalten"),
                    ("run_arena_sim", "Velo-Arena Simulation starten"),
                    ("manage_minecraft_proxy", "Velocity / Limbo / Paper steuern"),
                    ("manage_auth_failover", "Auth-Failover / Playerdata-Transfer"),
                ],
                "verbose_name": "Integration",
                "verbose_name_plural": "Integration",
            },
        ),
    ]
