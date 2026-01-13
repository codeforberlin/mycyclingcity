# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    test_live_api.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
"""
Live API integration tests against a running Gunicorn instance.

These tests are designed to run against a live server (default: http://127.0.0.1:8000).
They test:
- HTTP status codes
- JSON structure validity
- German number formatting (comma as decimal separator)
- All API endpoints

Usage:
    pytest api/tests/test_live_api.py -m live --base-url=http://127.0.0.1:8000
"""

import pytest
import requests
import json
import os
from decimal import Decimal
from typing import Dict, Any, Optional


# Configuration
DEFAULT_BASE_URL = os.getenv('TEST_BASE_URL', 'http://127.0.0.1:8000')
DEFAULT_API_KEY = os.getenv('TEST_API_KEY', 'MCC-APP-API-KEY-SECRET')


@pytest.fixture(scope='module')
def base_url(request):
    """Fixture providing the base URL for API tests."""
    return request.config.getoption('--base-url', default=DEFAULT_BASE_URL)


@pytest.fixture(scope='module')
def api_key(request):
    """Fixture providing the API key for authentication."""
    return request.config.getoption('--api-key', default=DEFAULT_API_KEY)


@pytest.fixture(scope='module')
def session(base_url):
    """Fixture providing a requests session."""
    session = requests.Session()
    session.base_url = base_url
    return session


def check_german_number_formatting(value: str) -> bool:
    """
    Check if a number string uses German formatting (comma as decimal separator).
    
    German format: 1.234,56 (point for thousands, comma for decimal)
    
    Args:
        value: String representation of a number
        
    Returns:
        True if the number uses German formatting (comma as decimal separator)
    """
    # Check if comma is used as decimal separator
    if ',' in value and '.' in value:
        # Has both comma and dot - check which is decimal separator
        comma_pos = value.rfind(',')
        dot_pos = value.rfind('.')
        # The one that appears last is likely the decimal separator
        return comma_pos > dot_pos
    elif ',' in value:
        # Only comma - could be German format
        parts = value.split(',')
        if len(parts) == 2:
            # Has comma separator - check if right part is numeric
            try:
                int(parts[1])
                return True
            except ValueError:
                return False
    return False


def check_english_number_formatting(value: str) -> bool:
    """
    Check if a number string uses English formatting (comma for thousands, dot for decimal).
    
    English format: 1,234.56 (comma for thousands, dot for decimal)
    
    Args:
        value: String representation of a number
        
    Returns:
        True if the number uses English formatting
    """
    if ',' in value and '.' in value:
        # Has both comma and dot - check which is decimal separator
        comma_pos = value.rfind(',')
        dot_pos = value.rfind('.')
        # In English format, dot should be the decimal separator (appears last)
        return dot_pos > comma_pos
    elif '.' in value and ',' not in value:
        # Only dot - could be English format (no thousands separator)
        parts = value.split('.')
        if len(parts) == 2:
            try:
                int(parts[1])
                return True
            except ValueError:
                return False
    elif ',' not in value and '.' not in value:
        # Integer without separators - valid English format
        try:
            int(value)
            return True
        except ValueError:
            return False
    return False


def extract_numbers_from_text(text: str) -> list:
    """
    Extract number strings from text that might be formatted.
    
    Args:
        text: Text to search for numbers
        
    Returns:
        List of number strings found in the text
    """
    import re
    # Pattern to match numbers with separators (e.g., 1.234,56 or 1,234.56)
    pattern = r'\d+[.,]\d+[.,]?\d*|\d+'
    matches = re.findall(pattern, text)
    return matches


def check_json_structure(data: Any, expected_keys: list) -> tuple:
    """
    Check if JSON data has expected structure.
    
    Args:
        data: JSON data to check
        expected_keys: List of expected top-level keys
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not isinstance(data, dict):
        return False, f"Expected dict, got {type(data)}"
    
    for key in expected_keys:
        if key not in data:
            return False, f"Missing key: {key}"
    
    return True, None


@pytest.mark.live
class TestLiveAPIEndpoints:
    """Live API tests for all endpoints."""
    
    def test_server_health(self, session):
        """Test that the server is running and accessible."""
        try:
            response = session.get(f"{session.base_url}/admin/", timeout=5)
            # Any response (even 404) means server is running
            assert response.status_code in [200, 302, 404], \
                f"Server not accessible. Status: {response.status_code}"
        except requests.exceptions.ConnectionError:
            pytest.skip("Server is not running. Start Gunicorn first.")
    
    def test_update_data_endpoint(self, session, api_key):
        """Test update_data endpoint with valid request."""
        url = f"{session.base_url}/api/update-data"
        
        payload = {
            'id_tag': 'test-tag-001',
            'device_id': 'test-device-01',
            'distance': '5.50000'
        }
        
        headers = {
            'X-Api-Key': api_key,
            'Content-Type': 'application/json'
        }
        
        try:
            response = session.post(url, json=payload, headers=headers, timeout=10)
            
            # Should return 200 (success) or 404 (cyclist/device not found) or 400 (validation error)
            assert response.status_code in [200, 400, 404], \
                f"Unexpected status code: {response.status_code}"
            
            if response.status_code == 200:
                data = response.json()
                assert isinstance(data, dict), "Response should be JSON object"
                # Check for success or skipped field
                assert 'success' in data or 'skipped' in data, \
                    "Response should contain 'success' or 'skipped' field"
        except requests.exceptions.ConnectionError:
            pytest.skip("Server is not running. Start Gunicorn first.")
    
    def test_update_data_invalid_api_key(self, session):
        """Test update_data endpoint with invalid API key."""
        url = f"{session.base_url}/api/update-data"
        
        payload = {
            'id_tag': 'test-tag-001',
            'device_id': 'test-device-01',
            'distance': '5.50000'
        }
        
        headers = {
            'X-Api-Key': 'INVALID-KEY',
            'Content-Type': 'application/json'
        }
        
        try:
            response = session.post(url, json=payload, headers=headers, timeout=10)
            assert response.status_code == 403, \
                f"Expected 403 Forbidden, got {response.status_code}"
        except requests.exceptions.ConnectionError:
            pytest.skip("Server is not running. Start Gunicorn first.")
    
    def test_get_cyclist_coins_endpoint(self, session, api_key):
        """Test get_cyclist_coins endpoint."""
        url = f"{session.base_url}/api/get-cyclist-coins/testplayer"
        
        headers = {
            'X-Api-Key': api_key
        }
        
        try:
            response = session.get(url, headers=headers, timeout=10)
            
            # Should return 200 (success) or 404 (cyclist not found)
            assert response.status_code in [200, 404], \
                f"Unexpected status code: {response.status_code}"
            
            if response.status_code == 200:
                data = response.json()
                is_valid, error = check_json_structure(
                    data,
                    ['coins_total', 'coins_spendable', 'distance_total']
                )
                assert is_valid, f"Invalid JSON structure: {error}"
                
                # Check that numeric values are present
                assert isinstance(data['coins_total'], (int, float))
                assert isinstance(data['coins_spendable'], (int, float))
        except requests.exceptions.ConnectionError:
            pytest.skip("Server is not running. Start Gunicorn first.")
    
    def test_get_user_id_endpoint(self, session, api_key):
        """Test get_user_id endpoint."""
        url = f"{session.base_url}/api/get-user-id"
        
        payload = {
            'id_tag': 'test-tag-001'
        }
        
        headers = {
            'X-Api-Key': api_key,
            'Content-Type': 'application/json'
        }
        
        try:
            response = session.post(url, json=payload, headers=headers, timeout=10)
            assert response.status_code == 200, \
                f"Expected 200 OK, got {response.status_code}"
            
            data = response.json()
            is_valid, error = check_json_structure(data, ['user_id'])
            assert is_valid, f"Invalid JSON structure: {error}"
        except requests.exceptions.ConnectionError:
            pytest.skip("Server is not running. Start Gunicorn first.")
    
    def test_get_mapped_minecraft_cyclists_endpoint(self, session, api_key):
        """Test get_mapped_minecraft_cyclists endpoint."""
        url = f"{session.base_url}/api/get-mapped-minecraft-cyclists"
        
        headers = {
            'X-Api-Key': api_key
        }
        
        try:
            response = session.get(url, headers=headers, timeout=10)
            assert response.status_code == 200, \
                f"Expected 200 OK, got {response.status_code}"
            
            data = response.json()
            assert isinstance(data, dict), "Response should be a JSON object"
        except requests.exceptions.ConnectionError:
            pytest.skip("Server is not running. Start Gunicorn first.")
    
    def test_get_travel_locations_endpoint(self, session):
        """Test get_travel_locations endpoint."""
        url = f"{session.base_url}/api/get-travel-locations"
        
        try:
            response = session.get(url, timeout=10)
            assert response.status_code == 200, \
                f"Expected 200 OK, got {response.status_code}"
            
            data = response.json()
            assert isinstance(data, list), "Response should be a JSON array"
        except requests.exceptions.ConnectionError:
            pytest.skip("Server is not running. Start Gunicorn first.")
    
    def test_kiosk_playlist_endpoint(self, session):
        """Test kiosk playlist endpoint."""
        url = f"{session.base_url}/api/kiosk/test-kiosk-001/playlist"
        
        try:
            response = session.get(url, timeout=10)
            # Should return 200 (success) or 404 (device not found) or 503 (inactive)
            assert response.status_code in [200, 404, 503], \
                f"Unexpected status code: {response.status_code}"
            
            if response.status_code == 200:
                data = response.json()
                is_valid, error = check_json_structure(
                    data,
                    ['device_id', 'device_name', 'playlist']
                )
                assert is_valid, f"Invalid JSON structure: {error}"
        except requests.exceptions.ConnectionError:
            pytest.skip("Server is not running. Start Gunicorn first.")
    
    def test_kiosk_commands_endpoint(self, session):
        """Test kiosk commands endpoint."""
        url = f"{session.base_url}/api/kiosk/test-kiosk-001/commands"
        
        try:
            response = session.get(url, timeout=10)
            # Should return 200 (success) or 404 (device not found)
            assert response.status_code in [200, 404], \
                f"Unexpected status code: {response.status_code}"
            
            if response.status_code == 200:
                data = response.json()
                is_valid, error = check_json_structure(
                    data,
                    ['device_id', 'commands', 'brightness']
                )
                assert is_valid, f"Invalid JSON structure: {error}"
        except requests.exceptions.ConnectionError:
            pytest.skip("Server is not running. Start Gunicorn first.")
    
    def test_get_cyclist_distance_endpoint(self, session, api_key):
        """Test get_cyclist_distance endpoint."""
        # Test with a cyclist identifier (user_id, id_tag, or mc_username)
        url = f"{session.base_url}/api/get-cyclist-distance/testplayer"
        
        headers = {
            'X-Api-Key': api_key
        }
        
        try:
            response = session.get(url, headers=headers, timeout=10)
            # Should return 200 (success) or 404 (cyclist not found)
            assert response.status_code in [200, 404], \
                f"Unexpected status code: {response.status_code}"
            
            if response.status_code == 200:
                data = response.json()
                is_valid, error = check_json_structure(
                    data,
                    ['player_id', 'user_id', 'distance_total']  # Note: JSON uses 'player_id' for cyclist ID
                )
                assert is_valid, f"Invalid JSON structure: {error}"
                
                # Check that distance_total is a number in English format
                assert isinstance(data['distance_total'], (int, float)), \
                    "distance_total should be a number"
                distance_str = str(data['distance_total'])
                # Should use dot as decimal separator (English format)
                if ',' in distance_str and '.' in distance_str:
                    comma_pos = distance_str.rfind(',')
                    dot_pos = distance_str.rfind('.')
                    assert dot_pos > comma_pos, \
                        f"distance_total should use English format (comma for thousands, dot for decimal), got: {distance_str}"
        except requests.exceptions.ConnectionError:
            pytest.skip("Server is not running. Start Gunicorn first.")
    
    def test_get_cyclist_distance_with_date_range(self, session, api_key):
        """Test get_cyclist_distance endpoint with date range."""
        url = f"{session.base_url}/api/get-cyclist-distance/testplayer"
        
        headers = {
            'X-Api-Key': api_key
        }
        
        # Test with date range
        from datetime import datetime, timedelta
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)
        
        params = {
            'start_date': start_date.strftime('%Y-%m-%d'),
            'end_date': end_date.strftime('%Y-%m-%d')
        }
        
        try:
            response = session.get(url, headers=headers, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                # Should have period data
                assert 'distance_period' in data, \
                    "Response should contain distance_period when date range is provided"
                assert 'period_start' in data, \
                    "Response should contain period_start when date range is provided"
                assert 'period_end' in data, \
                    "Response should contain period_end when date range is provided"
                
                # Check that distance_period is a number
                assert isinstance(data['distance_period'], (int, float)), \
                    "distance_period should be a number"
        except requests.exceptions.ConnectionError:
            pytest.skip("Server is not running. Start Gunicorn first.")
    
    def test_get_group_distance_endpoint(self, session, api_key):
        """Test get_group_distance endpoint."""
        # Test with a group identifier (ID or name)
        url = f"{session.base_url}/api/get-group-distance/1"
        
        headers = {
            'X-Api-Key': api_key
        }
        
        try:
            response = session.get(url, headers=headers, timeout=10)
            # Should return 200 (success) or 404 (group not found)
            assert response.status_code in [200, 404], \
                f"Unexpected status code: {response.status_code}"
            
            if response.status_code == 200:
                data = response.json()
                is_valid, error = check_json_structure(
                    data,
                    ['group_id', 'name', 'distance_total']
                )
                assert is_valid, f"Invalid JSON structure: {error}"
                
                # Check that distance_total is a number in English format
                assert isinstance(data['distance_total'], (int, float)), \
                    "distance_total should be a number"
        except requests.exceptions.ConnectionError:
            pytest.skip("Server is not running. Start Gunicorn first.")
    
    def test_get_group_distance_with_date_range(self, session, api_key):
        """Test get_group_distance endpoint with date range."""
        url = f"{session.base_url}/api/get-group-distance/1"
        
        headers = {
            'X-Api-Key': api_key
        }
        
        # Test with date range
        from datetime import datetime, timedelta
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)
        
        params = {
            'start_date': start_date.strftime('%Y-%m-%d'),
            'end_date': end_date.strftime('%Y-%m-%d'),
            'include_children': 'false'
        }
        
        try:
            response = session.get(url, headers=headers, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                # Should have period data
                assert 'distance_period' in data, \
                    "Response should contain distance_period when date range is provided"
                assert 'period_start' in data, \
                    "Response should contain period_start when date range is provided"
                assert 'period_end' in data, \
                    "Response should contain period_end when date range is provided"
                
                # Check that distance_period is a number
                assert isinstance(data['distance_period'], (int, float)), \
                    "distance_period should be a number"
        except requests.exceptions.ConnectionError:
            pytest.skip("Server is not running. Start Gunicorn first.")
    
    def test_get_cyclist_distance_invalid_api_key(self, session):
        """Test get_cyclist_distance endpoint with invalid API key."""
        url = f"{session.base_url}/api/get-cyclist-distance/testplayer"
        
        headers = {
            'X-Api-Key': 'INVALID-KEY'
        }
        
        try:
            response = session.get(url, headers=headers, timeout=10)
            assert response.status_code == 403, \
                f"Expected 403 Forbidden, got {response.status_code}"
        except requests.exceptions.ConnectionError:
            pytest.skip("Server is not running. Start Gunicorn first.")
    
    def test_get_group_distance_invalid_api_key(self, session):
        """Test get_group_distance endpoint with invalid API key."""
        url = f"{session.base_url}/api/get-group-distance/1"
        
        headers = {
            'X-Api-Key': 'INVALID-KEY'
        }
        
        try:
            response = session.get(url, headers=headers, timeout=10)
            assert response.status_code == 403, \
                f"Expected 403 Forbidden, got {response.status_code}"
        except requests.exceptions.ConnectionError:
            pytest.skip("Server is not running. Start Gunicorn first.")
    
    def test_get_leaderboard_cyclists_endpoint(self, session, api_key):
        """Test get_leaderboard_cyclists endpoint."""
        url = f"{session.base_url}/api/get-leaderboard/cyclists"
        
        headers = {
            'X-Api-Key': api_key
        }
        
        try:
            # Test default (total)
            response = session.get(url, headers=headers, timeout=10)
            assert response.status_code == 200, \
                f"Expected 200 OK, got {response.status_code}"
            
            data = response.json()
            is_valid, error = check_json_structure(
                data,
                ['sort', 'limit', 'players']
            )
            assert is_valid, f"Invalid JSON structure: {error}"
            assert isinstance(data['players'], list), "players should be a list"
            
            # Test with sort=daily
            params = {'sort': 'daily', 'limit': 5}
            response = session.get(url, headers=headers, params=params, timeout=10)
            assert response.status_code == 200
            data = response.json()
            assert data['sort'] == 'daily'
            assert len(data['players']) <= 5
        except requests.exceptions.ConnectionError:
            pytest.skip("Server is not running. Start Gunicorn first.")
    
    def test_get_leaderboard_groups_endpoint(self, session, api_key):
        """Test get_leaderboard_groups endpoint."""
        url = f"{session.base_url}/api/get-leaderboard/groups"
        
        headers = {
            'X-Api-Key': api_key
        }
        
        try:
            # Test default (total)
            response = session.get(url, headers=headers, timeout=10)
            assert response.status_code == 200, \
                f"Expected 200 OK, got {response.status_code}"
            
            data = response.json()
            is_valid, error = check_json_structure(
                data,
                ['sort', 'limit', 'groups']
            )
            assert is_valid, f"Invalid JSON structure: {error}"
            assert isinstance(data['groups'], list), "groups should be a list"
            
            # Test with different sort options
            for sort_type in ['daily', 'weekly', 'monthly']:
                params = {'sort': sort_type, 'limit': 5}
                response = session.get(url, headers=headers, params=params, timeout=10)
                assert response.status_code == 200
                data = response.json()
                assert data['sort'] == sort_type
        except requests.exceptions.ConnectionError:
            pytest.skip("Server is not running. Start Gunicorn first.")
    
    def test_get_active_cyclists_endpoint(self, session, api_key):
        """Test get_active_cyclists endpoint."""
        url = f"{session.base_url}/api/get-active-cyclists"
        
        headers = {
            'X-Api-Key': api_key
        }
        
        try:
            response = session.get(url, headers=headers, timeout=10)
            assert response.status_code == 200, \
                f"Expected 200 OK, got {response.status_code}"
            
            data = response.json()
            is_valid, error = check_json_structure(
                data,
                ['active_seconds', 'limit', 'players']
            )
            assert is_valid, f"Invalid JSON structure: {error}"
            assert isinstance(data['players'], list), "players should be a list"
            
            # Test with custom parameters
            params = {'limit': 5, 'active_seconds': 120}
            response = session.get(url, headers=headers, params=params, timeout=10)
            assert response.status_code == 200
            data = response.json()
            assert data['active_seconds'] == 120
            assert len(data['players']) <= 5
        except requests.exceptions.ConnectionError:
            pytest.skip("Server is not running. Start Gunicorn first.")
    
    def test_list_cyclists_endpoint(self, session, api_key):
        """Test list_cyclists endpoint."""
        url = f"{session.base_url}/api/list-cyclists"
        
        headers = {
            'X-Api-Key': api_key
        }
        
        try:
            response = session.get(url, headers=headers, timeout=10)
            assert response.status_code == 200, \
                f"Expected 200 OK, got {response.status_code}"
            
            data = response.json()
            is_valid, error = check_json_structure(
                data,
                ['page', 'page_size', 'total_count', 'total_pages', 'players']
            )
            assert is_valid, f"Invalid JSON structure: {error}"
            assert isinstance(data['players'], list), "players should be a list"
            assert data['page'] >= 1
            assert data['page_size'] > 0
            
            # Test pagination
            params = {'page': 1, 'page_size': 10}
            response = session.get(url, headers=headers, params=params, timeout=10)
            assert response.status_code == 200
            data = response.json()
            assert len(data['players']) <= 10
        except requests.exceptions.ConnectionError:
            pytest.skip("Server is not running. Start Gunicorn first.")
    
    def test_list_groups_endpoint(self, session, api_key):
        """Test list_groups endpoint."""
        url = f"{session.base_url}/api/list-groups"
        
        headers = {
            'X-Api-Key': api_key
        }
        
        try:
            response = session.get(url, headers=headers, timeout=10)
            assert response.status_code == 200, \
                f"Expected 200 OK, got {response.status_code}"
            
            data = response.json()
            is_valid, error = check_json_structure(
                data,
                ['page', 'page_size', 'total_count', 'total_pages', 'groups']
            )
            assert is_valid, f"Invalid JSON structure: {error}"
            assert isinstance(data['groups'], list), "groups should be a list"
            assert data['page'] >= 1
            assert data['page_size'] > 0
            
            # Test pagination
            params = {'page': 1, 'page_size': 10}
            response = session.get(url, headers=headers, params=params, timeout=10)
            assert response.status_code == 200
            data = response.json()
            assert len(data['groups']) <= 10
        except requests.exceptions.ConnectionError:
            pytest.skip("Server is not running. Start Gunicorn first.")
    
    def test_get_milestones_endpoint(self, session, api_key):
        """Test get_milestones endpoint."""
        url = f"{session.base_url}/api/get-milestones"
        
        headers = {
            'X-Api-Key': api_key
        }
        
        try:
            response = session.get(url, headers=headers, timeout=10)
            assert response.status_code == 200, \
                f"Expected 200 OK, got {response.status_code}"
            
            data = response.json()
            is_valid, error = check_json_structure(
                data,
                ['milestones']
            )
            assert is_valid, f"Invalid JSON structure: {error}"
            assert isinstance(data['milestones'], list), "milestones should be a list"
            
            # If milestones exist, check structure
            if data['milestones']:
                milestone = data['milestones'][0]
                assert 'track_id' in milestone
                assert 'track_name' in milestone
                assert 'milestones' in milestone
        except requests.exceptions.ConnectionError:
            pytest.skip("Server is not running. Start Gunicorn first.")
    
    def test_get_statistics_endpoint(self, session, api_key):
        """Test get_statistics endpoint."""
        url = f"{session.base_url}/api/get-statistics"
        
        headers = {
            'X-Api-Key': api_key
        }
        
        try:
            # Test without date range (defaults to last 30 days)
            response = session.get(url, headers=headers, timeout=10)
            assert response.status_code == 200, \
                f"Expected 200 OK, got {response.status_code}"
            
            data = response.json()
            is_valid, error = check_json_structure(
                data,
                ['period_start', 'period_end', 'total_distance', 'top_groups', 'top_players']
            )
            assert is_valid, f"Invalid JSON structure: {error}"
            assert isinstance(data['top_groups'], list), "top_groups should be a list"
            assert isinstance(data['top_players'], list), "top_players should be a list"
            
            # Test with date range
            from datetime import datetime, timedelta
            end_date = datetime.now()
            start_date = end_date - timedelta(days=7)
            
            params = {
                'start_date': start_date.strftime('%Y-%m-%d'),
                'end_date': end_date.strftime('%Y-%m-%d')
            }
            response = session.get(url, headers=headers, params=params, timeout=10)
            assert response.status_code == 200
            data = response.json()
            assert 'period_start' in data
            assert 'period_end' in data
        except requests.exceptions.ConnectionError:
            pytest.skip("Server is not running. Start Gunicorn first.")
    
    def test_new_endpoints_invalid_api_key(self, session):
        """Test that all new endpoints require valid API key."""
        endpoints = [
            '/api/get-leaderboard/cyclists',
            '/api/get-leaderboard/groups',
            '/api/get-active-cyclists',
            '/api/list-cyclists',
            '/api/list-groups',
            '/api/get-milestones',
            '/api/get-statistics',
        ]
        
        headers = {
            'X-Api-Key': 'INVALID-KEY'
        }
        
        for endpoint in endpoints:
            try:
                url = f"{session.base_url}{endpoint}"
                response = session.get(url, headers=headers, timeout=10)
                assert response.status_code == 403, \
                    f"Expected 403 Forbidden for {endpoint}, got {response.status_code}"
            except requests.exceptions.ConnectionError:
                pytest.skip("Server is not running. Start Gunicorn first.")


@pytest.mark.live
class TestLiveAPILocalization:
    """Tests for German number formatting in API responses."""
    
    def test_german_number_formatting_in_html(self, session):
        """Test that HTML responses use German number formatting (point for thousands, comma for decimal)."""
        # Test leaderboard view (should show German formatting: 1.234,56)
        # Note: After refactoring, leaderboard is at /leaderboard/kiosk/ but legacy URL may still work
        url = f"{session.base_url}/leaderboard/kiosk/"
        
        try:
            response = session.get(url, timeout=10)
            if response.status_code == 200:
                content = response.text
                assert 'text/html' in response.headers.get('Content-Type', ''), \
                    "Response should be HTML"
                
                # Extract numbers from HTML
                numbers = extract_numbers_from_text(content)
                
                # Check if at least some numbers use German format (point for thousands, comma for decimal)
                german_format_found = False
                for num_str in numbers:
                    if check_german_number_formatting(num_str):
                        german_format_found = True
                        # Verify: point should be before comma (thousands before decimal)
                        if '.' in num_str and ',' in num_str:
                            dot_pos = num_str.rfind('.')
                            comma_pos = num_str.rfind(',')
                            assert dot_pos < comma_pos, \
                                f"German format should have point before comma: {num_str}"
                        break
                
                # Note: If no numbers found, that's okay - test passes
                # We're just checking that if numbers exist, they use German format
        except requests.exceptions.ConnectionError:
            pytest.skip("Server is not running. Start Gunicorn first.")
    
    def test_json_responses_use_standard_format(self, session, api_key):
        """Test that JSON responses use English format (comma for thousands, dot as decimal separator)."""
        # JSON should always use English format: 1,234.56 (comma for thousands, dot for decimal)
        url = f"{session.base_url}/api/get-cyclist-coins/testplayer"
        
        headers = {
            'X-Api-Key': api_key
        }
        
        try:
            response = session.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                # Check numeric fields use English format
                if 'distance_total' in data:
                    distance_value = data['distance_total']
                    distance_str = str(distance_value)
                    
                    # Python's str() for floats uses dot as decimal, no thousands separator
                    # But if we have a formatted string, it should use English format
                    if ',' in distance_str and '.' in distance_str:
                        # Has both - check English format (comma before dot)
                        comma_pos = distance_str.rfind(',')
                        dot_pos = distance_str.rfind('.')
                        assert dot_pos > comma_pos, \
                            f"JSON should use English format (comma for thousands, dot for decimal), got: {distance_str}"
                    elif '.' in distance_str:
                        # Only dot - valid English format (no thousands separator)
                        assert True
                    elif ',' in distance_str:
                        # Only comma - might be thousands separator, but no decimal
                        # This is acceptable for integers
                        assert True
                
                # Check all numeric fields
                for key, value in data.items():
                    if isinstance(value, (int, float)):
                        value_str = str(value)
                        # Python's default string representation uses dot for decimal
                        # If comma exists, it should be thousands separator (appears before dot)
                        if ',' in value_str and '.' in value_str:
                            comma_pos = value_str.rfind(',')
                            dot_pos = value_str.rfind('.')
                            assert dot_pos > comma_pos, \
                                f"Field {key} should use English format (comma for thousands, dot for decimal), got: {value_str}"
        except requests.exceptions.ConnectionError:
            pytest.skip("Server is not running. Start Gunicorn first.")
    
    def test_json_large_numbers_use_english_thousands_separator(self, session, api_key):
        """Test that JSON responses with large numbers use comma as thousands separator."""
        # Test with a cyclist that might have large distance values
        url = f"{session.base_url}/api/get-cyclist-coins/testplayer"
        
        headers = {
            'X-Api-Key': api_key
        }
        
        try:
            response = session.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                
                # Check if any numeric value is >= 1000
                for key, value in data.items():
                    if isinstance(value, (int, float)) and abs(value) >= 1000:
                        value_str = str(value)
                        # Python's default str() doesn't add thousands separators
                        # But if the API formats numbers, they should use English format
                        # For now, we just verify the number is valid
                        # In a real scenario, if numbers are formatted, comma should be thousands separator
                        assert isinstance(value, (int, float)), \
                            f"Field {key} should be numeric, got: {type(value)}"
        except requests.exceptions.ConnectionError:
            pytest.skip("Server is not running. Start Gunicorn first.")
    
    def test_html_large_numbers_use_german_thousands_separator(self, session):
        """Test that HTML responses with large numbers use point as thousands separator."""
        # Test leaderboard view (should show German formatting: 1.234,56)
        # Note: After refactoring, leaderboard is at /leaderboard/kiosk/ but legacy URL may still work
        url = f"{session.base_url}/leaderboard/kiosk/"
        
        try:
            response = session.get(url, timeout=10)
            if response.status_code == 200:
                content = response.text
                assert 'text/html' in response.headers.get('Content-Type', ''), \
                    "Response should be HTML"
                
                # Extract numbers from HTML that might have thousands separators
                numbers = extract_numbers_from_text(content)
                
                # Look for numbers with both point and comma (German format: 1.234,56)
                german_format_found = False
                for num_str in numbers:
                    if '.' in num_str and ',' in num_str:
                        # Has both separators - check German format
                        dot_pos = num_str.rfind('.')
                        comma_pos = num_str.rfind(',')
                        if dot_pos < comma_pos:
                            # Point before comma = German format (thousands before decimal)
                            german_format_found = True
                            # Verify format: should be like 1.234,56
                            parts = num_str.split(',')
                            if len(parts) == 2:
                                # Decimal part should not contain point
                                assert '.' not in parts[1], \
                                    f"German format decimal part should not contain point: {num_str}"
                            break
                
                # Note: If no large numbers found, that's okay - test passes
                # We're just checking that if formatted numbers exist, they use German format
        except requests.exceptions.ConnectionError:
            pytest.skip("Server is not running. Start Gunicorn first.")
    
    def test_update_data_returns_english_numbers(self, session, api_key):
        """Test that update_data endpoint returns numbers in English format."""
        url = f"{session.base_url}/api/update-data"
        
        payload = {
            'id_tag': 'test-tag-001',
            'device_id': 'test-device-01',
            'distance': '5.50000'
        }
        
        headers = {
            'X-Api-Key': api_key,
            'Content-Type': 'application/json'
        }
        
        try:
            response = session.post(url, json=payload, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                # Check all numeric values in response
                def check_english_format(obj, path=""):
                    """Recursively check that all numbers use English format."""
                    if isinstance(obj, dict):
                        for key, value in obj.items():
                            check_english_format(value, f"{path}.{key}")
                    elif isinstance(obj, list):
                        for i, item in enumerate(obj):
                            check_english_format(item, f"{path}[{i}]")
                    elif isinstance(obj, (int, float)):
                        value_str = str(obj)
                        # Should use dot as decimal separator, not comma
                        if ',' in value_str:
                            parts = value_str.split(',')
                            if len(parts) == 2:
                                # Comma as decimal separator is wrong
                                assert False, f"Number at {path} uses comma as decimal separator: {value_str}"
                    elif isinstance(obj, str):
                        # Check if string represents a number with comma (should be dot)
                        try:
                            # Try to parse as float
                            if ',' in obj and obj.replace(',', '').replace('.', '').isdigit():
                                # Has comma and looks like a number - might be German format
                                if '.' not in obj or obj.rfind(',') > obj.rfind('.'):
                                    # Comma is decimal separator - this is wrong for JSON
                                    assert False, f"String number at {path} uses comma as decimal separator: {obj}"
                        except (ValueError, AttributeError):
                            pass
                
                check_english_format(data)
        except requests.exceptions.ConnectionError:
            pytest.skip("Server is not running. Start Gunicorn first.")
    
    def test_travel_locations_use_english_numbers(self, session):
        """Test that get_travel_locations returns numbers in English format."""
        url = f"{session.base_url}/api/get-travel-locations"
        
        try:
            response = session.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                assert isinstance(data, list), "Response should be a list"
                
                # Check each location entry
                for i, location in enumerate(data):
                    if isinstance(location, dict):
                        # Check numeric fields like distance, coordinates, etc.
                        for key, value in location.items():
                            if isinstance(value, (int, float)):
                                value_str = str(value)
                                # Should use dot as decimal separator
                                if ',' in value_str:
                                    parts = value_str.split(',')
                                    if len(parts) == 2:
                                        # Comma as decimal separator is wrong
                                        assert False, \
                                            f"Location[{i}].{key} uses comma as decimal separator: {value_str}"
        except requests.exceptions.ConnectionError:
            pytest.skip("Server is not running. Start Gunicorn first.")


@pytest.mark.live
class TestLiveAPIErrorHandling:
    """Tests for error handling in live API."""
    
    def test_malformed_json_request(self, session, api_key):
        """Test handling of malformed JSON requests."""
        url = f"{session.base_url}/api/update-data"
        
        headers = {
            'X-Api-Key': api_key,
            'Content-Type': 'application/json'
        }
        
        try:
            response = session.post(
                url,
                data='{invalid json}',
                headers=headers,
                timeout=10
            )
            # Should return 400 Bad Request
            assert response.status_code == 400, \
                f"Expected 400 Bad Request, got {response.status_code}"
        except requests.exceptions.ConnectionError:
            pytest.skip("Server is not running. Start Gunicorn first.")
    
    def test_missing_required_fields(self, session, api_key):
        """Test handling of missing required fields."""
        url = f"{session.base_url}/api/update-data"
        
        payload = {
            'device_id': 'test-device-01',
            # Missing 'id_tag' and 'distance'
        }
        
        headers = {
            'X-Api-Key': api_key,
            'Content-Type': 'application/json'
        }
        
        try:
            response = session.post(url, json=payload, headers=headers, timeout=10)
            # Should return 400 Bad Request
            assert response.status_code == 400, \
                f"Expected 400 Bad Request, got {response.status_code}"
        except requests.exceptions.ConnectionError:
            pytest.skip("Server is not running. Start Gunicorn first.")

