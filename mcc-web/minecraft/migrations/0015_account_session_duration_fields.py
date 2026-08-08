# Generated manually for per-account session duration settings.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("minecraft", "0014_play_account_authme_register"),
    ]

    operations = [
        migrations.AddField(
            model_name="minecraftplayaccount",
            name="add_time_minutes",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Leer = globaler Standard (MCC_MINECRAFT_SESSION_ADD_MINUTES)",
                null=True,
                verbose_name="Zeit hinzufügen (Min.)",
            ),
        ),
        migrations.AddField(
            model_name="minecraftplayaccount",
            name="session_duration_minutes",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Leer = globaler Standard (MCC_MINECRAFT_PLAYER_SESSION_MINUTES)",
                null=True,
                verbose_name="Session-Dauer (Min.)",
            ),
        ),
        migrations.AddField(
            model_name="minecraftteamregistration",
            name="add_time_minutes",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Leer = globaler Standard (MCC_MINECRAFT_SESSION_ADD_MINUTES)",
                null=True,
                verbose_name="Zeit hinzufügen (Min.)",
            ),
        ),
        migrations.AddField(
            model_name="minecraftteamregistration",
            name="session_duration_minutes",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Leer = globaler Standard (MCC_MINECRAFT_BUILDER_SESSION_MINUTES)",
                null=True,
                verbose_name="Session-Dauer (Min.)",
            ),
        ),
        migrations.CreateModel(
            name="MinecraftBuilderAccount",
            fields=[],
            options={
                "verbose_name": "Bau Account",
                "verbose_name_plural": "Bau Accounts",
                "proxy": True,
                "indexes": [],
                "constraints": [],
            },
            bases=("minecraft.minecraftteamregistration",),
        ),
        migrations.AlterModelOptions(
            name="minecraftplayaccount",
            options={
                "ordering": ["sort_order", "short_name"],
                "verbose_name": "Play Account",
                "verbose_name_plural": "Play Accounts",
            },
        ),
    ]
