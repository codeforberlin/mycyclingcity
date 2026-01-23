# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    logging_handler.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
"""
Custom logging handler for storing critical logs in the database.

This handler writes WARNING, ERROR, and CRITICAL log entries to the ApplicationLog model
for viewing in the Django Admin interface. It uses batch inserts for better performance.
"""
import logging
from logging.handlers import RotatingFileHandler
from django.db import transaction
from django.utils import timezone
from django.conf import settings
import threading
import queue
import time


class DatabaseLogHandler(logging.Handler):
    """
    Custom logging handler that stores log entries in the database.
    
    By default, only WARNING, ERROR, and CRITICAL logs are stored.
    DEBUG and INFO logs can be enabled via LOG_DB_DEBUG setting.
    
    Uses a background thread with batch inserts for better performance.
    """
    
    def __init__(self, level=logging.DEBUG, batch_size=10, flush_interval=5.0):
        """
        Initialize the database log handler.
        
        Args:
            level: Minimum log level to receive (default: DEBUG to receive all logs)
            batch_size: Number of log entries to batch before inserting (default: 10)
            flush_interval: Maximum seconds to wait before flushing batch (default: 5.0)
        
        Note: The handler receives all logs (DEBUG and above), but only stores
        WARNING/ERROR/CRITICAL by default. DEBUG/INFO can be enabled via LOG_DB_DEBUG.
        """
        # Always set to DEBUG to receive all log levels
        # Filtering happens in _should_store() based on LOG_DB_DEBUG setting
        super().__init__(logging.DEBUG)
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.log_queue = queue.Queue()
        self.batch = []
        self.last_flush = time.time()
        self.thread = None
        self._shutdown = False
        self._start_worker_thread()
    
    def _start_worker_thread(self):
        """Start the background worker thread for batch processing."""
        if self.thread is None or not self.thread.is_alive():
            self.thread = threading.Thread(target=self._worker, daemon=True)
            self.thread.start()
    
    def emit(self, record):
        """
        Emit a log record to the database.
        
        This method is called by the logging system for each log record.
        It queues the record for batch processing by the worker thread.
        """
        try:
            # Check if we should store this log level
            if not self._should_store(record.levelno):
                return
            
            # Format the log record
            log_entry = self._format_record(record)
            
            # Add to queue for batch processing
            try:
                self.log_queue.put(log_entry, block=False)
                # Debug: Log when we successfully queue a log entry (only for WARNING and above to avoid spam)
                # Write to stderr so it appears in gunicorn_error.log
                if record.levelno >= logging.WARNING:
                    import sys
                    sys.stderr.write(f"[DatabaseLogHandler] Queued {record.levelname} from {record.name}: {record.getMessage()[:80]}\n")
                    sys.stderr.flush()
            except queue.Full:
                # Queue is full, skip this log entry to avoid blocking
                print(f"DatabaseLogHandler queue is full, dropping log entry: {record.levelname} - {record.getMessage()[:100]}")
        except Exception as e:
            # Avoid infinite recursion if logging fails
            import traceback
            print(f"Error in DatabaseLogHandler.emit: {e}")
            print(f"Traceback: {traceback.format_exc()}")
            self.handleError(record)
    
    def _should_store(self, levelno):
        """
        Determine if a log level should be stored in the database.
        
        Checks the LoggingConfig model in the database first.
        Falls back to LOG_DB_DEBUG setting if config doesn't exist.
        """
        # Map levelno to level string
        level_map = {
            logging.DEBUG: 'DEBUG',
            logging.INFO: 'INFO',
            logging.WARNING: 'WARNING',
            logging.ERROR: 'ERROR',
            logging.CRITICAL: 'CRITICAL',
        }
        level_str = level_map.get(levelno, 'DEBUG')
        
        try:
            # Try to get configuration from database
            # Lazy import to avoid circular dependency
            from .models import LoggingConfig
            
            config = LoggingConfig.get_config()
            return config.should_store_level(level_str)
        except Exception:
            # If database access fails (e.g., during migrations), fall back to settings
            # This allows the handler to work even if the table doesn't exist yet
            if levelno >= logging.WARNING:
                return True
            
            # Check if DEBUG/INFO logging is enabled via environment variable
            if levelno >= logging.DEBUG:
                return getattr(settings, 'LOG_DB_DEBUG', False)
            
            return False
    
    def _format_record(self, record):
        """Format a log record for database storage."""
        # Get exception info if available
        exception_info = None
        if record.exc_info:
            import traceback
            exception_info = ''.join(traceback.format_exception(*record.exc_info))
        
        # Extract extra data
        extra_data = {}
        for key, value in record.__dict__.items():
            if key not in [
                'name', 'msg', 'args', 'created', 'filename', 'funcName',
                'levelname', 'levelno', 'lineno', 'module', 'msecs',
                'message', 'pathname', 'process', 'processName', 'relativeCreated',
                'thread', 'threadName', 'exc_info', 'exc_text', 'stack_info'
            ]:
                try:
                    # Try to serialize the value
                    import json
                    json.dumps(value)
                    extra_data[key] = value
                except (TypeError, ValueError):
                    extra_data[key] = str(value)
        
        return {
            'level': record.levelname,
            'logger_name': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'timestamp': timezone.now(),
            'exception_info': exception_info,
            'extra_data': extra_data if extra_data else None,
        }
    
    def _worker(self):
        """Background worker thread that processes log entries in batches."""
        while not self._shutdown:
            try:
                # Try to get a log entry with timeout
                try:
                    entry = self.log_queue.get(timeout=1.0)
                    self.batch.append(entry)
                except queue.Empty:
                    entry = None
                
                # Check if we should flush the batch
                should_flush = (
                    len(self.batch) >= self.batch_size or
                    (entry is None and len(self.batch) > 0 and 
                     time.time() - self.last_flush >= self.flush_interval)
                )
                
                if should_flush and len(self.batch) > 0:
                    self._flush_batch()
                    
            except Exception as e:
                # Log error to console to avoid recursion
                import traceback
                print(f"Error in DatabaseLogHandler worker: {e}")
                print(f"Traceback: {traceback.format_exc()}")
                time.sleep(1)
    
    def _flush_batch(self):
        """Flush the current batch of log entries to the database."""
        if not self.batch:
            return
        
        try:
            # Lazy import to avoid circular dependency during Django startup
            from .models import ApplicationLog
            
            batch_size = len(self.batch)
            with transaction.atomic():
                # Bulk create log entries
                log_entries = [
                    ApplicationLog(**entry) for entry in self.batch
                ]
                ApplicationLog.objects.bulk_create(log_entries, ignore_conflicts=True)
            
            import sys
            sys.stderr.write(f"[DatabaseLogHandler] Flushed {batch_size} log entries to database\n")
            sys.stderr.flush()
            self.batch.clear()
            self.last_flush = time.time()
        except Exception as e:
            # Log error to console to avoid recursion
            import traceback
            print(f"Error flushing log batch to database: {e}")
            print(f"Traceback: {traceback.format_exc()}")
            # Clear batch to prevent memory issues
            self.batch.clear()
    
    def close(self):
        """Close the handler and flush any remaining log entries."""
        self._shutdown = True
        if self.thread and self.thread.is_alive():
            # Wait for thread to finish (with timeout)
            self.thread.join(timeout=5.0)
        
        # Flush any remaining entries
        if self.batch:
            self._flush_batch()
        
        super().close()


class DynamicLevelFileHandler(RotatingFileHandler):
    """
    Custom file handler that dynamically checks LoggingConfig to determine
    if a log record should be written to the file.
    
    This ensures that all workers respect the LoggingConfig settings immediately,
    even if they haven't received the update signal yet.
    """
    
    def __init__(self, *args, **kwargs):
        """Initialize the dynamic level file handler."""
        # Always set handler level to DEBUG to receive all logs
        # Filtering happens in emit() based on LoggingConfig
        super().__init__(*args, **kwargs)
        self.setLevel(logging.DEBUG)
    
    def emit(self, record):
        """
        Emit a log record to the file, but only if LoggingConfig allows it.
        
        This method checks the LoggingConfig dynamically, ensuring that
        all workers respect the current configuration even if they haven't
        received the update signal yet.
        """
        # Check if we should write this log level based on LoggingConfig
        if not self._should_write(record.levelno):
            return
        
        # Call parent emit to write to file
        super().emit(record)
    
    def _should_write(self, levelno):
        """
        Determine if a log level should be written to the file.
        
        Checks the LoggingConfig model in the database dynamically.
        Falls back to WARNING if config doesn't exist.
        
        Args:
            levelno: Log level number (logging.DEBUG, logging.INFO, etc.)
        
        Returns:
            bool: True if the level should be written to the file
        """
        # Map levelno to level string
        level_map = {
            logging.DEBUG: 'DEBUG',
            logging.INFO: 'INFO',
            logging.WARNING: 'WARNING',
            logging.ERROR: 'ERROR',
            logging.CRITICAL: 'CRITICAL',
        }
        level_str = level_map.get(levelno, 'DEBUG')
        
        try:
            # Try to get configuration from database
            # Lazy import to avoid circular dependency
            from mgmt.models import LoggingConfig
            
            config = LoggingConfig.get_config()
            return config.should_store_level(level_str)
        except Exception:
            # If database access fails (e.g., during migrations), fall back to WARNING
            # This allows the handler to work even if the table doesn't exist yet
            return levelno >= logging.WARNING
