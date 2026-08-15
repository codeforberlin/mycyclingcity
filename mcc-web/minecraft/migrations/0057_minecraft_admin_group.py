# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.db import migrations


def create_minecraft_admin_group(apps, schema_editor):
    """Ensure minecraft_admin exists with full Minecraft menu permissions."""
    from minecraft.services.preset_groups import sync_minecraft_preset_groups

    sync_minecraft_preset_groups(clear_existing=True)


def remove_minecraft_admin_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name="minecraft_admin").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("minecraft", "0056_session_unlimited"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(create_minecraft_admin_group, remove_minecraft_admin_group),
    ]
