# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from decimal import Decimal

from django.db import migrations, models
from django.db.models import Sum


def backfill_distance_lifetime(apps, schema_editor):
    """Seed lifetime from max(period ledger, HourlyMetric sum)."""
    Device = apps.get_model("iot", "Device")
    HourlyMetric = apps.get_model("api", "HourlyMetric")
    zero = Decimal("0.00000")
    for device in Device.objects.all().iterator():
        period = device.distance_total or zero
        hm_sum = (
            HourlyMetric.objects.filter(device_id=device.pk).aggregate(s=Sum("distance_km"))["s"]
            or zero
        )
        lifetime = period if period >= hm_sum else hm_sum
        if device.distance_lifetime_km != lifetime:
            device.distance_lifetime_km = lifetime
            device.save(update_fields=["distance_lifetime_km"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("iot", "0016_device_arena_sim_allowed"),
        ("api", "0030_yearend_snapshot_spendable"),
    ]

    operations = [
        migrations.AddField(
            model_name="device",
            name="distance_lifetime_km",
            field=models.DecimalField(
                decimal_places=5,
                default=Decimal("0.00000"),
                help_text=(
                    "Kumulative KM der Station über alle Verleihe/Events. "
                    "Wird beim Ingest mitgeführt und bei Jahresabschluss nicht genullt."
                ),
                max_digits=15,
                verbose_name="Lebenslaufleistung (km)",
            ),
        ),
        migrations.AlterField(
            model_name="device",
            name="distance_total",
            field=models.DecimalField(
                decimal_places=5,
                default=Decimal("0.00000"),
                help_text="KM seit dem letzten Jahresabschluss/Reset. Wird bei Jahresabschluss genullt.",
                max_digits=15,
                verbose_name="Laufleistung Periode (km)",
            ),
        ),
        migrations.RunPython(backfill_distance_lifetime, noop_reverse),
    ]
