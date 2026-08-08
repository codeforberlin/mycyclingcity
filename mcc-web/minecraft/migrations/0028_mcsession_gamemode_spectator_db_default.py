# Database default for gamemode_spectator (SQLite NOT NULL safety)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("minecraft", "0027_session_spectator_toggle"),
    ]

    operations = [
        migrations.AlterField(
            model_name="mcsession",
            name="gamemode_spectator",
            field=models.BooleanField(
                db_default=False,
                default=False,
                help_text=(
                    "Aktueller Gamemode während der Session "
                    "(Toggle Adventure/Survival ↔ Spectator)."
                ),
                verbose_name="Spectator aktiv",
            ),
        ),
    ]
