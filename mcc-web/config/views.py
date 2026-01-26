# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    views.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
"""
Project: MyCyclingCity
Generation: AI-based

Custom views for the MCC application.
"""
from pathlib import Path
from django.http import HttpResponseRedirect, HttpResponse
from django.shortcuts import render
from django.utils.translation import activate, get_language
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_protect
from django.conf import settings
from django.urls import resolve, reverse
from urllib.parse import urlparse, urlunparse


@csrf_protect
@require_http_methods(["POST"])
def set_language(request) -> HttpResponseRedirect:
    """
    Custom language switcher that stores the language code in the session
    and redirects back to the previous page with the correct language prefix.

    Args:
        request: HTTP request object containing 'language' parameter

    Returns:
        HttpResponseRedirect to the previous page with language prefix or default page
    """
    language = request.POST.get('language', None)
    next_url = request.POST.get('next', None)

    # Validate language code
    if language and language in dict(settings.LANGUAGES):
        # Activate the language for the current request
        activate(language)

        # Store language in session
        request.session['django_language'] = language

        # Save session
        request.session.save()

    # Redirect to next URL with language prefix
    if next_url:
        # Parse the URL
        parsed = urlparse(next_url)
        path = parsed.path

        # Remove existing language prefix if present
        for lang_code, _ in settings.LANGUAGES:
            if path.startswith(f'/{lang_code}/'):
                path = path[len(f'/{lang_code}'):]
                break

        # Ensure path starts with /
        if not path.startswith('/'):
            path = '/' + path

        # Add new language prefix
        new_path = f'/{language}{path}'

        # Reconstruct URL with new path
        new_url = urlunparse((
            parsed.scheme,
            parsed.netloc,
            new_path,
            parsed.params,
            parsed.query,
            parsed.fragment
        ))

        return HttpResponseRedirect(new_url)
    else:
        # Fallback: redirect to root with language prefix
        return HttpResponseRedirect(f'/{language}/')


def privacy_policy(request) -> HttpResponse:
    """
    Display the privacy policy page with cookie information.

    Args:
        request: HTTP request object

    Returns:
        HttpResponse with rendered privacy policy template
    """
    return render(request, 'privacy_policy.html')


def health_check(request) -> HttpResponse:
    """
    Health check endpoint for monitoring and load balancers.
    
    Returns basic application health status including:
    - Application status
    - Database connectivity
    - Version information
    
    Args:
        request: HTTP request object
    
    Returns:
        HttpResponse with JSON health status
    """
    from django.http import JsonResponse
    from django.db import connection
    from django.conf import settings
    import time
    
    health_status = {
        'status': 'healthy',
        'timestamp': time.time(),
        'version': getattr(settings, 'PROJECT_VERSION', 'unknown'),
        'checks': {}
    }
    
    # Database check
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        health_status['checks']['database'] = 'ok'
    except Exception as e:
        health_status['checks']['database'] = f'error: {str(e)}'
        health_status['status'] = 'unhealthy'
    
    # Static files check
    try:
        static_root = settings.STATIC_ROOT
        if static_root and Path(static_root).exists():
            health_status['checks']['static_files'] = 'ok'
        else:
            health_status['checks']['static_files'] = 'warning: directory not found'
    except Exception as e:
        health_status['checks']['static_files'] = f'error: {str(e)}'
    
    # Media files check
    try:
        media_root = settings.MEDIA_ROOT
        if media_root and Path(media_root).exists():
            health_status['checks']['media_files'] = 'ok'
        else:
            health_status['checks']['media_files'] = 'warning: directory not found'
    except Exception as e:
        health_status['checks']['media_files'] = f'error: {str(e)}'
    
    status_code = 200 if health_status['status'] == 'healthy' else 503
    
    return JsonResponse(health_status, status=status_code)


def maintenance_page(request) -> HttpResponse:
    """
    Display the maintenance page.
    
    This view serves the maintenance.html page when maintenance mode is active.
    The page is served with HTTP 503 status code to indicate temporary unavailability.
    
    Args:
        request: HTTP request object
    
    Returns:
        HttpResponse with maintenance page (HTTP 503)
    """
    from django.conf import settings
    from pathlib import Path
    
    # Read the maintenance.html file from project_static
    maintenance_file = Path(settings.BASE_DIR) / 'project_static' / 'maintenance.html'
    
    if maintenance_file.exists():
        with open(maintenance_file, 'r', encoding='utf-8') as f:
            html_content = f.read()
        return HttpResponse(html_content, content_type='text/html; charset=utf-8', status=503)
    else:
        # Fallback: Simple maintenance message with login link
        login_url = '/de/admin/login/'
        login_link = f'<p><a href="{login_url}" style="color: white; text-decoration: underline;">🔐 Admin-Login</a></p>'
        return HttpResponse(
            f'<html><body style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; display: flex; align-items: center; justify-content: center; min-height: 100vh; font-family: Arial, sans-serif;"><div style="text-align: center;"><h1>Wartungsarbeiten</h1><p>Die Website wird derzeit gewartet.</p>{login_link}</div></body></html>',
            content_type='text/html; charset=utf-8',
            status=503
        )
