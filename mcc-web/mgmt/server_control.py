# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    server_control.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
"""
Admin views for server control (start, stop, restart).

Allows superusers to control the Gunicorn server from the Admin GUI.
"""

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from pathlib import Path
import subprocess
import os
import json
from mgmt.server_monitoring import get_server_metrics, get_health_checks


def is_superuser(user):
    """Check if user is superuser."""
    return user.is_superuser


@user_passes_test(is_superuser)
@staff_member_required
def server_control(request):
    """Main server control page."""
    script_path = Path(settings.BASE_DIR) / 'scripts' / 'mcc-web.sh'
    
    # Get server status
    status_info = get_server_status(script_path)
    
    # Get Gunicorn configuration
    try:
        from mgmt.models import GunicornConfig
        gunicorn_config = GunicornConfig.get_config()
        gunicorn_log_level = gunicorn_config.get_log_level_display()
    except Exception:
        gunicorn_log_level = _('Not available')
        gunicorn_config = None
    
    # Get server metrics
    metrics = get_server_metrics()
    
    # Get health checks
    health_checks = get_health_checks()
    
    context = {
        'title': _('Server Control'),
        'status': status_info,
        'script_path': script_path,
        'gunicorn_log_level': gunicorn_log_level,
        'gunicorn_config': gunicorn_config,
        'metrics': metrics,
        'health_checks': health_checks,
    }
    
    return render(request, 'admin/mgmt/server_control.html', context)


@user_passes_test(is_superuser)
@staff_member_required
def server_action(request, action):
    """Perform server action (start, stop, restart, reload, status)."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST requests allowed'}, status=405)
    
    if action not in ['start', 'stop', 'restart', 'reload', 'status']:
        return JsonResponse({'error': 'Invalid action'}, status=400)
    
    script_path = Path(settings.BASE_DIR) / 'scripts' / 'mcc-web.sh'
    
    if not script_path.exists():
        return JsonResponse({
            'error': f'Script not found: {script_path}',
            'success': False
        }, status=404)
    
    # Check if script is executable
    if not os.access(script_path, os.X_OK):
        return JsonResponse({
            'error': 'Script is not executable',
            'success': False
        }, status=403)
    
    try:
        # Try to run as mcc user with sudo, fallback to direct execution
        # Check if we're already running as mcc user
        current_user = os.getenv('USER') or os.getenv('USERNAME')
        
        if current_user == 'mcc':
            # Already running as mcc, execute directly
            cmd = [str(script_path), action]
        else:
            # Try to run with sudo as mcc user
            cmd = ['sudo', '-u', 'mcc', str(script_path), action]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        output = result.stdout + result.stderr
        
        if result.returncode == 0:
            # Get updated status
            status_info = get_server_status(script_path)
            
            return JsonResponse({
                'success': True,
                'message': f'Action "{action}" completed successfully',
                'output': output,
                'status': status_info
            })
        else:
            return JsonResponse({
                'success': False,
                'error': f'Action "{action}" failed',
                'output': output,
                'returncode': result.returncode
            }, status=500)
            
    except subprocess.TimeoutExpired:
        return JsonResponse({
            'success': False,
            'error': 'Action timed out'
        }, status=504)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


def get_server_status(script_path):
    """Get current server status."""
    if not script_path.exists():
        return {
            'running': False,
            'error': 'Script not found'
        }
    
    try:
        # Try to run as mcc user with sudo, fallback to direct execution
        current_user = os.getenv('USER') or os.getenv('USERNAME')
        
        if current_user == 'mcc':
            cmd = [str(script_path), 'status']
        else:
            cmd = ['sudo', '-u', 'mcc', str(script_path), 'status']
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        running = result.returncode == 0
        output = result.stdout + result.stderr
        
        # Try to extract PID
        pid = None
        pidfile = Path(settings.BASE_DIR) / 'mcc-web.pid'
        if pidfile.exists():
            try:
                with open(pidfile, 'r') as f:
                    pid = f.read().strip()
            except Exception:
                pass
        
        return {
            'running': running,
            'pid': pid,
            'output': output,
        }
    except Exception as e:
        return {
            'running': False,
            'error': str(e)
        }


@user_passes_test(is_superuser)
@staff_member_required
def server_metrics_api(request):
    """API endpoint for AJAX requests to get server metrics."""
    metrics = get_server_metrics()
    return JsonResponse(metrics, json_dumps_params={'default': str})


@user_passes_test(is_superuser)
@staff_member_required
def server_health_api(request):
    """API endpoint for AJAX requests to get health checks."""
    health_checks = get_health_checks()
    return JsonResponse(health_checks, json_dumps_params={'default': str})
