# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    fix_device_group_assignments.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

"""
Management command to fix device group assignments.

This command updates all devices in the database so that they are assigned
to top-level groups (schools) only, not to subgroups (classes).

Devices can be used by multiple classes, so they should only be assigned
to the top-level parent group (school).

Usage:
    python manage.py fix_device_group_assignments
    python manage.py fix_device_group_assignments --dry-run  # Preview changes only
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from api.models import Group
from iot.models import Device
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Fix device group assignments to use top-level groups only'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview changes without applying them',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be saved'))
        
        # Get all devices with group assignments
        devices = Device.objects.filter(group__isnull=False).select_related('group')
        
        updated_count = 0
        skipped_count = 0
        error_count = 0
        
        self.stdout.write(f"Found {devices.count()} devices with group assignments")
        
        with transaction.atomic():
            for device in devices:
                current_group = device.group
                
                # Check if device is already assigned to a top-level group
                if current_group.parent is None:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"✓ Device '{device.name}' already assigned to top-level group '{current_group.name}'"
                        )
                    )
                    skipped_count += 1
                    continue
                
                # Find the top-level parent group
                top_parent = current_group
                visited = set()
                while top_parent.parent and top_parent.id not in visited:
                    visited.add(top_parent.id)
                    top_parent = top_parent.parent
                
                if top_parent.parent is not None:
                    self.stdout.write(
                        self.style.ERROR(
                            f"✗ Device '{device.name}': Could not find top-level parent for group '{current_group.name}'"
                        )
                    )
                    error_count += 1
                    continue
                
                # Update device assignment
                if not dry_run:
                    device.group = top_parent
                    device.save()
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f"{'[DRY RUN] ' if dry_run else ''}✓ Device '{device.name}': "
                        f"'{current_group.name}' → '{top_parent.name}'"
                    )
                )
                updated_count += 1
        
        # Summary
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("Summary:")
        self.stdout.write(f"  Updated: {updated_count}")
        self.stdout.write(f"  Skipped (already correct): {skipped_count}")
        self.stdout.write(f"  Errors: {error_count}")
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    "\nThis was a dry run. Run without --dry-run to apply changes."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"\n✓ Successfully updated {updated_count} device group assignments"
                )
            )
