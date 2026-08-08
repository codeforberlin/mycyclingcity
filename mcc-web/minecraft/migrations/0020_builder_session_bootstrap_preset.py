from django.db import migrations

from minecraft.rcon_preset_defaults import BUILDER_SESSION_BOOTSTRAP_PRESET


def create_builder_session_bootstrap_preset(apps, schema_editor):
    preset_model = apps.get_model("minecraft", "MinecraftRconPreset")
    preset_model.objects.update_or_create(
        slug=BUILDER_SESSION_BOOTSTRAP_PRESET["slug"],
        defaults={
            "name": BUILDER_SESSION_BOOTSTRAP_PRESET["name"],
            "category": BUILDER_SESSION_BOOTSTRAP_PRESET["category"],
            "sort_order": BUILDER_SESSION_BOOTSTRAP_PRESET["sort_order"],
            "description": BUILDER_SESSION_BOOTSTRAP_PRESET["description"],
            "commands": BUILDER_SESSION_BOOTSTRAP_PRESET["commands"],
            "enabled": True,
            "is_system": True,
            "requires_confirmation": False,
            "stop_on_error": True,
        },
    )


def remove_builder_session_bootstrap_preset(apps, schema_editor):
    preset_model = apps.get_model("minecraft", "MinecraftRconPreset")
    preset_model.objects.filter(slug=BUILDER_SESSION_BOOTSTRAP_PRESET["slug"]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("minecraft", "0019_alter_mcsession_options_and_more"),
    ]

    operations = [
        migrations.RunPython(
            create_builder_session_bootstrap_preset,
            remove_builder_session_bootstrap_preset,
        ),
    ]
