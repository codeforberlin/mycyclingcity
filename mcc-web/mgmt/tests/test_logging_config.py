# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    test_logging_config.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

"""
Unit tests for LoggingConfig model.

Tests cover:
- Singleton pattern
- should_store_level method
- Log level filtering logic
"""

import pytest
from django.test import TestCase

from mgmt.models import LoggingConfig


@pytest.mark.unit
@pytest.mark.django_db
class TestLoggingConfig:
    """Tests for LoggingConfig model."""
    
    def test_get_config_creates_singleton(self):
        """Test that get_config creates a singleton instance."""
        # Clear any existing config
        LoggingConfig.objects.all().delete()
        
        # Get config (should create new instance)
        config1 = LoggingConfig.get_config()
        assert config1.pk == 1
        # Default is 'INFO', not 'WARNING'
        assert config1.min_log_level == 'INFO'
        
        # Get config again (should return same instance)
        config2 = LoggingConfig.get_config()
        assert config2.pk == config1.pk
        assert config2.min_log_level == config1.min_log_level
        
        # Verify only one instance exists
        assert LoggingConfig.objects.count() == 1
    
    def test_should_store_level_warning(self):
        """Test should_store_level with WARNING min level."""
        config = LoggingConfig.get_config()
        config.min_log_level = 'WARNING'
        config.save()
        
        # Should store WARNING and above
        assert config.should_store_level('WARNING') is True
        assert config.should_store_level('ERROR') is True
        assert config.should_store_level('CRITICAL') is True
        
        # Should not store below WARNING
        assert config.should_store_level('DEBUG') is False
        assert config.should_store_level('INFO') is False
    
    def test_should_store_level_debug(self):
        """Test should_store_level with DEBUG min level."""
        config = LoggingConfig.get_config()
        config.min_log_level = 'DEBUG'
        config.save()
        
        # Should store all levels
        assert config.should_store_level('DEBUG') is True
        assert config.should_store_level('INFO') is True
        assert config.should_store_level('WARNING') is True
        assert config.should_store_level('ERROR') is True
        assert config.should_store_level('CRITICAL') is True
    
    def test_should_store_level_info(self):
        """Test should_store_level with INFO min level."""
        config = LoggingConfig.get_config()
        config.min_log_level = 'INFO'
        config.save()
        
        # Should store INFO and above
        assert config.should_store_level('INFO') is True
        assert config.should_store_level('WARNING') is True
        assert config.should_store_level('ERROR') is True
        assert config.should_store_level('CRITICAL') is True
        
        # Should not store DEBUG
        assert config.should_store_level('DEBUG') is False
    
    def test_should_store_level_error(self):
        """Test should_store_level with ERROR min level."""
        config = LoggingConfig.get_config()
        config.min_log_level = 'ERROR'
        config.save()
        
        # Should store ERROR and above
        assert config.should_store_level('ERROR') is True
        assert config.should_store_level('CRITICAL') is True
        
        # Should not store below ERROR
        assert config.should_store_level('DEBUG') is False
        assert config.should_store_level('INFO') is False
        assert config.should_store_level('WARNING') is False
    
    def test_should_store_level_critical(self):
        """Test should_store_level with CRITICAL min level."""
        config = LoggingConfig.get_config()
        config.min_log_level = 'CRITICAL'
        config.save()
        
        # Should only store CRITICAL
        assert config.should_store_level('CRITICAL') is True
        
        # Should not store below CRITICAL
        assert config.should_store_level('DEBUG') is False
        assert config.should_store_level('INFO') is False
        assert config.should_store_level('WARNING') is False
        assert config.should_store_level('ERROR') is False
    
    def test_should_store_level_unknown_level(self):
        """Test should_store_level with unknown level (should default to True)."""
        config = LoggingConfig.get_config()
        config.min_log_level = 'WARNING'
        config.save()
        
        # Unknown level should default to storing
        assert config.should_store_level('UNKNOWN') is True
