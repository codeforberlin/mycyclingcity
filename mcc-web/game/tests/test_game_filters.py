# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    test_game_filters.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

"""
Test suite for game filtering functionality.

Tests the filtering of cyclists and devices based on:
- Top-level groups (schools)
- Subgroups (classes)
- Search queries
"""

import pytest
from django.test import Client
from django.urls import reverse
from api.models import Group, Cyclist, GroupType
from iot.models import Device


@pytest.mark.django_db
class TestGameFilters:
    """Test suite for game filtering endpoints."""
    
    @pytest.fixture
    def client(self):
        """Create a test client."""
        return Client()
    
    @pytest.fixture
    def group_type(self):
        """Create a test group type."""
        return GroupType.objects.create(name="Schule")
    
    @pytest.fixture
    def top_groups(self, group_type):
        """Create test top-level groups (schools)."""
        school1 = Group.objects.create(
            name="Schule01",
            group_type=group_type,
            is_visible=True
        )
        school2 = Group.objects.create(
            name="Schule02",
            group_type=group_type,
            is_visible=True
        )
        return {'school1': school1, 'school2': school2}
    
    @pytest.fixture
    def subgroups(self, top_groups, group_type):
        """Create test subgroups (classes) for schools."""
        # Classes for Schule01
        class1a = Group.objects.create(
            name="Klasse 1a",
            group_type=group_type,
            parent=top_groups['school1'],
            is_visible=True
        )
        class1b = Group.objects.create(
            name="Klasse 1b",
            group_type=group_type,
            parent=top_groups['school1'],
            is_visible=True
        )
        # Classes for Schule02
        class2a = Group.objects.create(
            name="Klasse 2a",
            group_type=group_type,
            parent=top_groups['school2'],
            is_visible=True
        )
        return {
            'school1_class1a': class1a,
            'school1_class1b': class1b,
            'school2_class2a': class2a,
        }
    
    @pytest.fixture
    def cyclists(self, subgroups):
        """Create test cyclists assigned to different groups."""
        # Cyclists for Schule01 - Klasse 1a
        cyclist1 = Cyclist.objects.create(
            user_id="Max_Mustermann",
            id_tag="TAG001",
            is_visible=True
        )
        cyclist1.groups.add(subgroups['school1_class1a'])
        
        cyclist2 = Cyclist.objects.create(
            user_id="Lisa_Schmidt",
            id_tag="TAG002",
            is_visible=True
        )
        cyclist2.groups.add(subgroups['school1_class1a'])
        
        # Cyclist for Schule01 - Klasse 1b
        cyclist3 = Cyclist.objects.create(
            user_id="Tom_Weber",
            id_tag="TAG003",
            is_visible=True
        )
        cyclist3.groups.add(subgroups['school1_class1b'])
        
        # Cyclists for Schule02 - Klasse 2a
        cyclist4 = Cyclist.objects.create(
            user_id="Anna_Mueller",
            id_tag="TAG004",
            is_visible=True
        )
        cyclist4.groups.add(subgroups['school2_class2a'])
        
        cyclist5 = Cyclist.objects.create(
            user_id="Peter_Fischer",
            id_tag="TAG005",
            is_visible=True
        )
        cyclist5.groups.add(subgroups['school2_class2a'])
        
        return {
            'max': cyclist1,
            'lisa': cyclist2,
            'tom': cyclist3,
            'anna': cyclist4,
            'peter': cyclist5,
        }
    
    @pytest.fixture
    def devices(self):
        """Create test devices."""
        device1 = Device.objects.create(
            name="device001",
            display_name="Gerät 1",
            is_visible=True
        )
        device2 = Device.objects.create(
            name="device002",
            display_name="Gerät 2",
            is_visible=True
        )
        device3 = Device.objects.create(
            name="device003",
            display_name="Gerät 3",
            is_visible=True
        )
        return {
            'device1': device1,
            'device2': device2,
            'device3': device3,
        }
    
    def test_get_filtered_cyclists_no_filter(self, client, cyclists):
        """Test that all cyclists are returned when no filter is applied."""
        url = reverse('game:get_filtered_cyclists')
        response = client.get(url)
        
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        
        # Should contain all cyclists from all schools
        assert 'Max_Mustermann' in content
        assert 'Lisa_Schmidt' in content
        assert 'Tom_Weber' in content
        assert 'Anna_Mueller' in content
        assert 'Peter_Fischer' in content
    
    def test_get_filtered_cyclists_all_top_groups_explicit(self, client, cyclists, top_groups):
        """Test that all cyclists are returned when explicitly selecting 'Alle TOP-Gruppen' (empty top_group parameter)."""
        url = reverse('game:get_filtered_cyclists')
        # Explicitly pass empty top_group parameter (simulating "Alle TOP-Gruppen" selection)
        response = client.get(url, {'top_group': ''})
        
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        
        # Should contain ALL cyclists from ALL schools, not just the first one
        # Schule01 cyclists
        assert 'Max_Mustermann' in content, "Max_Mustermann (Schule01) should be in results"
        assert 'Lisa_Schmidt' in content, "Lisa_Schmidt (Schule01) should be in results"
        assert 'Tom_Weber' in content, "Tom_Weber (Schule01) should be in results"
        
        # Schule02 cyclists
        assert 'Anna_Mueller' in content, "Anna_Mueller (Schule02) should be in results"
        assert 'Peter_Fischer' in content, "Peter_Fischer (Schule02) should be in results"
    
    def test_get_filtered_cyclists_all_top_groups_no_parameter(self, client, cyclists, top_groups):
        """Test that all cyclists are returned when no top_group parameter is provided."""
        url = reverse('game:get_filtered_cyclists')
        # No top_group parameter at all (simulating initial page load or reset)
        response = client.get(url)
        
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        
        # Should contain ALL cyclists from ALL schools
        # Schule01 cyclists
        assert 'Max_Mustermann' in content, "Max_Mustermann (Schule01) should be in results"
        assert 'Lisa_Schmidt' in content, "Lisa_Schmidt (Schule01) should be in results"
        assert 'Tom_Weber' in content, "Tom_Weber (Schule01) should be in results"
        
        # Schule02 cyclists
        assert 'Anna_Mueller' in content, "Anna_Mueller (Schule02) should be in results"
        assert 'Peter_Fischer' in content, "Peter_Fischer (Schule02) should be in results"
    
    def test_get_filtered_cyclists_reset_from_specific_to_all(self, client, cyclists, top_groups):
        """Test that resetting from a specific top group to 'Alle TOP-Gruppen' returns all cyclists."""
        url = reverse('game:get_filtered_cyclists')
        
        # First, filter by Schule01 - should only show Schule01 cyclists
        response1 = client.get(url, {'top_group': top_groups['school1'].id})
        assert response1.status_code == 200
        content1 = response1.content.decode('utf-8')
        assert 'Max_Mustermann' in content1
        assert 'Lisa_Schmidt' in content1
        assert 'Tom_Weber' in content1
        assert 'Anna_Mueller' not in content1, "Anna_Mueller (Schule02) should NOT be in filtered results"
        assert 'Peter_Fischer' not in content1, "Peter_Fischer (Schule02) should NOT be in filtered results"
        
        # Then, reset to "Alle TOP-Gruppen" (empty top_group) - should show ALL cyclists
        response2 = client.get(url, {'top_group': ''})
        assert response2.status_code == 200
        content2 = response2.content.decode('utf-8')
        
        # Should contain ALL cyclists from ALL schools
        assert 'Max_Mustermann' in content2, "After reset: Max_Mustermann (Schule01) should be in results"
        assert 'Lisa_Schmidt' in content2, "After reset: Lisa_Schmidt (Schule01) should be in results"
        assert 'Tom_Weber' in content2, "After reset: Tom_Weber (Schule01) should be in results"
        assert 'Anna_Mueller' in content2, "After reset: Anna_Mueller (Schule02) should be in results"
        assert 'Peter_Fischer' in content2, "After reset: Peter_Fischer (Schule02) should be in results"
    
    def test_get_filtered_cyclists_by_top_group(self, client, cyclists, top_groups):
        """Test filtering cyclists by top-level group (school)."""
        url = reverse('game:get_filtered_cyclists')
        response = client.get(url, {'top_group': top_groups['school1'].id})
        
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        
        # Should only contain cyclists from Schule01
        assert 'Max_Mustermann' in content
        assert 'Lisa_Schmidt' in content
        assert 'Tom_Weber' in content
        
        # Should NOT contain cyclists from Schule02
        assert 'Anna_Mueller' not in content
        assert 'Peter_Fischer' not in content
    
    def test_get_filtered_cyclists_by_subgroup(self, client, cyclists, subgroups):
        """Test filtering cyclists by subgroup (class)."""
        url = reverse('game:get_filtered_cyclists')
        response = client.get(url, {'subgroup': subgroups['school1_class1a'].id})
        
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        
        # Should only contain cyclists from Klasse 1a
        assert 'Max_Mustermann' in content
        assert 'Lisa_Schmidt' in content
        
        # Should NOT contain other cyclists
        assert 'Tom_Weber' not in content
        assert 'Anna_Mueller' not in content
        assert 'Peter_Fischer' not in content
    
    def test_get_filtered_cyclists_by_search(self, client, cyclists):
        """Test filtering cyclists by search query."""
        url = reverse('game:get_filtered_cyclists')
        response = client.get(url, {'cyclist_search': 'Max'})
        
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        
        # Should only contain Max_Mustermann
        assert 'Max_Mustermann' in content
        
        # Should NOT contain other cyclists
        assert 'Lisa_Schmidt' not in content
        assert 'Tom_Weber' not in content
        assert 'Anna_Mueller' not in content
        assert 'Peter_Fischer' not in content
    
    def test_get_filtered_cyclists_top_group_and_search(self, client, cyclists, top_groups):
        """Test filtering cyclists by top group AND search query."""
        url = reverse('game:get_filtered_cyclists')
        response = client.get(url, {
            'top_group': top_groups['school1'].id,
            'cyclist_search': 'Max'
        })
        
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        
        # Should only contain Max_Mustermann (from Schule01 and matches search)
        assert 'Max_Mustermann' in content
        
        # Should NOT contain other cyclists
        assert 'Lisa_Schmidt' not in content
        assert 'Tom_Weber' not in content
        assert 'Anna_Mueller' not in content
        assert 'Peter_Fischer' not in content
    
    def test_get_filtered_cyclists_subgroup_priority(self, client, cyclists, top_groups, subgroups):
        """Test that subgroup filter takes priority over top group filter."""
        url = reverse('game:get_filtered_cyclists')
        # Provide both top_group and subgroup - subgroup should take priority
        response = client.get(url, {
            'top_group': top_groups['school1'].id,
            'subgroup': subgroups['school1_class1a'].id
        })
        
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        
        # Should only contain cyclists from Klasse 1a (subgroup takes priority)
        assert 'Max_Mustermann' in content
        assert 'Lisa_Schmidt' in content
        
        # Should NOT contain Tom_Weber (from Klasse 1b, same school but different class)
        assert 'Tom_Weber' not in content
    
    def test_get_subgroups_for_top_group(self, client, top_groups, subgroups):
        """Test getting subgroups for a selected top group."""
        url = reverse('game:get_subgroups')
        response = client.get(url, {'top_group': top_groups['school1'].id})
        
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        
        # Should contain subgroups of Schule01
        assert 'Klasse 1a' in content
        assert 'Klasse 1b' in content
        
        # Should NOT contain subgroups of Schule02
        assert 'Klasse 2a' not in content
    
    def test_get_subgroups_no_top_group(self, client):
        """Test getting subgroups when no top group is selected."""
        url = reverse('game:get_subgroups')
        response = client.get(url)
        
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        
        # Should only contain "Alle Untergruppen" option
        assert 'Alle Untergruppen' in content
    
    def test_get_filtered_devices_no_filter(self, client, devices):
        """Test that all devices are returned when no filter is applied."""
        url = reverse('game:get_filtered_devices')
        response = client.get(url)
        
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        
        # Should contain all devices (using display_name)
        assert 'Gerät 1' in content
        assert 'Gerät 2' in content
        assert 'Gerät 3' in content
        
        # Should NOT contain internal device names
        assert 'device001' not in content
        assert 'device002' not in content
        assert 'device003' not in content
    
    def test_get_filtered_devices_by_top_group(self, client, devices, top_groups):
        """Test filtering devices by top-level group."""
        # Assign devices to different top groups
        devices['device1'].group = top_groups['school1']
        devices['device1'].save()
        devices['device2'].group = top_groups['school1']
        devices['device2'].save()
        devices['device3'].group = top_groups['school2']
        devices['device3'].save()
        
        url = reverse('game:get_filtered_devices')
        response = client.get(url, {'top_group': top_groups['school1'].id})
        
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        
        # Should only contain devices from Schule01
        assert 'Gerät 1' in content
        assert 'Gerät 2' in content
        
        # Should NOT contain device from Schule02
        assert 'Gerät 3' not in content
    
    def test_get_filtered_devices_by_search(self, client, devices):
        """Test filtering devices by search query."""
        url = reverse('game:get_filtered_devices')
        response = client.get(url, {'device_search': 'Gerät 1'})
        
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        
        # Should only contain Gerät 1
        assert 'Gerät 1' in content
        
        # Should NOT contain other devices
        assert 'Gerät 2' not in content
        assert 'Gerät 3' not in content
    
    def test_get_filtered_devices_top_group_and_search(self, client, devices, top_groups):
        """Test filtering devices by top group AND search query."""
        # Assign devices to different top groups
        devices['device1'].group = top_groups['school1']
        devices['device1'].save()
        devices['device2'].group = top_groups['school1']
        devices['device2'].save()
        devices['device3'].group = top_groups['school2']
        devices['device3'].save()
        
        url = reverse('game:get_filtered_devices')
        response = client.get(url, {
            'top_group': top_groups['school1'].id,
            'device_search': 'Gerät 1'
        })
        
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        
        # Should only contain Gerät 1 (from Schule01 and matches search)
        assert 'Gerät 1' in content
        
        # Should NOT contain other devices
        assert 'Gerät 2' not in content
        assert 'Gerät 3' not in content
    
    def test_get_filtered_devices_no_group_assigned(self, client, devices, top_groups):
        """Test that devices without group assignment are shown when no filter is applied."""
        # Don't assign any group to devices
        url = reverse('game:get_filtered_devices')
        response = client.get(url)
        
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        
        # Should contain all devices (no filter applied)
        assert 'Gerät 1' in content
        assert 'Gerät 2' in content
        assert 'Gerät 3' in content
    
    def test_get_filtered_devices_no_group_assigned_with_filter(self, client, devices, top_groups):
        """Test that devices without group assignment are NOT shown when filter is applied."""
        # Don't assign any group to devices
        url = reverse('game:get_filtered_devices')
        response = client.get(url, {'top_group': top_groups['school1'].id})
        
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        
        # Should NOT contain devices without group assignment
        assert 'Gerät 1' not in content
        assert 'Gerät 2' not in content
        assert 'Gerät 3' not in content
    
    def test_get_filtered_devices_display_name_fallback(self, client):
        """Test that device name is used as fallback when display_name is empty."""
        # Create device without display_name
        device = Device.objects.create(
            name="device_no_display",
            display_name="",  # Empty display_name
            is_visible=True
        )
        
        url = reverse('game:get_filtered_devices')
        response = client.get(url)
        
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        
        # Should fall back to name when display_name is empty
        assert 'device_no_display' in content
    
    def test_get_filtered_cyclists_invalid_top_group(self, client, cyclists):
        """Test filtering with invalid top group ID."""
        url = reverse('game:get_filtered_cyclists')
        response = client.get(url, {'top_group': 99999})  # Non-existent ID
        
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        
        # Should return all cyclists (invalid filter is ignored)
        assert 'Max_Mustermann' in content
        assert 'Lisa_Schmidt' in content
    
    def test_get_filtered_cyclists_invalid_subgroup(self, client, cyclists):
        """Test filtering with invalid subgroup ID."""
        url = reverse('game:get_filtered_cyclists')
        response = client.get(url, {'subgroup': 99999})  # Non-existent ID
        
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        
        # Should return all cyclists (invalid filter is ignored)
        assert 'Max_Mustermann' in content
        assert 'Lisa_Schmidt' in content
    
    def test_get_filtered_cyclists_hidden_cyclist(self, client, cyclists):
        """Test that hidden (is_visible=False) cyclists are not returned."""
        # Create a hidden cyclist
        hidden_cyclist = Cyclist.objects.create(
            user_id="Hidden_User",
            id_tag="TAG_HIDDEN",
            is_visible=False
        )
        
        url = reverse('game:get_filtered_cyclists')
        response = client.get(url)
        
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        
        # Should NOT contain hidden cyclist
        assert 'Hidden_User' not in content
    
    def test_get_filtered_devices_hidden_device(self, client, devices):
        """Test that hidden (is_visible=False) devices are not returned."""
        # Create a hidden device
        hidden_device = Device.objects.create(
            name="hidden_device",
            display_name="Verstecktes Gerät",
            is_visible=False
        )
        
        url = reverse('game:get_filtered_devices')
        response = client.get(url)
        
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        
        # Should NOT contain hidden device
        assert 'Verstecktes Gerät' not in content
