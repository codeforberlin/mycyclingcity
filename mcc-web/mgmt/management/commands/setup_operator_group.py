# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    setup_operator_group.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

"""
Management command to create the Operator user group and assign permissions.

This command creates a Django user group called "Operatoren" and assigns
all necessary permissions for operators to manage their assigned TOP-Groups
and related data.

Usage:
    python manage.py setup_operator_group
"""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group as AuthGroup, Permission
from django.contrib.contenttypes.models import ContentType
from api.models import (
    Group as ApiGroup, Cyclist, TravelTrack, Milestone, GroupTravelStatus,
    TravelHistory, GroupMilestoneAchievement
)
from eventboard.models import Event, EventHistory, GroupEventStatus
from kiosk.models import KioskDevice, KioskPlaylistEntry
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Create Operator user group and assign permissions'

    def handle(self, *args, **options):
        """Create the Operator group and assign permissions."""
        
        # Create or get the Operator group (Django auth Group, not api Group)
        group, created = AuthGroup.objects.get_or_create(name='Operatoren')
        
        if created:
            self.stdout.write(self.style.SUCCESS('Created Operator group "Operatoren"'))
        else:
            self.stdout.write(self.style.WARNING('Operator group "Operatoren" already exists'))
        
        # Clear existing permissions (in case of re-run)
        group.permissions.clear()
        
        # Define permissions to assign
        permissions_to_assign = []
        
        # Group permissions (api.models.Group, not django.contrib.auth.models.Group)
        permissions_to_assign.extend([
            Permission.objects.get(codename='add_group', content_type=ContentType.objects.get_for_model(ApiGroup)),
            Permission.objects.get(codename='change_group', content_type=ContentType.objects.get_for_model(ApiGroup)),
            Permission.objects.get(codename='delete_group', content_type=ContentType.objects.get_for_model(ApiGroup)),
            Permission.objects.get(codename='view_group', content_type=ContentType.objects.get_for_model(ApiGroup)),
        ])
        
        # Cyclist permissions
        permissions_to_assign.extend([
            Permission.objects.get(codename='add_cyclist', content_type=ContentType.objects.get_for_model(Cyclist)),
            Permission.objects.get(codename='change_cyclist', content_type=ContentType.objects.get_for_model(Cyclist)),
            Permission.objects.get(codename='delete_cyclist', content_type=ContentType.objects.get_for_model(Cyclist)),
            Permission.objects.get(codename='view_cyclist', content_type=ContentType.objects.get_for_model(Cyclist)),
        ])
        
        # TravelTrack permissions
        permissions_to_assign.extend([
            Permission.objects.get(codename='add_traveltrack', content_type=ContentType.objects.get_for_model(TravelTrack)),
            Permission.objects.get(codename='change_traveltrack', content_type=ContentType.objects.get_for_model(TravelTrack)),
            Permission.objects.get(codename='delete_traveltrack', content_type=ContentType.objects.get_for_model(TravelTrack)),
            Permission.objects.get(codename='view_traveltrack', content_type=ContentType.objects.get_for_model(TravelTrack)),
        ])
        
        # Milestone permissions
        permissions_to_assign.extend([
            Permission.objects.get(codename='add_milestone', content_type=ContentType.objects.get_for_model(Milestone)),
            Permission.objects.get(codename='change_milestone', content_type=ContentType.objects.get_for_model(Milestone)),
            Permission.objects.get(codename='delete_milestone', content_type=ContentType.objects.get_for_model(Milestone)),
            Permission.objects.get(codename='view_milestone', content_type=ContentType.objects.get_for_model(Milestone)),
        ])
        
        # GroupTravelStatus permissions
        permissions_to_assign.extend([
            Permission.objects.get(codename='add_grouptravelstatus', content_type=ContentType.objects.get_for_model(GroupTravelStatus)),
            Permission.objects.get(codename='change_grouptravelstatus', content_type=ContentType.objects.get_for_model(GroupTravelStatus)),
            Permission.objects.get(codename='delete_grouptravelstatus', content_type=ContentType.objects.get_for_model(GroupTravelStatus)),
            Permission.objects.get(codename='view_grouptravelstatus', content_type=ContentType.objects.get_for_model(GroupTravelStatus)),
        ])
        
        # TravelHistory permissions (view only)
        permissions_to_assign.extend([
            Permission.objects.get(codename='view_travelhistory', content_type=ContentType.objects.get_for_model(TravelHistory)),
        ])
        
        # GroupMilestoneAchievement permissions (view and change)
        permissions_to_assign.extend([
            Permission.objects.get(codename='view_groupmilestoneachievement', content_type=ContentType.objects.get_for_model(GroupMilestoneAchievement)),
            Permission.objects.get(codename='change_groupmilestoneachievement', content_type=ContentType.objects.get_for_model(GroupMilestoneAchievement)),
        ])
        
        # Event permissions
        permissions_to_assign.extend([
            Permission.objects.get(codename='add_event', content_type=ContentType.objects.get_for_model(Event)),
            Permission.objects.get(codename='change_event', content_type=ContentType.objects.get_for_model(Event)),
            Permission.objects.get(codename='delete_event', content_type=ContentType.objects.get_for_model(Event)),
            Permission.objects.get(codename='view_event', content_type=ContentType.objects.get_for_model(Event)),
        ])
        
        # GroupEventStatus permissions
        permissions_to_assign.extend([
            Permission.objects.get(codename='add_groupeventstatus', content_type=ContentType.objects.get_for_model(GroupEventStatus)),
            Permission.objects.get(codename='change_groupeventstatus', content_type=ContentType.objects.get_for_model(GroupEventStatus)),
            Permission.objects.get(codename='delete_groupeventstatus', content_type=ContentType.objects.get_for_model(GroupEventStatus)),
            Permission.objects.get(codename='view_groupeventstatus', content_type=ContentType.objects.get_for_model(GroupEventStatus)),
        ])
        
        # EventHistory permissions (view and delete)
        permissions_to_assign.extend([
            Permission.objects.get(codename='view_eventhistory', content_type=ContentType.objects.get_for_model(EventHistory)),
            Permission.objects.get(codename='delete_eventhistory', content_type=ContentType.objects.get_for_model(EventHistory)),
        ])
        
        # KioskDevice permissions
        permissions_to_assign.extend([
            Permission.objects.get(codename='add_kioskdevice', content_type=ContentType.objects.get_for_model(KioskDevice)),
            Permission.objects.get(codename='change_kioskdevice', content_type=ContentType.objects.get_for_model(KioskDevice)),
            Permission.objects.get(codename='delete_kioskdevice', content_type=ContentType.objects.get_for_model(KioskDevice)),
            Permission.objects.get(codename='view_kioskdevice', content_type=ContentType.objects.get_for_model(KioskDevice)),
        ])
        
        # KioskPlaylistEntry permissions
        permissions_to_assign.extend([
            Permission.objects.get(codename='add_kioskplaylistentry', content_type=ContentType.objects.get_for_model(KioskPlaylistEntry)),
            Permission.objects.get(codename='change_kioskplaylistentry', content_type=ContentType.objects.get_for_model(KioskPlaylistEntry)),
            Permission.objects.get(codename='delete_kioskplaylistentry', content_type=ContentType.objects.get_for_model(KioskPlaylistEntry)),
            Permission.objects.get(codename='view_kioskplaylistentry', content_type=ContentType.objects.get_for_model(KioskPlaylistEntry)),
        ])
        
        # Assign all permissions
        group.permissions.set(permissions_to_assign)
        
        self.stdout.write(self.style.SUCCESS(
            f'Successfully assigned {len(permissions_to_assign)} permissions to Operator group'
        ))
        
        # Display summary
        self.stdout.write(self.style.SUCCESS('\nOperator group setup complete!'))
        self.stdout.write(self.style.SUCCESS('\nTo assign a user as operator:'))
        self.stdout.write(self.style.SUCCESS('  1. Create or select a user'))
        self.stdout.write(self.style.SUCCESS('  2. Set is_staff=True'))
        self.stdout.write(self.style.SUCCESS('  3. Add user to "Operatoren" group'))
        self.stdout.write(self.style.SUCCESS('  4. Assign user as manager to a TOP-Group (via Group.managers field)'))
