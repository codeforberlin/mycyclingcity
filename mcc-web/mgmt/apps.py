# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    apps.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
from django.apps import AppConfig
import logging
import threading
import time


class MgmtConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'mgmt'
    
    # Class variable to track the background thread
    _level_check_thread = None
    _level_check_running = False
    
    def ready(self):
        """Configure logging levels based on LoggingConfig."""
        # Import here to avoid circular dependencies
        from django.db.models.signals import post_save, post_migrate
        
        # Connect signal to update logger levels when LoggingConfig is saved
        # This avoids database access during app initialization
        def connect_signal():
            try:
                from .models import LoggingConfig
                post_save.connect(self._on_logging_config_saved, sender=LoggingConfig)
            except Exception:
                pass
        
        # Connect the signal immediately (no DB access)
        connect_signal()
        
        # Update logger levels after migrations are complete
        # This avoids the RuntimeWarning about database access during initialization
        def update_levels_after_migrate(**kwargs):
            try:
                from .models import LoggingConfig
                config = LoggingConfig.get_config()
                self._update_logger_levels(config.min_log_level)
                # Start background thread to periodically check for changes
                # This ensures all workers (even those not handling the admin request) get updates
                self._start_level_check_thread()
            except Exception:
                # Database not ready yet, will be set on first config save
                pass
        
        post_migrate.connect(update_levels_after_migrate, sender=self, weak=False)
    
    @classmethod
    def _start_level_check_thread(cls):
        """Start a background thread that periodically checks LoggingConfig and updates logger levels."""
        if cls._level_check_running:
            return
        
        cls._level_check_running = True
        
        def check_levels_periodically():
            """Background thread that checks LoggingConfig every 5 seconds."""
            last_level = None
            while cls._level_check_running:
                try:
                    from .models import LoggingConfig
                    config = LoggingConfig.get_config()
                    current_level = config.min_log_level
                    
                    # Only update if level has changed
                    if current_level != last_level:
                        cls._update_logger_levels(current_level)
                        last_level = current_level
                except Exception:
                    # Silently ignore errors (database might not be ready, etc.)
                    pass
                
                # Check every 5 seconds
                time.sleep(5)
        
        cls._level_check_thread = threading.Thread(
            target=check_levels_periodically,
            daemon=True,
            name='LoggingConfigLevelChecker'
        )
        cls._level_check_thread.start()
    
    @staticmethod
    def _update_logger_levels(min_log_level):
        """
        Update logger levels and handler levels based on LoggingConfig.
        
        If LoggingConfig is set to DEBUG, we need to set logger levels to DEBUG
        so that DEBUG messages reach the handlers and can be stored in the database.
        If LoggingConfig is set to INFO, we need to set logger levels to INFO
        so that DEBUG messages are filtered out and not written to files.
        
        We also update handler levels to match, so that file handlers don't write
        DEBUG logs when LoggingConfig is set to INFO or higher.
        
        Args:
            min_log_level: String level from LoggingConfig ('DEBUG', 'INFO', 'WARNING', etc.)
        """
        # Map LoggingConfig levels to logging module levels
        level_map = {
            'DEBUG': logging.DEBUG,
            'INFO': logging.INFO,
            'WARNING': logging.WARNING,
            'ERROR': logging.ERROR,
            'CRITICAL': logging.CRITICAL,
        }
        
        target_level = level_map.get(min_log_level, logging.INFO)
        
        # Update logger levels for all application loggers
        # This ensures that logs at the configured level and above reach the handlers
        app_loggers = ['api', 'mgmt', 'iot', 'kiosk', 'game']
        handler_names = ['api_file', 'mgmt_file', 'iot_file', 'kiosk_file', 'game_file']
        
        for logger_name, handler_name in zip(app_loggers, handler_names):
            logger = logging.getLogger(logger_name)
            # Always set logger level to match LoggingConfig (not just when lower)
            # This allows DEBUG messages to reach handlers when config is DEBUG
            # and filters out DEBUG messages when config is INFO or higher
            logger.setLevel(target_level)
            
            # Also update handler levels to match LoggingConfig
            # This ensures that file handlers don't write DEBUG logs when config is INFO or higher
            for handler in logger.handlers:
                # Check if this is a file handler for this app
                # File handlers are typically RotatingFileHandler instances
                handler_class_name = handler.__class__.__name__
                if handler_class_name in ['RotatingFileHandler', 'FileHandler']:
                    # Try to identify the handler by checking its filename attribute
                    handler_filename = getattr(handler, 'baseFilename', None) or getattr(handler, 'filename', None)
                    if handler_filename and handler_name.replace('_file', '') in handler_filename:
                        handler.setLevel(target_level)
                # Also check by handler name if available
                if hasattr(handler, 'name') and handler.name == handler_name:
                    handler.setLevel(target_level)
            
            # Also update all existing child loggers (e.g., 'api.views', 'api.models', etc.)
            # This ensures that child loggers also respect the new level
            for existing_logger_name in list(logging.Logger.manager.loggerDict.keys()):
                if existing_logger_name.startswith(logger_name + '.'):
                    child_logger = logging.getLogger(existing_logger_name)
                    child_logger.setLevel(target_level)
                    # Also update child logger handlers
                    for handler in child_logger.handlers:
                        handler_class_name = handler.__class__.__name__
                        if handler_class_name in ['RotatingFileHandler', 'FileHandler']:
                            handler_filename = getattr(handler, 'baseFilename', None) or getattr(handler, 'filename', None)
                            if handler_filename and handler_name.replace('_file', '') in handler_filename:
                                handler.setLevel(target_level)
    
    @staticmethod
    def _on_logging_config_saved(sender, instance, **kwargs):
        """
        Update logger levels when LoggingConfig is saved.
        
        This signal handler ensures that when LoggingConfig is changed in the Admin GUI,
        the logger levels are immediately updated without requiring a server restart.
        
        Also ensures the background thread is running to update all workers.
        """
        MgmtConfig._update_logger_levels(instance.min_log_level)
        # Ensure background thread is running (in case it wasn't started yet)
        MgmtConfig._start_level_check_thread()