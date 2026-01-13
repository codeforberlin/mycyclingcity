# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    generate_large_test_data.py
# @author  Roland Rutz

#
"""
Management command to generate large-scale test data for load testing.

This command generates test data files with multiple schools and classes
based on configuration templates.

Usage:
    python manage.py generate_large_test_data --scenario medium --output api/tests/test_data_medium.json
    python manage.py generate_large_test_data --schools 5 --classes 35 --output api/tests/test_data_large.json
"""

import json
import os
import random
from django.core.management.base import BaseCommand
from django.conf import settings
from decimal import Decimal
from datetime import datetime, timedelta
from django.utils import timezone


class Command(BaseCommand):
    help = 'Generate large-scale test data for load testing'

    def add_arguments(self, parser):
        parser.add_argument(
            '--scenario',
            type=str,
            choices=['small', 'medium', 'large', 'xlarge'],
            help='Predefined scenario to generate',
        )
        parser.add_argument(
            '--schools',
            type=int,
            help='Number of schools to generate',
        )
        parser.add_argument(
            '--classes',
            type=int,
            help='Total number of classes to generate (distributed across schools)',
        )
        parser.add_argument(
            '--output',
            type=str,
            default='api/tests/test_data_generated.json',
            help='Output file path (default: api/tests/test_data_generated.json)',
        )
        parser.add_argument(
            '--students-per-class',
            type=int,
            default=25,
            help='Number of students per class (default: 25)',
        )
        parser.add_argument(
            '--devices-per-class',
            type=int,
            default=3,
            help='Number of devices per class (default: 3)',
        )

    def handle(self, *args, **options):
        scenario = options.get('scenario')
        schools_count = options.get('schools')
        classes_count = options.get('classes')
        output_path = options['output']
        students_per_class = options['students_per_class']
        devices_per_class = options['devices_per_class']

        # Load template if scenario is specified
        if scenario:
            template_path = os.path.join(settings.BASE_DIR, 'api/tests/test_data_large_template.json')
            if os.path.exists(template_path):
                with open(template_path, 'r', encoding='utf-8') as f:
                    template = json.load(f)
                    scenario_config = template['scenarios'].get(scenario, {})
                    schools_count = scenario_config.get('schools', 2)
                    classes_per_school = scenario_config.get('classes_per_school', [])
                    if classes_per_school:
                        classes_count = sum(classes_per_school)
                    else:
                        classes_count = schools_count * 6  # Default: 6 classes per school

        if not schools_count or not classes_count:
            self.stdout.write(self.style.ERROR("Please specify --scenario or both --schools and --classes"))
            return

        self.stdout.write(self.style.NOTICE(f"Generating test data: {schools_count} schools, {classes_count} classes"))
        
        # Generate test data
        test_data = self.generate_test_data(
            schools_count, classes_count, students_per_class, devices_per_class
        )

        # Get absolute path
        if not os.path.isabs(output_path):
            output_path = os.path.join(settings.BASE_DIR, output_path)

        # Ensure directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Write to file
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(test_data, f, indent=2, ensure_ascii=False)

        self.stdout.write(self.style.SUCCESS(f"Test data generated: {output_path}"))
        self.stdout.write(f"  - {len(test_data['groups'])} groups")
        self.stdout.write(f"  - {len(test_data['players'])} players")
        self.stdout.write(f"  - {len(test_data['devices'])} devices")
        self.stdout.write(f"  - {len(test_data['mileage_updates'])} mileage updates")

    def generate_test_data(self, schools_count, classes_count, students_per_class, devices_per_class):
        """Generate test data structure."""
        groups = []
        players = []
        devices = []
        mileage_updates = []

        # Distribute classes across schools
        classes_per_school = self.distribute_classes(schools_count, classes_count)
        grade_levels = ["1", "2", "3", "4", "5", "6"]
        class_letters = ["a", "b", "c", "d", "e", "f", "g"]

        group_id = 1
        player_id = 1
        device_id = 1

        # Generate schools and classes
        for school_idx in range(schools_count):
            school_id = school_idx + 1
            school_name = f"Schule{school_id:02d}"
            
            # Create school group
            groups.append({
                "id": group_id,
                "group_type": "Schule",
                "name": school_name,
                "short_name": school_name,
                "is_visible": True,
                "parent": None,
                "distance_total": 0.0,
                "coins_total": 0
            })
            school_group_id = group_id
            group_id += 1

            # Generate classes for this school
            num_classes = classes_per_school[school_idx]
            class_idx = 0
            
            for grade in grade_levels:
                if class_idx >= num_classes:
                    break
                for letter in class_letters:
                    if class_idx >= num_classes:
                        break
                    
                    class_name = f"{grade}{letter}-{school_name}"
                    groups.append({
                        "id": group_id,
                        "group_type": "Klasse",
                        "name": class_name,
                        "short_name": f"{grade}{letter}",
                        "is_visible": True,
                        "parent": school_group_id,
                        "distance_total": 0.0,
                        "coins_total": 0
                    })
                    class_group_id = group_id
                    group_id += 1

                    # Generate students for this class
                    for student_idx in range(students_per_class):
                        user_id = f"student-{school_id:02d}-{class_group_id:02d}-{student_idx+1:02d}"
                        id_tag = f"tag-{school_id:02d}-{class_group_id:02d}-{student_idx+1:02d}"
                        
                        players.append({
                            "id": player_id,
                            "user_id": user_id,
                            "id_tag": id_tag,
                            "is_visible": True,
                            "group_ids": [class_group_id],
                            "distance_total": 0.0,
                            "coins_total": 0
                        })
                        player_id += 1

                    # Generate devices for this class
                    for device_idx in range(devices_per_class):
                        device_name = f"device-{school_id:02d}-{class_group_id:02d}-{device_idx+1:01d}"
                        devices.append({
                            "id": device_id,
                            "name": device_name,
                            "display_name": f"Device {school_id}-{class_group_id}-{device_idx+1}",
                            "is_visible": True,
                            "group_id": class_group_id,
                            "distance_total": 0.0
                        })
                        device_id += 1

                    class_idx += 1

        # Generate mileage updates
        now = timezone.now()
        for day_offset in range(-30, 1):  # Last 30 days
            for update_idx in range(10):  # 10 updates per day
                # Random player and device
                player = random.choice(players)
                device = random.choice(devices)
                
                # Ensure device belongs to same group as player
                player_group_id = player['group_ids'][0]
                device_group_id = device['group_id']
                if device_group_id != player_group_id:
                    # Find device from same group
                    matching_devices = [d for d in devices if d['group_id'] == player_group_id]
                    if matching_devices:
                        device = random.choice(matching_devices)
                    else:
                        continue  # Skip if no matching device

                # Random distance
                distance = round(random.uniform(0.5, 15.0), 1)
                
                # Random hour within the day
                hour_offset = random.randint(0, 23)
                
                mileage_updates.append({
                    "player_id": player['id'],
                    "device_id": device['id'],
                    "distance_delta": distance,
                    "timestamp_offset_hours": day_offset * 24 + hour_offset - now.hour
                })

        return {
            "groups": groups,
            "players": players,
            "devices": devices,
            "mileage_updates": mileage_updates,
            "expected_results": {
                "_note": "Expected results should be calculated after loading test data"
            }
        }

    def distribute_classes(self, schools_count, classes_count):
        """Distribute classes evenly across schools."""
        base_classes = classes_count // schools_count
        remainder = classes_count % schools_count
        
        distribution = [base_classes] * schools_count
        for i in range(remainder):
            distribution[i] += 1
        
        return distribution

