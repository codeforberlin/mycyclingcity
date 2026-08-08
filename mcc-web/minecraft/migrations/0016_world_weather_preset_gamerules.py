from django.db import migrations

from minecraft.rcon_preset_defaults import WORLD_WEATHER_PRESETS


def update_world_weather_presets(apps, schema_editor):
    preset_model = apps.get_model("minecraft", "MinecraftRconPreset")
    for slug, data in WORLD_WEATHER_PRESETS.items():
        preset_model.objects.filter(slug=slug).update(
            description=data["description"],
            commands=data["commands"],
        )


def revert_world_weather_presets(apps, schema_editor):
    preset_model = apps.get_model("minecraft", "MinecraftRconPreset")
    legacy = {
        "day-clear": {
            "description": "Heller Tag, klares Wetter, Tageszyklus pausiert.",
            "commands": ["time set day", "weather clear", "gamerule doDaylightCycle false"],
        },
        "day-cycle": {
            "description": "Tag, klares Wetter, Tageszyklus läuft weiter.",
            "commands": ["time set day", "weather clear", "gamerule doDaylightCycle true"],
        },
        "noon": {
            "description": "Mittagshelligkeit für Screenshots und Präsentationen.",
            "commands": ["time set noon", "weather clear", "gamerule doDaylightCycle false"],
        },
        "night": {
            "description": "Nacht, klares Wetter, Tageszyklus pausiert.",
            "commands": ["time set night", "weather clear", "gamerule doDaylightCycle false"],
        },
    }
    for slug, data in legacy.items():
        preset_model.objects.filter(slug=slug).update(
            description=data["description"],
            commands=data["commands"],
        )


class Migration(migrations.Migration):

    dependencies = [
        ("minecraft", "0015_account_session_duration_fields"),
    ]

    operations = [
        migrations.RunPython(update_world_weather_presets, revert_world_weather_presets),
    ]
