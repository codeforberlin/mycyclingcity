from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("minecraft", "0016_world_weather_preset_gamerules"),
    ]

    operations = [
        migrations.AddField(
            model_name="minecraftintegrationconfig",
            name="player_session_active_hint",
            field=models.CharField(
                blank=True,
                default="⚠️ FEZitty-Pass eingesammelt?",
                help_text="Gelber Hinweis auf dem Spieler-Sessions-Dashboard bei laufender Session. Leer lassen = Hinweis ausblenden.",
                max_length=200,
                verbose_name="Hinweis aktive Spieler-Session",
            ),
        ),
    ]
