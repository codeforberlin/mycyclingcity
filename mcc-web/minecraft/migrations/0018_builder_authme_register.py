from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("minecraft", "0017_player_session_active_hint"),
    ]

    operations = [
        migrations.AddField(
            model_name="minecraftteamregistration",
            name="authme_is_registered",
            field=models.BooleanField(
                default=False,
                help_text="AuthMe-Account wurde per RCON registriert",
                verbose_name="Auf MC-Server angelegt",
            ),
        ),
        migrations.AddField(
            model_name="minecraftteamregistration",
            name="authme_last_error",
            field=models.TextField(blank=True, verbose_name="Letzter MC-Registrierungsfehler"),
        ),
        migrations.AddField(
            model_name="minecraftteamregistration",
            name="authme_registered_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="MC-Registrierung am",
            ),
        ),
    ]
