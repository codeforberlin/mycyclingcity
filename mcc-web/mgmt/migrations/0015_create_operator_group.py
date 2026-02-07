# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    0015_create_operator_group.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

# Generated migration to create Operator user group and assign permissions
# This migration creates the "Operatoren" group with all necessary permissions
# for operators to manage their assigned TOP-Groups and related data.

from django.db import migrations


def create_operator_group(apps, schema_editor):
    """
    Create Operator user group and assign permissions.
    
    This function replicates the logic from mgmt/management/commands/setup_operator_group.py
    but uses historical models from apps.get_model() for migration compatibility.
    """
    # Get historical models
    AuthGroup = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    ContentType = apps.get_model('contenttypes', 'ContentType')
    
    # Get all required models
    ApiGroup = apps.get_model('api', 'Group')
    Cyclist = apps.get_model('api', 'Cyclist')
    TravelTrack = apps.get_model('api', 'TravelTrack')
    Milestone = apps.get_model('api', 'Milestone')
    GroupTravelStatus = apps.get_model('api', 'GroupTravelStatus')
    TravelHistory = apps.get_model('api', 'TravelHistory')
    GroupMilestoneAchievement = apps.get_model('api', 'GroupMilestoneAchievement')
    
    Event = apps.get_model('eventboard', 'Event')
    EventHistory = apps.get_model('eventboard', 'EventHistory')
    GroupEventStatus = apps.get_model('eventboard', 'GroupEventStatus')
    
    KioskDevice = apps.get_model('kiosk', 'KioskDevice')
    KioskPlaylistEntry = apps.get_model('kiosk', 'KioskPlaylistEntry')
    
    # Create or get the Operator group
    group, created = AuthGroup.objects.get_or_create(name='Operatoren')
    
    # Clear existing permissions (in case of re-run)
    group.permissions.clear()
    
    # Define permissions to assign
    permissions_to_assign = []
    
    # Helper function to get permission safely
    def get_permission(model, codename):
        """Get permission for a model, return None if not found."""
        try:
            content_type = ContentType.objects.get_for_model(model)
            return Permission.objects.get(codename=codename, content_type=content_type)
        except (Permission.DoesNotExist, ContentType.DoesNotExist):
            return None
    
    # Group permissions (api.models.Group, not django.contrib.auth.models.Group)
    for codename in ['add_group', 'change_group', 'delete_group', 'view_group']:
        perm = get_permission(ApiGroup, codename)
        if perm:
            permissions_to_assign.append(perm)
    
    # Cyclist permissions
    for codename in ['add_cyclist', 'change_cyclist', 'delete_cyclist', 'view_cyclist']:
        perm = get_permission(Cyclist, codename)
        if perm:
            permissions_to_assign.append(perm)
    
    # TravelTrack permissions
    for codename in ['add_traveltrack', 'change_traveltrack', 'delete_traveltrack', 'view_traveltrack']:
        perm = get_permission(TravelTrack, codename)
        if perm:
            permissions_to_assign.append(perm)
    
    # Milestone permissions
    for codename in ['add_milestone', 'change_milestone', 'delete_milestone', 'view_milestone']:
        perm = get_permission(Milestone, codename)
        if perm:
            permissions_to_assign.append(perm)
    
    # GroupTravelStatus permissions
    for codename in ['add_grouptravelstatus', 'change_grouptravelstatus', 'delete_grouptravelstatus', 'view_grouptravelstatus']:
        perm = get_permission(GroupTravelStatus, codename)
        if perm:
            permissions_to_assign.append(perm)
    
    # TravelHistory permissions (view only)
    perm = get_permission(TravelHistory, 'view_travelhistory')
    if perm:
        permissions_to_assign.append(perm)
    
    # GroupMilestoneAchievement permissions (view and change)
    for codename in ['view_groupmilestoneachievement', 'change_groupmilestoneachievement']:
        perm = get_permission(GroupMilestoneAchievement, codename)
        if perm:
            permissions_to_assign.append(perm)
    
    # Event permissions
    for codename in ['add_event', 'change_event', 'delete_event', 'view_event']:
        perm = get_permission(Event, codename)
        if perm:
            permissions_to_assign.append(perm)
    
    # GroupEventStatus permissions
    for codename in ['add_groupeventstatus', 'change_groupeventstatus', 'delete_groupeventstatus', 'view_groupeventstatus']:
        perm = get_permission(GroupEventStatus, codename)
        if perm:
            permissions_to_assign.append(perm)
    
    # EventHistory permissions (view only)
    perm = get_permission(EventHistory, 'view_eventhistory')
    if perm:
        permissions_to_assign.append(perm)
    
    # KioskDevice permissions
    for codename in ['add_kioskdevice', 'change_kioskdevice', 'delete_kioskdevice', 'view_kioskdevice']:
        perm = get_permission(KioskDevice, codename)
        if perm:
            permissions_to_assign.append(perm)
    
    # KioskPlaylistEntry permissions
    for codename in ['add_kioskplaylistentry', 'change_kioskplaylistentry', 'delete_kioskplaylistentry', 'view_kioskplaylistentry']:
        perm = get_permission(KioskPlaylistEntry, codename)
        if perm:
            permissions_to_assign.append(perm)
    
    # Assign all permissions
    group.permissions.set(permissions_to_assign)


def reverse_create_operator_group(apps, schema_editor):
    """Remove Operator group."""
    AuthGroup = apps.get_model('auth', 'Group')
    AuthGroup.objects.filter(name='Operatoren').delete()


class Migration(migrations.Migration):

    dependencies = [
        # ContentTypes and Permissions must exist
        ('contenttypes', '0001_initial'),
        ('auth', '0001_initial'),
        # All model migrations must be complete
        ('api', '0012_delete_event_delete_eventhistory_and_more'),  # After api models are migrated
        ('eventboard', '0001_initial'),  # After eventboard models are migrated
        ('kiosk', '0003_alter_kioskdevice_brightness_and_more'),  # After kiosk models are migrated
        ('mgmt', '0014_alter_alertrule_alert_type_alter_alertrule_is_active_and_more'),  # After latest mgmt migration
    ]

    operations = [
        migrations.RunPython(
            create_operator_group,
            reverse_create_operator_group,
        ),
    ]
