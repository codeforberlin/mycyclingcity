# Generated manually for cart_label_mode on arena motion settings.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("minecraft", "0025_run_arena_sim_permission"),
    ]

    operations = [
        migrations.AddField(
            model_name="minecraftarenamotionsettings",
            name="cart_label_mode",
            field=models.CharField(
                choices=[
                    ("name_only", "Nur Name (Status im HUD)"),
                    ("full", "Voll (Platz, km/h, Runden auf der Lore)"),
                ],
                default="name_only",
                max_length=16,
                verbose_name="Lore-Label-Modus",
            ),
        ),
    ]
