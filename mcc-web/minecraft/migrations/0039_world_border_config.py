# Generated manually for World Border admin fields

from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("minecraft", "0038_builder_default_adventure_help"),
    ]

    operations = [
        migrations.AddField(
            model_name="minecraftintegrationconfig",
            name="world_border_center_x",
            field=models.FloatField(default=0.0, verbose_name="Border-Zentrum X"),
        ),
        migrations.AddField(
            model_name="minecraftintegrationconfig",
            name="world_border_center_z",
            field=models.FloatField(default=0.0, verbose_name="Border-Zentrum Z"),
        ),
        migrations.AddField(
            model_name="minecraftintegrationconfig",
            name="world_border_damage_amount",
            field=models.FloatField(
                default=0.2,
                help_text=(
                    "Vanilla worldborder damage amount. 0 = praktisch kein Schaden "
                    "(Spieler werden weiterhin zurückgeschoben)."
                ),
                verbose_name="Schaden pro Sekunde",
            ),
        ),
        migrations.AddField(
            model_name="minecraftintegrationconfig",
            name="world_border_enabled",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "Wenn aktiv: „Anwenden“ setzt die konfigurierte Größe. "
                    "Wenn inaktiv bzw. „Deaktivieren“: Border auf Vanilla-Maximum."
                ),
                verbose_name="World Border aktiv",
            ),
        ),
        migrations.AddField(
            model_name="minecraftintegrationconfig",
            name="world_border_size",
            field=models.PositiveIntegerField(
                default=1000,
                help_text=(
                    "Durchmesser / Kantenlänge des quadratischen Bereichs "
                    "(1000 → ca. 1000×1000 Blöcke)."
                ),
                validators=[MinValueValidator(1)],
                verbose_name="Border-Größe (Blöcke)",
            ),
        ),
        migrations.AddField(
            model_name="minecraftintegrationconfig",
            name="world_border_warning_distance",
            field=models.PositiveIntegerField(
                default=5,
                help_text="Vanilla worldborder warning distance.",
                verbose_name="Warnung (Blöcke)",
            ),
        ),
    ]
