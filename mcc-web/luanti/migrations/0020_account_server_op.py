# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("luanti", "0019_session_spawn_region"),
    ]

    operations = [
        migrations.AddField(
            model_name="luantiaccount",
            name="server_op",
            field=models.BooleanField(
                db_default=False,
                db_index=True,
                default=False,
                help_text=(
                    "Wenn aktiv: bei Session-Freigabe erweiterte Luanti-Privilegien "
                    "(u. a. server, privs, ban, kick, protection_bypass, give, teleport) — "
                    "vergleichbar mit Minecraft /op."
                ),
                verbose_name="Server-Operator",
            ),
        ),
    ]
