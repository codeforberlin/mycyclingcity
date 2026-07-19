from django.db import migrations

from minecraft.rcon_preset_defaults import CITY_MODE_PRESET


def update_city_preset(apps, schema_editor):
    preset_model = apps.get_model("minecraft", "MinecraftRconPreset")
    preset_model.objects.update_or_create(
        slug=CITY_MODE_PRESET["slug"],
        defaults={
            "name": CITY_MODE_PRESET["name"],
            "category": CITY_MODE_PRESET["category"],
            "sort_order": CITY_MODE_PRESET["sort_order"],
            "description": CITY_MODE_PRESET["description"],
            "commands": CITY_MODE_PRESET["commands"],
            "enabled": True,
        },
    )


def revert_city_preset(apps, schema_editor):
    preset_model = apps.get_model("minecraft", "MinecraftRconPreset")
    preset_model.objects.filter(slug=CITY_MODE_PRESET["slug"]).update(
        description="Schützt Bauwerke: keine Mob-Zerstörung, kein Feuer, Inventar behalten.",
        commands=[
            "gamerule mobGriefing false",
            "gamerule doFireTick false",
            "gamerule keepInventory true",
        ],
    )


class Migration(migrations.Migration):

    dependencies = [
        ("minecraft", "0009_shop_item_unique_loc"),
    ]

    operations = [
        migrations.RunPython(update_city_preset, revert_city_preset),
    ]
