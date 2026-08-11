# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("minecraft", "0054_stations_and_ms_allowlist"),
    ]

    operations = [
        migrations.AddField(
            model_name="minecraftintegrationconfig",
            name="world_ticket_enabled",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "Zeigt den Ticket-Zähler auf den Session-Kacheln und vergibt "
                    "Paper-Tickets per RCON beim Freischalten."
                ),
                verbose_name="MCC-Welt-Tickets aktiv",
            ),
        ),
        migrations.AddField(
            model_name="minecraftintegrationconfig",
            name="world_ticket_velos",
            field=models.PositiveIntegerField(
                default=100,
                help_text=(
                    "Preis eines Paper-Tickets. Bei Radler-Konto (RFID/Warteliste) "
                    "wird Anzahl × dieser Betrag vom Guthaben abgezogen."
                ),
                validators=[MinValueValidator(1)],
                verbose_name="Velos pro MCC-Ticket",
            ),
        ),
        migrations.AddField(
            model_name="minecraftintegrationconfig",
            name="world_ticket_max",
            field=models.PositiveIntegerField(
                default=10,
                help_text="Obergrenze für den Ticket-Zähler auf den Session-Kacheln.",
                validators=[MinValueValidator(1)],
                verbose_name="Max. Tickets pro Freigabe",
            ),
        ),
        migrations.AddField(
            model_name="mcsession",
            name="world_ticket_count",
            field=models.PositiveSmallIntegerField(
                db_default=0,
                default=0,
                help_text=(
                    "Anzahl Paper-Tickets (custom_data mcc_ticket), die beim Bootstrap "
                    "per RCON ins Inventar gelegt werden."
                ),
                verbose_name="MCC-Welt-Tickets",
            ),
        ),
    ]
