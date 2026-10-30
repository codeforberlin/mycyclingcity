# Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("luanti", "0022_daytime_preset_always_day"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="luantiintegrationconfig",
            options={
                "permissions": [
                    ("access_luanti_control", "Control öffnen"),
                    ("access_luanti_city", "Stadtsteuerung öffnen"),
                    ("access_luanti_shop", "Shop öffnen"),
                    ("access_luanti_arena", "Arena/Loren öffnen"),
                    ("manage_luanti_accounts", "Accounts verwalten"),
                    ("manage_luanti_sessions", "Sessions verwalten"),
                    ("manage_luanti_stations", "Stationen verwalten"),
                    ("view_luanti_login_password", "Luanti Login-Passwort anzeigen"),
                    ("set_luanti_login_password", "Luanti Login-Passwort setzen"),
                ],
                "verbose_name": "Luanti-Konfiguration",
                "verbose_name_plural": "Luanti-Konfiguration",
            },
        ),
    ]
