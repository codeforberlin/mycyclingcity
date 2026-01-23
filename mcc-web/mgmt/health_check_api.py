# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    health_check_api.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
"""
API endpoint for external monitoring systems (Nagios, etc.).

Provides a health check endpoint that can be queried via HTTPS with API key authentication.
Returns HTTP status codes suitable for monitoring systems:
- 200 OK: All checks passed
- 503 Service Unavailable: Critical errors detected
- 200 OK with warning status: Warnings detected (monitoring system can check JSON status)

Usage:
    GET /api/health/?api_key=YOUR_API_KEY
    GET /api/health/?api_key=YOUR_API_KEY&format=json
    GET /api/health/?api_key=YOUR_API_KEY&format=nagios
"""

from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.utils import timezone
from mgmt.server_monitoring import get_health_checks
import json


def validate_api_key(api_key):
    """
    Validate the provided API key.
    
    Args:
        api_key: API key to validate
    
    Returns:
        bool: True if valid, False otherwise
    """
    # Get configured API keys from settings
    # Can be a single key or comma-separated list
    configured_keys = getattr(settings, 'HEALTH_CHECK_API_KEYS', [])
    
    # If no keys configured, allow access (for development)
    # In production, always configure keys!
    if not configured_keys:
        return True
    
    # Support both single key and list
    if isinstance(configured_keys, str):
        configured_keys = [configured_keys]
    
    # Filter out empty strings
    configured_keys = [k for k in configured_keys if k]
    
    # If still no valid keys after filtering, allow access
    if not configured_keys:
        return True
    
    # Check if provided key matches any configured key
    return api_key in configured_keys


@csrf_exempt
@require_http_methods(["GET"])
def health_check_api(request):
    """
    Health check endpoint for external monitoring systems.
    
    Query parameters:
        api_key: API key for authentication (required)
        format: Output format - 'json' (default) or 'nagios' (plain text)
        detailed: Include detailed check information (default: true)
    
    Returns:
        - 200 OK: All checks passed or warnings only
        - 503 Service Unavailable: Critical errors detected
        - 401 Unauthorized: Invalid or missing API key
    """
    # Get API key from query parameters
    api_key = request.GET.get('api_key', '')
    
    # Validate API key
    if not validate_api_key(api_key):
        return JsonResponse({
            'status': 'error',
            'message': 'Invalid or missing API key',
            'timestamp': timezone.now().isoformat(),
        }, status=401)
    
    # Get output format
    output_format = request.GET.get('format', 'json').lower()
    detailed = request.GET.get('detailed', 'true').lower() == 'true'
    
    # Get health checks
    health_checks = get_health_checks()
    
    # Determine overall status
    overall_status = health_checks.get('overall_status', 'unknown')
    
    # Count check statuses
    check_statuses = {}
    for check_name, check_data in health_checks.get('checks', {}).items():
        status = check_data.get('status', 'unknown')
        check_statuses[status] = check_statuses.get(status, 0) + 1
    
    # Determine HTTP status code
    # 503 for critical errors, 200 for OK or warnings
    http_status = 503 if overall_status == 'unhealthy' else 200
    
    # Prepare response data
    response_data = {
        'status': overall_status,
        'timestamp': health_checks.get('timestamp', timezone.now()).isoformat(),
        'checks_passed': check_statuses.get('ok', 0),
        'checks_warning': check_statuses.get('warning', 0),
        'checks_error': check_statuses.get('error', 0),
    }
    
    # Add detailed check information if requested
    if detailed:
        response_data['checks'] = health_checks.get('checks', {})
    
    # Format response based on requested format
    if output_format == 'nagios':
        # Nagios-compatible plain text format
        return format_nagios_response(response_data, health_checks, http_status)
    else:
        # JSON format (default)
        return JsonResponse(response_data, status=http_status)


def format_nagios_response(response_data, health_checks, http_status):
    """
    Format response in Nagios-compatible plain text format.
    
    Format: STATUS_CODE | metric1=value1 metric2=value2
    
    Args:
        response_data: Response data dictionary
        health_checks: Full health checks dictionary
        http_status: HTTP status code
    
    Returns:
        HttpResponse with plain text format
    """
    # Determine Nagios status code
    if response_data['status'] == 'unhealthy':
        nagios_status = 'CRITICAL'
    elif response_data['status'] == 'healthy':
        nagios_status = 'OK'
    else:
        nagios_status = 'WARNING'
    
    # Build status message
    status_msg = f"{nagios_status} - "
    status_msg += f"Passed: {response_data['checks_passed']}, "
    status_msg += f"Warnings: {response_data['checks_warning']}, "
    status_msg += f"Errors: {response_data['checks_error']}"
    
    # Build performance data (for Nagios graphing)
    perf_data = f"| passed={response_data['checks_passed']} "
    perf_data += f"warnings={response_data['checks_warning']} "
    perf_data += f"errors={response_data['checks_error']}"
    
    # Add individual check metrics if available
    checks = health_checks.get('checks', {})
    for check_name, check_data in checks.items():
        status = check_data.get('status', 'unknown')
        # Add check status as metric (0=ok, 1=warning, 2=error)
        status_value = 0 if status == 'ok' else (1 if status == 'warning' else 2)
        perf_data += f" {check_name}_status={status_value}"
    
    # Combine message and performance data
    output = f"{status_msg}{perf_data}"
    
    # Add detailed information if there are warnings or errors
    if response_data['checks_warning'] > 0 or response_data['checks_error'] > 0:
        output += "\n\nDetails:"
        for check_name, check_data in checks.items():
            status = check_data.get('status', 'unknown')
            if status != 'ok':
                message = check_data.get('message', '')
                output += f"\n{check_name}: {status.upper()} - {message}"
    
    # Return plain text response
    return HttpResponse(
        output,
        content_type='text/plain',
        status=http_status
    )
