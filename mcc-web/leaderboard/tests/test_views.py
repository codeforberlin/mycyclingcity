# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    test_views.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

"""
Unit tests for Leaderboard views.

Tests cover:
- leaderboard_page view
- leaderboard_ticker view
- _calculate_group_totals_from_metrics helper
"""

import pytest
from django.test import Client
from django.utils import timezone
from unittest.mock import patch
from decimal import Decimal

from leaderboard.views import leaderboard_page, leaderboard_ticker, _calculate_group_totals_from_metrics
from api.tests.conftest import GroupFactory, CyclistFactory, HourlyMetricFactory


@pytest.mark.unit
@pytest.mark.django_db
class TestLeaderboardViews:
    """Tests for Leaderboard views."""
    
    def test_leaderboard_page_default(self):
        """Test leaderboard page with default parameters."""
        client = Client()
        response = client.get('/de/leaderboard/')
        
        assert response.status_code == 200
    
    def test_leaderboard_page_with_group_id(self):
        """Test leaderboard page with group_id parameter."""
        group = GroupFactory()
        client = Client()
        response = client.get(f'/de/leaderboard/?group_id={group.id}')
        
        assert response.status_code == 200
    
    def test_leaderboard_ticker(self):
        """Test leaderboard ticker endpoint."""
        client = Client()
        response = client.get('/de/leaderboard/ticker/')
        
        assert response.status_code == 200
    
    def test_calculate_group_totals_from_metrics_empty(self):
        """Test calculating totals for empty group list."""
        result = _calculate_group_totals_from_metrics([], timezone.now())
        
        assert result == {}
    
    def test_calculate_group_totals_from_metrics(self):
        """Test calculating totals from metrics."""
        group = GroupFactory()
        now = timezone.now()
        
        # Create some hourly metrics
        HourlyMetricFactory(
            group_at_time=group,
            timestamp=now.replace(hour=10),
            distance_km=Decimal('5.0'),
        )
        HourlyMetricFactory(
            group_at_time=group,
            timestamp=now.replace(hour=11),
            distance_km=Decimal('3.0'),
        )
        
        result = _calculate_group_totals_from_metrics([group], now, use_cache=False)
        
        assert group.id in result
        assert result[group.id]['total'] >= 8.0  # At least the metrics we created
    
    def test_calculate_group_totals_from_metrics_uses_cache(self):
        """Test that cache is used when enabled."""
        group = GroupFactory()
        now = timezone.now()
        
        # First call - should calculate
        result1 = _calculate_group_totals_from_metrics([group], now, use_cache=True)
        
        # Second call - should use cache
        result2 = _calculate_group_totals_from_metrics([group], now, use_cache=True)
        
        # Results should be the same (from cache)
        assert result1 == result2
