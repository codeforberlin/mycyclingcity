# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    test_views.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

"""
Unit tests for Ranking views.

Tests cover:
- ranking_page view
"""

import pytest
from django.test import Client
from urllib.parse import quote

from ranking.views import ranking_page
from api.tests.conftest import GroupFactory, CyclistFactory


@pytest.mark.unit
@pytest.mark.django_db
class TestRankingViews:
    """Tests for Ranking views."""
    
    def test_ranking_page_default(self):
        """Test ranking page with default parameters."""
        client = Client()
        response = client.get('/de/ranking/')
        
        assert response.status_code == 200
        assert 'groups' in response.context or 'target_groups' in response.context
    
    def test_ranking_page_with_group_id(self):
        """Test ranking page with group_id parameter."""
        group = GroupFactory()
        client = Client()
        response = client.get(f'/de/ranking/?group_id={group.id}')
        
        assert response.status_code == 200
    
    def test_ranking_page_with_group_name(self):
        """Test ranking page with group_name parameter."""
        group = GroupFactory(name="Test Group")
        client = Client()
        # URL encode the group name
        encoded_name = quote(group.name)
        response = client.get(f'/de/ranking/?group_name={encoded_name}')
        
        assert response.status_code == 200
    
    def test_ranking_page_with_invalid_group_id(self):
        """Test ranking page with invalid group_id."""
        client = Client()
        response = client.get('/de/ranking/?group_id=99999')
        
        assert response.status_code == 200  # Should still render, just no group selected
    
    def test_ranking_page_kiosk_mode(self):
        """Test ranking page in kiosk mode."""
        client = Client()
        response = client.get('/de/ranking/kiosk/')
        
        assert response.status_code == 200
    
    def test_ranking_page_with_interval(self):
        """Test ranking page with custom refresh interval."""
        client = Client()
        response = client.get('/de/ranking/?interval=30')
        
        assert response.status_code == 200
    
    def test_ranking_page_show_cyclists_false(self):
        """Test ranking page with show_cyclists=false."""
        client = Client()
        response = client.get('/de/ranking/?show_cyclists=false')
        
        assert response.status_code == 200
    
    def test_ranking_page_multiple_group_ids(self):
        """Test ranking page with multiple comma-separated group IDs."""
        group1 = GroupFactory()
        group2 = GroupFactory()
        client = Client()
        response = client.get(f'/de/ranking/?group_id={group1.id},{group2.id}')
        
        assert response.status_code == 200
    
    def test_ranking_page_group_id_none(self):
        """Test ranking page with group_id='none'."""
        client = Client()
        response = client.get('/de/ranking/?group_id=none')
        
        assert response.status_code == 200
