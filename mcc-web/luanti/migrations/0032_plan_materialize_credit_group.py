# Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
# SPDX-License-Identifier: AGPL-3.0-or-later

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0030_yearend_snapshot_spendable"),
        ("luanti", "0031_session_mode_plan"),
    ]

    operations = [
        migrations.AlterField(
            model_name="luantiplanmaterializetransaction",
            name="group",
            field=models.ForeignKey(
                blank=True,
                help_text="Primär belastete Gruppe bei der Velo-Abbuchung (nicht zwingend Verkaufsguthaben).",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="luanti_plan_materialize_txs",
                to="api.group",
                verbose_name="Abbuchungs-Gruppe (primär)",
            ),
        ),
        migrations.AddField(
            model_name="luantiplanmaterializetransaction",
            name="credit_group",
            field=models.ForeignKey(
                blank=True,
                help_text="Gruppe, die Kaufguthaben für Verkauf nach Umwandlung erhielt (Actor oder Regional-TOP).",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="luanti_plan_materialize_credit_txs",
                to="api.group",
                verbose_name="Verkaufsguthaben-Gruppe",
            ),
        ),
    ]