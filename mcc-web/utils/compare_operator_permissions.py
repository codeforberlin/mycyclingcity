#!/usr/bin/env python3
# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Script to extract and compare Operator permissions from migration and production database
# Usage: python utils/compare_operator_permissions.py

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType


def get_permissions_from_migration():
    """Extract expected permissions from migration 0015_create_operator_group.py"""
    # These are the permissions defined in the migration
    expected_permissions = {
        'api.group': ['add_group', 'change_group', 'delete_group', 'view_group'],
        'api.cyclist': ['add_cyclist', 'change_cyclist', 'delete_cyclist', 'view_cyclist'],
        'api.traveltrack': ['add_traveltrack', 'change_traveltrack', 'delete_traveltrack', 'view_traveltrack'],
        'api.milestone': ['add_milestone', 'change_milestone', 'delete_milestone', 'view_milestone'],
        'api.grouptravelstatus': ['add_grouptravelstatus', 'change_grouptravelstatus', 'delete_grouptravelstatus', 'view_grouptravelstatus'],
        'api.travelhistory': ['view_travelhistory'],
        'api.groupmilestoneachievement': ['view_groupmilestoneachievement', 'change_groupmilestoneachievement'],
        'eventboard.event': ['add_event', 'change_event', 'delete_event', 'view_event'],
        'eventboard.groupeventstatus': ['add_groupeventstatus', 'change_groupeventstatus', 'delete_groupeventstatus', 'view_groupeventstatus'],
        'eventboard.eventhistory': ['view_eventhistory', 'delete_eventhistory'],
        'kiosk.kioskdevice': ['add_kioskdevice', 'change_kioskdevice', 'delete_kioskdevice', 'view_kioskdevice'],
        'kiosk.kioskplaylistentry': ['add_kioskplaylistentry', 'change_kioskplaylistentry', 'delete_kioskplaylistentry', 'view_kioskplaylistentry'],
    }
    return expected_permissions


def get_permissions_from_database():
    """Get actual permissions from database"""
    try:
        group = Group.objects.get(name='Operatoren')
        
        # Group by model
        from collections import defaultdict
        by_model = defaultdict(list)
        
        for perm in group.permissions.all().order_by('content_type__app_label', 'content_type__model', 'codename'):
            key = f'{perm.content_type.app_label}.{perm.content_type.model}'
            by_model[key].append(perm.codename)
        
        # Convert to dict with sorted lists
        result = {}
        for model in sorted(by_model.keys()):
            result[model] = sorted(by_model[model])
        
        return result, group.permissions.count()
    except Group.DoesNotExist:
        return None, 0


def compare_permissions(expected, actual):
    """Compare expected and actual permissions"""
    print("=" * 70)
    print("PERMISSION COMPARISON")
    print("=" * 70)
    
    if actual is None:
        print("\n❌ Operatoren group does not exist in database!")
        return False
    
    all_models = set(expected.keys()) | set(actual.keys())
    
    missing_in_db = []
    extra_in_db = []
    differences = []
    
    for model in sorted(all_models):
        expected_perms = set(expected.get(model, []))
        actual_perms = set(actual.get(model, []))
        
        if model not in actual:
            missing_in_db.append(model)
            print(f"\n❌ Model {model} missing in database")
            print(f"   Expected: {sorted(expected_perms)}")
        elif model not in expected:
            extra_in_db.append(model)
            print(f"\n⚠️  Model {model} exists in database but not in migration")
            print(f"   Found: {sorted(actual_perms)}")
        elif expected_perms != actual_perms:
            differences.append(model)
            missing = expected_perms - actual_perms
            extra = actual_perms - expected_perms
            if missing:
                print(f"\n❌ Model {model} missing permissions: {sorted(missing)}")
            if extra:
                print(f"\n⚠️  Model {model} has extra permissions: {sorted(extra)}")
        else:
            print(f"\n✓ Model {model}: OK ({len(expected_perms)} permissions)")
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    if not missing_in_db and not extra_in_db and not differences:
        print("✅ All permissions match!")
        return True
    else:
        if missing_in_db:
            print(f"❌ Missing models in database: {missing_in_db}")
        if extra_in_db:
            print(f"⚠️  Extra models in database: {extra_in_db}")
        if differences:
            print(f"⚠️  Permission differences in: {differences}")
        return False


def main():
    print("=" * 70)
    print("OPERATOR PERMISSIONS COMPARISON")
    print("=" * 70)
    
    # Get expected permissions from migration
    print("\n[1] Extracting expected permissions from migration 0015_create_operator_group.py...")
    expected = get_permissions_from_migration()
    
    total_expected = sum(len(perms) for perms in expected.values())
    print(f"   Found {len(expected)} models with {total_expected} total permissions")
    
    # Get actual permissions from database
    print("\n[2] Reading actual permissions from database...")
    actual, actual_count = get_permissions_from_database()
    
    if actual is None:
        print("   ❌ Operatoren group not found in database")
        print("\n   Expected permissions from migration:")
        for model, perms in sorted(expected.items()):
            print(f"     {model}: {perms}")
        return 1
    
    print(f"   Found {len(actual)} models with {actual_count} total permissions")
    
    # Compare
    print("\n[3] Comparing permissions...")
    match = compare_permissions(expected, actual)
    
    if not match:
        print("\n⚠️  Differences found! Please review the migration.")
        return 1
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
