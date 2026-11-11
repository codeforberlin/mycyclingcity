# Generated manually for plan materialize purchase credit idempotency.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("luanti", "0028_luanti_registered_item_plan_ghost"),
    ]

    operations = [
        migrations.AddField(
            model_name="luantiplanblock",
            name="purchase_credit_granted",
            field=models.BooleanField(
                default=False,
                verbose_name="Kaufguthaben nach Umwandlung gebucht",
            ),
        ),
    ]
