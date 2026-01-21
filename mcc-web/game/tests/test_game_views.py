# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    test_game_views.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

"""
Unit tests for game view functions.

Tests the view functions directly to ensure they return correct results,
especially for edge cases like empty filters.
"""

import pytest
from django.test import RequestFactory
from django.urls import reverse
from api.models import Group, Cyclist, GroupType
from iot.models import Device
from game.views import get_filtered_cyclists, get_filtered_devices, get_subgroups


@pytest.mark.django_db
class TestGetFilteredCyclistsView:
    """Unit tests for get_filtered_cyclists view function."""
    
    @pytest.fixture
    def factory(self):
        """Create a request factory."""
        return RequestFactory()
    
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
        school3 = Group.objects.create(
            name="Schule03",
            group_type=group_type,
            is_visible=True
        )
        return {'school1': school1, 'school2': school2, 'school3': school3}
    
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
        # Classes for Schule03
        class3a = Group.objects.create(
            name="Klasse 3a",
            group_type=group_type,
            parent=top_groups['school3'],
            is_visible=True
        )
        return {
            'school1_class1a': class1a,
            'school1_class1b': class1b,
            'school2_class2a': class2a,
            'school3_class3a': class3a,
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
        
        # Cyclist for Schule03 - Klasse 3a
        cyclist6 = Cyclist.objects.create(
            user_id="Sarah_Bauer",
            id_tag="TAG006",
            is_visible=True
        )
        cyclist6.groups.add(subgroups['school3_class3a'])
        
        return {
            'max': cyclist1,
            'lisa': cyclist2,
            'tom': cyclist3,
            'anna': cyclist4,
            'peter': cyclist5,
            'sarah': cyclist6,
        }
    
    def test_get_filtered_cyclists_no_parameters(self, factory, cyclists):
        """Test that ALL cyclists from ALL schools are returned when no parameters are provided."""
        request = factory.get(reverse('game:get_filtered_cyclists'))
        response = get_filtered_cyclists(request)
        
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        
        # Should contain ALL cyclists from ALL schools
        assert 'Max_Mustermann' in content, "Max_Mustermann (Schule01) should be in results"
        assert 'Lisa_Schmidt' in content, "Lisa_Schmidt (Schule01) should be in results"
        assert 'Tom_Weber' in content, "Tom_Weber (Schule01) should be in results"
        assert 'Anna_Mueller' in content, "Anna_Mueller (Schule02) should be in results"
        assert 'Peter_Fischer' in content, "Peter_Fischer (Schule02) should be in results"
        assert 'Sarah_Bauer' in content, "Sarah_Bauer (Schule03) should be in results"
    
    def test_get_filtered_cyclists_empty_top_group(self, factory, cyclists, top_groups):
        """Test that ALL cyclists are returned when top_group parameter is empty string."""
        request = factory.get(reverse('game:get_filtered_cyclists'), {'top_group': ''})
        response = get_filtered_cyclists(request)
        
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        
        # Should contain ALL cyclists from ALL schools, not just the first one
        assert 'Max_Mustermann' in content, "Max_Mustermann (Schule01) should be in results"
        assert 'Lisa_Schmidt' in content, "Lisa_Schmidt (Schule01) should be in results"
        assert 'Tom_Weber' in content, "Tom_Weber (Schule01) should be in results"
        assert 'Anna_Mueller' in content, "Anna_Mueller (Schule02) should be in results"
        assert 'Peter_Fischer' in content, "Peter_Fischer (Schule02) should be in results"
        assert 'Sarah_Bauer' in content, "Sarah_Bauer (Schule03) should be in results"
    
    def test_get_filtered_cyclists_empty_top_group_and_subgroup(self, factory, cyclists, top_groups):
        """Test that ALL cyclists are returned when both top_group and subgroup are empty."""
        request = factory.get(reverse('game:get_filtered_cyclists'), {
            'top_group': '',
            'subgroup': ''
        })
        response = get_filtered_cyclists(request)
        
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        
        # Should contain ALL cyclists from ALL schools
        assert 'Max_Mustermann' in content, "Max_Mustermann (Schule01) should be in results"
        assert 'Lisa_Schmidt' in content, "Lisa_Schmidt (Schule01) should be in results"
        assert 'Tom_Weber' in content, "Tom_Weber (Schule01) should be in results"
        assert 'Anna_Mueller' in content, "Anna_Mueller (Schule02) should be in results"
        assert 'Peter_Fischer' in content, "Peter_Fischer (Schule02) should be in results"
        assert 'Sarah_Bauer' in content, "Sarah_Bauer (Schule03) should be in results"
    
    def test_get_filtered_cyclists_reset_from_school1_to_all(self, factory, cyclists, top_groups):
        """Test resetting from Schule01 filter to 'Alle TOP-Gruppen' returns all cyclists."""
        # First, filter by Schule01
        request1 = factory.get(reverse('game:get_filtered_cyclists'), {
            'top_group': str(top_groups['school1'].id)
        })
        response1 = get_filtered_cyclists(request1)
        assert response1.status_code == 200
        content1 = response1.content.decode('utf-8')
        
        # Should only contain Schule01 cyclists
        assert 'Max_Mustermann' in content1
        assert 'Lisa_Schmidt' in content1
        assert 'Tom_Weber' in content1
        assert 'Anna_Mueller' not in content1, "Anna_Mueller (Schule02) should NOT be in filtered results"
        assert 'Peter_Fischer' not in content1, "Peter_Fischer (Schule02) should NOT be in filtered results"
        assert 'Sarah_Bauer' not in content1, "Sarah_Bauer (Schule03) should NOT be in filtered results"
        
        # Then, reset to "Alle TOP-Gruppen" (empty top_group)
        request2 = factory.get(reverse('game:get_filtered_cyclists'), {'top_group': ''})
        response2 = get_filtered_cyclists(request2)
        assert response2.status_code == 200
        content2 = response2.content.decode('utf-8')
        
        # Should contain ALL cyclists from ALL schools
        assert 'Max_Mustermann' in content2, "After reset: Max_Mustermann (Schule01) should be in results"
        assert 'Lisa_Schmidt' in content2, "After reset: Lisa_Schmidt (Schule01) should be in results"
        assert 'Tom_Weber' in content2, "After reset: Tom_Weber (Schule01) should be in results"
        assert 'Anna_Mueller' in content2, "After reset: Anna_Mueller (Schule02) should be in results"
        assert 'Peter_Fischer' in content2, "After reset: Peter_Fischer (Schule02) should be in results"
        assert 'Sarah_Bauer' in content2, "After reset: Sarah_Bauer (Schule03) should be in results"
    
    def test_get_filtered_cyclists_by_school1(self, factory, cyclists, top_groups):
        """Test filtering by Schule01 returns only Schule01 cyclists."""
        request = factory.get(reverse('game:get_filtered_cyclists'), {
            'top_group': str(top_groups['school1'].id)
        })
        response = get_filtered_cyclists(request)
        
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        
        # Should only contain Schule01 cyclists
        assert 'Max_Mustermann' in content
        assert 'Lisa_Schmidt' in content
        assert 'Tom_Weber' in content
        
        # Should NOT contain cyclists from other schools
        assert 'Anna_Mueller' not in content
        assert 'Peter_Fischer' not in content
        assert 'Sarah_Bauer' not in content
    
    def test_get_filtered_cyclists_by_school2(self, factory, cyclists, top_groups):
        """Test filtering by Schule02 returns only Schule02 cyclists."""
        request = factory.get(reverse('game:get_filtered_cyclists'), {
            'top_group': str(top_groups['school2'].id)
        })
        response = get_filtered_cyclists(request)
        
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        
        # Should only contain Schule02 cyclists
        assert 'Anna_Mueller' in content
        assert 'Peter_Fischer' in content
        
        # Should NOT contain cyclists from other schools
        assert 'Max_Mustermann' not in content
        assert 'Lisa_Schmidt' not in content
        assert 'Tom_Weber' not in content
        assert 'Sarah_Bauer' not in content
    
    def test_get_filtered_cyclists_by_school3(self, factory, cyclists, top_groups):
        """Test filtering by Schule03 returns only Schule03 cyclists."""
        request = factory.get(reverse('game:get_filtered_cyclists'), {
            'top_group': str(top_groups['school3'].id)
        })
        response = get_filtered_cyclists(request)
        
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        
        # Should only contain Schule03 cyclists
        assert 'Sarah_Bauer' in content
        
        # Should NOT contain cyclists from other schools
        assert 'Max_Mustermann' not in content
        assert 'Lisa_Schmidt' not in content
        assert 'Tom_Weber' not in content
        assert 'Anna_Mueller' not in content
        assert 'Peter_Fischer' not in content
