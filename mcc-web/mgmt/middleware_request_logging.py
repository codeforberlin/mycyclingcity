# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    middleware_request_logging.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
"""
Middleware for logging HTTP requests for performance analysis.

This middleware logs all HTTP requests to the RequestLog model
for analysis of slow requests, error patterns, and performance bottlenecks.
"""

import time
from django.utils.deprecation import MiddlewareMixin
from django.db import transaction


class RequestLoggingMiddleware(MiddlewareMixin):
    """
    Middleware to log HTTP requests for performance analysis.
    
    Logs request path, method, status code, response time, user, IP, etc.
    """
    
    def process_request(self, request):
        """Store request start time."""
        request._start_time = time.time()
        return None
    
    def process_response(self, request, response):
        """Log request information after response is generated."""
        # Skip logging for certain paths (admin static files, etc.)
        skip_paths = ['/static/', '/media/', '/favicon.ico']
        if any(request.path.startswith(path) for path in skip_paths):
            return response
        
        # Calculate response time
        if hasattr(request, '_start_time'):
            response_time_ms = (time.time() - request._start_time) * 1000
        else:
            response_time_ms = 0
        
        # Log request asynchronously to avoid blocking response
        try:
            # Use on_commit to log after transaction commits
            transaction.on_commit(
                lambda: self._log_request_async(
                    request=request,
                    response=response,
                    response_time_ms=response_time_ms
                )
            )
        except Exception:
            # Silently fail if logging fails - don't break the request
            pass
        
        return response
    
    def _log_request_async(self, request, response, response_time_ms):
        """Log request information asynchronously."""
        try:
            from mgmt.models import RequestLog, LoggingConfig
            
            # Check if request logging is enabled
            config = LoggingConfig.get_config()
            if not config.enable_request_logging:
                return  # Request logging is disabled
            
            # Get user if authenticated
            user = request.user if hasattr(request, 'user') and request.user.is_authenticated else None
            
            # Get IP address
            ip_address = None
            if hasattr(request, 'META'):
                x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
                if x_forwarded_for:
                    ip_address = x_forwarded_for.split(',')[0].strip()
                else:
                    ip_address = request.META.get('REMOTE_ADDR')
            
            # Get user agent
            user_agent = request.META.get('HTTP_USER_AGENT', '')[:500]
            
            # Get query string
            query_string = request.META.get('QUERY_STRING', '')
            
            # Determine if error
            is_error = response.status_code >= 400
            
            # Create log entry
            RequestLog.objects.create(
                path=request.path[:500],
                method=request.method,
                status_code=response.status_code,
                response_time_ms=response_time_ms,
                user=user,
                ip_address=ip_address,
                user_agent=user_agent,
                query_string=query_string,
                is_error=is_error,
            )
        except Exception:
            # Silently fail - don't break the application
            pass
