# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    middleware_logging_config.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
"""
Middleware to ensure LoggingConfig background thread is running in each worker.

This middleware ensures that the background thread for checking LoggingConfig
is started in each worker process, even if post_fork hook didn't work.
"""

from django.utils.deprecation import MiddlewareMixin


class LoggingConfigMiddleware(MiddlewareMixin):
    """
    Middleware to ensure LoggingConfig background thread is running.
    
    This is a safety net to ensure the background thread runs in each worker,
    even if the post_fork hook didn't work properly.
    """
    
    _thread_started = False
    
    def process_request(self, request):
        """Ensure background thread is running (only once per worker)."""
        # Use class variable to ensure thread is only started once per worker process
        if not LoggingConfigMiddleware._thread_started:
            try:
                from django.apps import apps
                mgmt_config = apps.get_app_config('mgmt')
                if hasattr(mgmt_config, '_start_level_check_thread'):
                    # Only start if not already running
                    if not mgmt_config._level_check_running:
                        mgmt_config._start_level_check_thread()
                    LoggingConfigMiddleware._thread_started = True
            except Exception:
                # Silently ignore errors (app might not be ready yet)
                pass
        
        return None
