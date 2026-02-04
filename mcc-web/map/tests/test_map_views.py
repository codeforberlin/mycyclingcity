# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    test_map_views.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

"""
Unit tests for Map views.

Tests cover:
- map_page view
- map_ticker view
- are_all_parents_visible helper
- API endpoints
"""

import pytest
from django.test import Client
from urllib.parse import quote

from map.views import map_page, map_ticker, are_all_parents_visible, get_group_avatars, get_new_milestones, get_all_milestones_status
from api.tests.conftest import GroupFactory, CyclistFactory, TravelTrackFactory, MilestoneFactory


@pytest.mark.unit
@pytest.mark.django_db
class TestMapViews:
    """Tests for Map views."""
    
    def test_map_page_default(self):
        """Test map page with default parameters."""
        client = Client()
        response = client.get('/de/map/')
        
        assert response.status_code == 200
    
    def test_map_page_with_group_id(self):
        """Test map page with group_id parameter."""
        group = GroupFactory()
        client = Client()
        response = client.get(f'/de/map/?group_id={group.id}')
        
        assert response.status_code == 200
    
    def test_map_page_with_group_name(self):
        """Test map page with group_name parameter."""
        group = GroupFactory(name="Test Group")
        client = Client()
        encoded_name = quote(group.name)
        response = client.get(f'/de/map/?group_name={encoded_name}')
        
        assert response.status_code == 200
    
    def test_map_page_mobile_detection(self):
        """Test map page mobile device detection."""
        client = Client(HTTP_USER_AGENT='Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X)')
        response = client.get('/de/map/')
        
        assert response.status_code == 200
    
    def test_map_ticker(self):
        """Test map ticker endpoint."""
        client = Client()
        response = client.get('/de/map/ticker/')
        
        assert response.status_code == 200
    
    def test_map_ticker_with_group_id(self):
        """Test map ticker with group_id parameter."""
        group = GroupFactory()
        client = Client()
        response = client.get(f'/de/map/ticker/?group_id={group.id}')
        
        assert response.status_code == 200
    
    def test_get_group_avatars(self):
        """Test get_group_avatars API endpoint."""
        group = GroupFactory()
        client = Client()
        response = client.get('/de/map/api/group-avatars/')
        
        assert response.status_code == 200
        # Should return JSON
        assert response['Content-Type'] == 'application/json'
    
    def test_get_new_milestones(self):
        """Test get_new_milestones API endpoint."""
        track = TravelTrackFactory()
        milestone = MilestoneFactory(track=track)
        client = Client()
        response = client.get('/de/map/api/new-milestones/')
        
        assert response.status_code == 200
        assert response['Content-Type'] == 'application/json'
    
    def test_get_all_milestones_status(self):
        """Test get_all_milestones_status API endpoint."""
        track = TravelTrackFactory()
        MilestoneFactory(track=track)
        client = Client()
        response = client.get('/de/map/api/all-milestones-status/')
        
        assert response.status_code == 200
        assert response['Content-Type'] == 'application/json'


@pytest.mark.unit
@pytest.mark.django_db
class TestMapHelpers:
    """Tests for Map helper functions."""
    
    def test_are_all_parents_visible_visible_group(self):
        """Test are_all_parents_visible with visible group."""
        group = GroupFactory(is_visible=True)
        
        result = are_all_parents_visible(group)
        
        assert result is True
    
    def test_are_all_parents_visible_invisible_group(self):
        """Test are_all_parents_visible with invisible group."""
        group = GroupFactory(is_visible=False)
        
        result = are_all_parents_visible(group)
        
        assert result is False
    
    def test_are_all_parents_visible_with_parents(self):
        """Test are_all_parents_visible with parent hierarchy."""
        parent = GroupFactory(is_visible=True)
        child = GroupFactory(parent=parent, is_visible=True)
        
        result = are_all_parents_visible(child)
        
        assert result is True
    
    def test_are_all_parents_visible_invisible_parent(self):
        """Test are_all_parents_visible with invisible parent."""
        parent = GroupFactory(is_visible=False)
        child = GroupFactory(parent=parent, is_visible=True)
        
        result = are_all_parents_visible(child)
        
        assert result is False
    
    def test_are_all_parents_visible_multiple_levels(self):
        """Test are_all_parents_visible with multiple parent levels."""
        grandparent = GroupFactory(is_visible=True)
        parent = GroupFactory(parent=grandparent, is_visible=True)
        child = GroupFactory(parent=parent, is_visible=True)
        
        result = are_all_parents_visible(child)
        
        assert result is True
