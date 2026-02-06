# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    middleware.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

"""
Timezone Middleware for Django Admin Interface

This middleware reads the 'django_timezone' cookie and activates the timezone
for the current request. It only processes requests to /admin/ paths.
"""

import logging
from django.utils import timezone
from django.conf import settings
from datetime import timezone as dt_timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:
    # Fallback for Python < 3.9
    from backports.zoneinfo import ZoneInfo  # noqa: F401

logger = logging.getLogger(__name__)


class TimezoneMiddleware:
    """
    Middleware to activate timezone based on cookie value.
    
    Only processes requests to /admin/ paths. Falls back to settings.TIME_ZONE
    if no cookie is present or if the timezone is invalid.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.cookie_name = 'django_timezone'
        self.default_timezone = getattr(settings, 'TIME_ZONE', 'UTC')
    
    def __call__(self, request):
        # Only process admin requests (including localized paths like /de/admin/)
        is_admin_path = request.path.startswith('/admin/') or '/admin/' in request.path
        if is_admin_path:
            # Log that middleware is being executed (for debugging)
            logger.debug(f"TimezoneMiddleware: Processing admin request {request.path}")
            timezone_name = self._get_timezone_from_request(request)
            
            if timezone_name:
                try:
                    # Validate and activate timezone
                    tz = ZoneInfo(timezone_name)
                    timezone.activate(tz)
                    current_tz = timezone.get_current_timezone()
                    logger.debug(
                        f"TimezoneMiddleware: Activated timezone '{timezone_name}' "
                        f"for request {request.path} (current timezone: {current_tz})"
                    )
                except Exception as e:
                    # Invalid timezone - log warning and use default
                    logger.warning(
                        f"Invalid timezone '{timezone_name}' from cookie. "
                        f"Falling back to {self.default_timezone}. Error: {e}"
                    )
                    try:
                        timezone.activate(ZoneInfo(self.default_timezone))
                    except Exception:
                        # Even default timezone failed - use UTC as last resort
                        timezone.activate(dt_timezone.utc)
            else:
                # No cookie - use default timezone
                current_tz = timezone.get_current_timezone()
                logger.debug(
                    f"TimezoneMiddleware: No cookie found, using default timezone "
                    f"'{self.default_timezone}' for request {request.path} "
                    f"(current timezone: {current_tz})"
                )
                try:
                    timezone.activate(ZoneInfo(self.default_timezone))
                except Exception:
                    timezone.activate(dt_timezone.utc)
        
        response = self.get_response(request)
        return response
    
    def _get_timezone_from_request(self, request):
        """
        Extract timezone name from cookie.
        
        Returns:
            str: Timezone name or None if not found/invalid
        """
        timezone_name = request.COOKIES.get(self.cookie_name)
        
        if not timezone_name:
            return None
        
        # URL-decode the timezone name (JavaScript uses encodeURIComponent)
        from urllib.parse import unquote
        timezone_name = unquote(timezone_name)
        
        # Basic validation: remove whitespace and check if not empty
        timezone_name = timezone_name.strip()
        if not timezone_name:
            return None
        
        return timezone_name
