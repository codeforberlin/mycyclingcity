# Generated manually for plan live convert admin flag

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("luanti", "0029_luanti_plan_purchase_credit_granted"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="luantiprotectedregion",
            name="plan_live_convert_active",
            field=models.BooleanField(
                default=False,
                help_text="Server wandelt Hologramme fortlaufend um, sobald Plan-Pool-Velos (z. B. durch Radfahren) verfügbar sind — ohne /mccplan autoconvert ingame.",
                verbose_name="Live-Umwandlung aktiv",
            ),
        ),
        migrations.AddField(
            model_name="luantiprotectedregion",
            name="plan_live_convert_started_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="Live-Umwandlung gestartet am",
            ),
        ),
        migrations.AddField(
            model_name="luantiprotectedregion",
            name="plan_live_convert_started_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Live-Umwandlung gestartet von",
            ),
        ),
    ]
