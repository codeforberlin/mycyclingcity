# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    test_logging_handler.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

"""
Unit tests for DatabaseLogHandler.

Tests cover:
- Handler initialization
- Log record queuing
- Batch processing
- Database storage
- Log level filtering
- Error handling
"""

import pytest
import logging
import time
from django.test import TestCase
from django.utils import timezone
from datetime import timedelta

from mgmt.logging_handler import DatabaseLogHandler
from mgmt.models import ApplicationLog, LoggingConfig


@pytest.mark.unit
@pytest.mark.django_db
class TestDatabaseLogHandler:
    """Tests for DatabaseLogHandler."""
    
    def test_handler_initialization(self):
        """Test that handler initializes correctly."""
        handler = DatabaseLogHandler(batch_size=5, flush_interval=1.0)
        
        assert handler.batch_size == 5
        assert handler.flush_interval == 1.0
        assert handler.level == logging.DEBUG
        assert handler.thread is not None
        assert handler.thread.is_alive()
        assert handler._shutdown is False
        
        # Cleanup
        handler.close()
    
    def test_handler_queues_log_record(self):
        """Test that handler queues log records correctly."""
        handler = DatabaseLogHandler(batch_size=1, flush_interval=0.1)
        
        # Create a test log record
        logger = logging.getLogger('test_logger')
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        
        # Send a WARNING log
        logger.warning("Test warning message")
        
        # Wait for processing
        time.sleep(0.5)
        
        # Check that log was queued (queue should be empty after processing)
        assert handler.log_queue.qsize() == 0
        
        # Cleanup
        logger.removeHandler(handler)
        handler.close()
    
    def test_handler_stores_warning_in_database(self):
        """Test that WARNING logs are stored in database."""
        # Ensure LoggingConfig exists with WARNING level
        config = LoggingConfig.get_config()
        config.min_log_level = 'WARNING'
        config.save()
        
        handler = DatabaseLogHandler(batch_size=1, flush_interval=0.1)
        
        # Create a test log record
        logger = logging.getLogger('test_logger')
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        
        # Send a WARNING log
        logger.warning("Test warning message for database")
        
        # Wait for batch processing
        time.sleep(0.5)
        
        # Check database
        logs = ApplicationLog.objects.filter(message__contains="Test warning message for database")
        assert logs.count() == 1
        
        log = logs.first()
        assert log.level == 'WARNING'
        assert log.logger_name == 'test_logger'
        assert 'Test warning message for database' in log.message
        
        # Cleanup
        logger.removeHandler(handler)
        handler.close()
    
    def test_handler_stores_error_in_database(self):
        """Test that ERROR logs are stored in database."""
        # Ensure LoggingConfig exists with WARNING level
        config = LoggingConfig.get_config()
        config.min_log_level = 'WARNING'
        config.save()
        
        handler = DatabaseLogHandler(batch_size=1, flush_interval=0.1)
        
        # Create a test log record
        logger = logging.getLogger('test_logger')
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        
        # Send an ERROR log
        logger.error("Test error message for database")
        
        # Wait for batch processing
        time.sleep(0.5)
        
        # Check database
        logs = ApplicationLog.objects.filter(message__contains="Test error message for database")
        assert logs.count() == 1
        
        log = logs.first()
        assert log.level == 'ERROR'
        assert log.logger_name == 'test_logger'
        
        # Cleanup
        logger.removeHandler(handler)
        handler.close()
    
    def test_handler_filters_debug_logs(self):
        """Test that DEBUG logs are filtered when min_log_level is WARNING."""
        # Ensure LoggingConfig exists with WARNING level
        config = LoggingConfig.get_config()
        config.min_log_level = 'WARNING'
        config.save()
        
        handler = DatabaseLogHandler(batch_size=1, flush_interval=0.1)
        
        # Create a test log record
        logger = logging.getLogger('test_logger')
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        
        # Send a DEBUG log
        logger.debug("Test debug message - should not be stored")
        
        # Wait for batch processing
        time.sleep(0.5)
        
        # Check database - should be empty
        logs = ApplicationLog.objects.filter(message__contains="Test debug message")
        assert logs.count() == 0
        
        # Cleanup
        logger.removeHandler(handler)
        handler.close()
    
    def test_handler_stores_debug_when_enabled(self):
        """Test that DEBUG logs are stored when min_log_level is DEBUG."""
        # Ensure LoggingConfig exists with DEBUG level
        config = LoggingConfig.get_config()
        config.min_log_level = 'DEBUG'
        config.save()
        
        handler = DatabaseLogHandler(batch_size=1, flush_interval=0.1)
        
        # Create a test log record
        logger = logging.getLogger('test_logger')
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        
        # Send a DEBUG log
        logger.debug("Test debug message - should be stored")
        
        # Wait for batch processing
        time.sleep(0.5)
        
        # Check database
        logs = ApplicationLog.objects.filter(message__contains="Test debug message - should be stored")
        assert logs.count() == 1
        
        log = logs.first()
        assert log.level == 'DEBUG'
        
        # Cleanup
        logger.removeHandler(handler)
        handler.close()
    
    def test_handler_batch_processing(self):
        """Test that handler processes logs in batches."""
        # Ensure LoggingConfig exists with WARNING level
        config = LoggingConfig.get_config()
        config.min_log_level = 'WARNING'
        config.save()
        
        handler = DatabaseLogHandler(batch_size=3, flush_interval=0.1)
        
        # Create a test log record
        logger = logging.getLogger('test_logger')
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        
        # Send multiple logs
        for i in range(5):
            logger.warning(f"Test warning message {i}")
        
        # Wait for batch processing
        time.sleep(0.5)
        
        # Check database - all logs should be stored
        logs = ApplicationLog.objects.filter(message__contains="Test warning message")
        assert logs.count() == 5
        
        # Cleanup
        logger.removeHandler(handler)
        handler.close()
    
    def test_handler_exception_info(self):
        """Test that exception info is stored correctly."""
        # Ensure LoggingConfig exists with WARNING level
        config = LoggingConfig.get_config()
        config.min_log_level = 'WARNING'
        config.save()
        
        handler = DatabaseLogHandler(batch_size=1, flush_interval=0.1)
        
        # Create a test log record
        logger = logging.getLogger('test_logger')
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        
        # Send an ERROR log with exception
        try:
            raise ValueError("Test exception")
        except ValueError:
            logger.error("Test error with exception", exc_info=True)
        
        # Wait for batch processing
        time.sleep(0.5)
        
        # Check database
        logs = ApplicationLog.objects.filter(message__contains="Test error with exception")
        assert logs.count() == 1
        
        log = logs.first()
        assert log.exception_info is not None
        assert 'ValueError' in log.exception_info
        assert 'Test exception' in log.exception_info
        
        # Cleanup
        logger.removeHandler(handler)
        handler.close()
    
    def test_handler_logger_name_preserved(self):
        """Test that logger name is preserved correctly."""
        # Ensure LoggingConfig exists with WARNING level
        config = LoggingConfig.get_config()
        config.min_log_level = 'WARNING'
        config.save()
        
        handler = DatabaseLogHandler(batch_size=1, flush_interval=0.1)
        
        # Create loggers with different names
        logger1 = logging.getLogger('api.views')
        logger1.addHandler(handler)
        logger1.setLevel(logging.DEBUG)
        
        logger2 = logging.getLogger('mgmt.admin')
        logger2.addHandler(handler)
        logger2.setLevel(logging.DEBUG)
        
        # Send logs
        logger1.warning("Test from api.views")
        logger2.warning("Test from mgmt.admin")
        
        # Wait for batch processing
        time.sleep(0.5)
        
        # Check database
        logs = ApplicationLog.objects.filter(message__contains="Test from")
        assert logs.count() == 2
        
        logger_names = set(logs.values_list('logger_name', flat=True))
        assert 'api.views' in logger_names
        assert 'mgmt.admin' in logger_names
        
        # Cleanup
        logger1.removeHandler(handler)
        logger2.removeHandler(handler)
        handler.close()
    
    def test_handler_close(self):
        """Test that handler closes correctly and flushes remaining logs."""
        # Ensure LoggingConfig exists with WARNING level
        config = LoggingConfig.get_config()
        config.min_log_level = 'WARNING'
        config.save()
        
        handler = DatabaseLogHandler(batch_size=10, flush_interval=10.0)
        
        # Create a test log record
        logger = logging.getLogger('test_logger')
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        
        # Send a log
        logger.warning("Test warning before close")
        
        # Close handler (should flush remaining logs)
        handler.close()
        
        # Wait a bit
        time.sleep(0.2)
        
        # Check database
        logs = ApplicationLog.objects.filter(message__contains="Test warning before close")
        assert logs.count() == 1
        
        # Check that thread is stopped
        assert handler._shutdown is True
        assert not handler.thread.is_alive()
        
        # Cleanup
        logger.removeHandler(handler)
