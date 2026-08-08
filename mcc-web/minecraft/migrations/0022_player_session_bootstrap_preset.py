from django.db import migrations

from minecraft.rcon_preset_defaults import PLAYER_SESSION_BOOTSTRAP_PRESET


def create_player_session_bootstrap_preset(apps, schema_editor):
    preset_model = apps.get_model("minecraft", "MinecraftRconPreset")
    preset_model.objects.update_or_create(
        slug=PLAYER_SESSION_BOOTSTRAP_PRESET["slug"],
        defaults={
            "name": PLAYER_SESSION_BOOTSTRAP_PRESET["name"],
            "category": PLAYER_SESSION_BOOTSTRAP_PRESET["category"],
            "sort_order": PLAYER_SESSION_BOOTSTRAP_PRESET["sort_order"],
            "description": PLAYER_SESSION_BOOTSTRAP_PRESET["description"],
            "commands": PLAYER_SESSION_BOOTSTRAP_PRESET["commands"],
            "enabled": True,
            "is_system": True,
            "requires_confirmation": False,
            "stop_on_error": True,
        },
    )


def remove_player_session_bootstrap_preset(apps, schema_editor):
    preset_model = apps.get_model("minecraft", "MinecraftRconPreset")
    preset_model.objects.filter(slug=PLAYER_SESSION_BOOTSTRAP_PRESET["slug"]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("minecraft", "0021_session_waitlist"),
    ]

    operations = [
        migrations.RunPython(
            create_player_session_bootstrap_preset,
            remove_player_session_bootstrap_preset,
        ),
    ]
