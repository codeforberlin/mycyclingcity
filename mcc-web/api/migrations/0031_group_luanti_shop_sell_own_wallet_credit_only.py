# Generated manually for Luanti shop sell restriction on TOP groups.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0030_yearend_snapshot_spendable"),
    ]

    operations = [
        migrations.AddField(
            model_name="group",
            name="luanti_shop_sell_own_wallet_credit_only",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Nur für TOP-Gruppen: Kind-Gruppen dürfen im Luanti-Shop Blöcke "
                    "nur zurückverkaufen, wenn Kaufguthaben auf ihrer eigenen Shop-Wallet liegt "
                    "(nicht TOP-Pool)."
                ),
                verbose_name="Luanti: Verkauf nur eigenes Kaufguthaben (TOP)",
            ),
        ),
    ]