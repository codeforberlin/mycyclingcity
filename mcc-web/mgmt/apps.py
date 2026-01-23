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
    
    # Instance variable to track the background thread per process
    # IMPORTANT: With preload_app=True, ready() is called in master process,
    # but we need the thread in each worker process. Use instance variable instead of class variable.
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
        
        # Start background thread IMMEDIATELY to periodically check for changes
        # This ensures all workers (even those not handling the admin request) get updates
        # The thread will retry if database is not ready yet
        # This avoids database access during app initialization (prevents RuntimeWarning)
        # IMPORTANT: With preload_app=True, this is called in master process,
        # but after forking, each worker process needs its own thread
        self._start_level_check_thread()
        
        # Also connect to post_migrate to set levels after migrations
        # This ensures logger levels are set after database is ready
        def update_levels_after_migrate(**kwargs):
            try:
                from .models import LoggingConfig
                config = LoggingConfig.get_config()
                self._update_logger_levels(config.min_log_level)
                # Background thread should already be running, but ensure it is
                self._start_level_check_thread()
            except Exception:
                # Database not ready yet, background thread will retry
                pass
        
        post_migrate.connect(update_levels_after_migrate, sender=self, weak=False)
    
    def _start_level_check_thread(self):
        """Start a background thread that periodically checks LoggingConfig and updates logger levels."""
        # Use instance variable instead of class variable to ensure thread runs in each worker process
        # With preload_app=True, each worker process has its own instance
        if self._level_check_running:
            return
        
        self._level_check_running = True
        
        # Store reference to self for use in closure
        app_config_instance = self
        
        def check_levels_periodically():
            """Background thread that checks LoggingConfig periodically."""
            last_level = None
            # Initial delay to allow database to be ready
            time.sleep(2)
            
            # Check interval - 60 seconds is sufficient since log level is only changed for debugging
            check_interval = 60.0  # Check every 60 seconds
            
            while app_config_instance._level_check_running:
                try:
                    from .models import LoggingConfig
                    config = LoggingConfig.get_config()
                    current_level = config.min_log_level
                    
                    # Always update on first successful check (last_level is None)
                    # This ensures logger levels are set even if database wasn't ready at startup
                    # Also update if level has changed
                    if current_level != last_level or last_level is None:
                        MgmtConfig._update_logger_levels(current_level)
                        last_level = current_level
                except Exception:
                    # Silently ignore errors (database might not be ready, etc.)
                    # Continue checking - database might become available later
                    pass
                
                # Check every 60 seconds (sufficient for debugging purposes)
                time.sleep(check_interval)
        
        self._level_check_thread = threading.Thread(
            target=check_levels_periodically,
            daemon=True,
            name='LoggingConfigLevelChecker'
        )
        self._level_check_thread.start()
    
    @classmethod
    def _update_logger_levels(cls, min_log_level):
        """
        Update logger levels based on LoggingConfig.
        
        This function sets the logger level directly, ensuring efficient filtering
        at the logger level. This prevents unnecessary log message creation and
        formatting for logs that would be filtered anyway.
        
        Args:
            min_log_level: String level from LoggingConfig ('DEBUG', 'INFO', 'WARNING', etc.)
        """
        # Map string level to logging constant
        level_map = {
            'DEBUG': logging.DEBUG,
            'INFO': logging.INFO,
            'WARNING': logging.WARNING,
            'ERROR': logging.ERROR,
            'CRITICAL': logging.CRITICAL,
        }
        
        target_logger_level = level_map.get(min_log_level, logging.WARNING)
        
        # Update logger levels for all application loggers
        app_loggers = ['api', 'mgmt', 'iot', 'kiosk', 'game', 'map', 'leaderboard']
        
        for logger_name in app_loggers:
            logger = logging.getLogger(logger_name)
            # Set logger level based on LoggingConfig
            logger.setLevel(target_logger_level)
            
            # Also update all existing child loggers (e.g., 'api.views', 'api.models', etc.)
            # This ensures that child loggers also respect the new level
            # IMPORTANT: We need to iterate over ALL existing loggers, not just the ones
            # that were created before, because new loggers might be created after this call
            for existing_logger_name in list(logging.Logger.manager.loggerDict.keys()):
                if existing_logger_name.startswith(logger_name + '.'):
                    child_logger = logging.getLogger(existing_logger_name)
                    child_logger.setLevel(target_logger_level)
    
    @classmethod
    def _on_logging_config_saved(cls, sender, instance, **kwargs):
        """
        Update logger levels when LoggingConfig is saved.
        
        This signal handler ensures that when LoggingConfig is changed in the Admin GUI,
        the logger levels are immediately updated without requiring a server restart.
        
        Note: This only updates the worker that handled the admin request.
        Other workers are updated via the background thread (within 2 seconds).
        """
        cls._update_logger_levels(instance.min_log_level)
        # Note: We can't start the thread here because we don't have access to the instance
        # The thread should already be running from ready() in each worker process