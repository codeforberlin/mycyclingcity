# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    0005_populate_group_types.py
# @author  Roland Rutz

#
from django.db import migrations


def populate_group_types(apps, schema_editor):
    """Create default GroupType entries: 'Schule' and 'Klasse'."""
    GroupType = apps.get_model('api', 'GroupType')
    
    # Create 'Schule' type
    GroupType.objects.get_or_create(
        name='Schule',
        defaults={
            'description': 'Übergeordnete Gruppe für Schulen',
            'is_active': True
        }
    )
    
    # Create 'Klasse' type
    GroupType.objects.get_or_create(
        name='Klasse',
        defaults={
            'description': 'Untergeordnete Gruppe für Klassen',
            'is_active': True
        }
    )


def reverse_populate_group_types(apps, schema_editor):
    """Remove default GroupType entries."""
    GroupType = apps.get_model('api', 'GroupType')
    GroupType.objects.filter(name__in=['Schule', 'Klasse']).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0004_add_group_type_model'),
    ]

    operations = [
        migrations.RunPython(populate_group_types, reverse_populate_group_types),
    ]
