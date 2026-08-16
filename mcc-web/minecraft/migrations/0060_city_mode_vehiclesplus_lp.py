from django.db import migrations

from minecraft.rcon_preset_defaults import (
    BUILDER_SESSION_BOOTSTRAP_PRESET,
    CITY_MODE_PRESET,
    PLAYER_SESSION_BOOTSTRAP_PRESET,
)


def _upsert(preset_model, preset: dict, *, is_system: bool = False) -> None:
    defaults = {
        "name": preset["name"],
        "category": preset["category"],
        "sort_order": preset["sort_order"],
        "description": preset["description"],
        "commands": preset["commands"],
        "enabled": True,
    }
    if is_system:
        defaults.update(
            {
                "is_system": True,
                "requires_confirmation": False,
                "stop_on_error": True,
            }
        )
    preset_model.objects.update_or_create(slug=preset["slug"], defaults=defaults)


def update_presets(apps, schema_editor):
    preset_model = apps.get_model("minecraft", "MinecraftRconPreset")
    _upsert(preset_model, CITY_MODE_PRESET, is_system=False)
    _upsert(preset_model, BUILDER_SESSION_BOOTSTRAP_PRESET, is_system=True)
    _upsert(preset_model, PLAYER_SESSION_BOOTSTRAP_PRESET, is_system=True)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("minecraft", "0059_city_mode_vehiclesplus_wg_flags"),
    ]

    operations = [
        migrations.RunPython(update_presets, noop_reverse),
    ]
