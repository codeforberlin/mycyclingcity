# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.db import migrations


def grant_transfer_group_velos(apps, schema_editor):
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")
    ContentType = apps.get_model("contenttypes", "ContentType")

    ct = ContentType.objects.filter(app_label="api", model="groupvelotransfer").first()
    if ct is None:
        return
    perm = Permission.objects.filter(
        content_type=ct, codename="transfer_group_velos"
    ).first()
    if perm is None:
        return
    for group_name in ("minecraft_admin", "mcc_operator", "Operatoren"):
        group = Group.objects.filter(name=group_name).first()
        if group is not None:
            group.permissions.add(perm)


def revoke_transfer_group_velos(apps, schema_editor):
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")
    ContentType = apps.get_model("contenttypes", "ContentType")

    ct = ContentType.objects.filter(app_label="api", model="groupvelotransfer").first()
    if ct is None:
        return
    perm = Permission.objects.filter(
        content_type=ct, codename="transfer_group_velos"
    ).first()
    if perm is None:
        return
    for group in Group.objects.filter(
        name__in=["minecraft_admin", "mcc_operator", "Operatoren"]
    ):
        group.permissions.remove(perm)


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0028_group_velo_transfer"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.RunPython(grant_transfer_group_velos, revoke_transfer_group_velos),
    ]
