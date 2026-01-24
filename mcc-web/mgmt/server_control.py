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
import logging
from mgmt.server_monitoring import get_server_metrics, get_health_checks

logger = logging.getLogger(__name__)


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
    logger.info("Server action requested: action=%s user=%s method=%s", action, request.user, request.method)
    if request.method != 'POST':
        logger.info("Server action rejected: non-POST method=%s", request.method)
        return JsonResponse({'error': 'Only POST requests allowed'}, status=405)
    
    if action not in ['start', 'stop', 'restart', 'reload', 'status']:
        logger.info("Server action rejected: invalid action=%s", action)
        return JsonResponse({'error': 'Invalid action'}, status=400)
    
    script_path = Path(settings.BASE_DIR) / 'scripts' / 'mcc-web.sh'
    logger.info("Server action script path resolved: %s", script_path)
    
    if not script_path.exists():
        logger.info("Server action failed: script not found at %s", script_path)
        return JsonResponse({
            'error': f'Script not found: {script_path}',
            'success': False
        }, status=404)
    
    # Check if script is executable
    if not os.access(script_path, os.X_OK):
        logger.info("Server action failed: script not executable at %s", script_path)
        return JsonResponse({
            'error': 'Script is not executable',
            'success': False
        }, status=403)
    
    try:
        current_user = os.getenv('USER') or os.getenv('USERNAME')
        logger.info("Server action executing as user=%s (requested action=%s)", current_user, action)
        cmd = [str(script_path), action]
        logger.info("Server action command: %s", " ".join(cmd))

        # Stop/restart will terminate the current Gunicorn worker; run detached
        if action in ['stop', 'restart']:
            logs_dir = Path(settings.BASE_DIR) / 'logs'
            logs_dir.mkdir(parents=True, exist_ok=True)
            action_log = logs_dir / 'server_action.log'
            with open(action_log, 'a') as log_handle:
                log_handle.write(f"\n--- {action} started by {request.user} ---\n")
                log_handle.flush()
                subprocess.Popen(
                    cmd,
                    stdout=log_handle,
                    stderr=log_handle,
                    start_new_session=True,
                    close_fds=True,
                )
            logger.info("Server action started in background: action=%s log=%s", action, action_log)
            return JsonResponse({
                'success': True,
                'message': f'Action "{action}" started in background',
                'output': f'Background execution. Details in {action_log}',
            }, status=202)
        
        timeout_seconds = 30
        if action == 'restart':
            # restart includes stop + start; stop can wait up to 30s
            timeout_seconds = 120
        logger.info("Server action timeout configured: action=%s timeout=%ss", action, timeout_seconds)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds
        )
        
        output = result.stdout + result.stderr
        logger.info("Server action completed: action=%s returncode=%s", action, result.returncode)
        
        if result.returncode == 0:
            # Get updated status
            status_info = get_server_status(script_path)
            logger.info("Server action success: action=%s status_running=%s pid=%s", action, status_info.get('running'), status_info.get('pid'))
            
            return JsonResponse({
                'success': True,
                'message': f'Action "{action}" completed successfully',
                'output': output,
                'status': status_info
            })
        else:
            logger.info("Server action failed: action=%s returncode=%s output=%s", action, result.returncode, output.strip())
            return JsonResponse({
                'success': False,
                'error': f'Action "{action}" failed',
                'output': output,
                'returncode': result.returncode
            }, status=500)
            
    except subprocess.TimeoutExpired:
        logger.info("Server action timeout: action=%s", action)
        return JsonResponse({
            'success': False,
            'error': 'Action timed out'
        }, status=504)
    except Exception as e:
        logger.info("Server action error: action=%s error=%s", action, str(e))
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


def get_server_status(script_path):
    """Get current server status."""
    logger.info("Server status requested with script path: %s", script_path)
    if not script_path.exists():
        logger.info("Server status failed: script not found at %s", script_path)
        return {
            'running': False,
            'error': 'Script not found'
        }
    
    try:
        current_user = os.getenv('USER') or os.getenv('USERNAME')
        logger.info("Server status executing as user=%s", current_user)
        cmd = [str(script_path), 'status']
        logger.info("Server status command: %s", " ".join(cmd))
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        running = result.returncode == 0
        output = result.stdout + result.stderr
        logger.info("Server status completed: running=%s returncode=%s", running, result.returncode)
        
        # Try to extract PID
        pid = None
        pidfile = Path(settings.BASE_DIR) / 'tmp' / 'mcc-web.pid'
        if pidfile.exists():
            try:
                with open(pidfile, 'r') as f:
                    pid = f.read().strip()
            except Exception:
                pass
        logger.info("Server status pid resolved: %s", pid or "N/A")
        
        return {
            'running': running,
            'pid': pid,
            'output': output,
        }
    except Exception as e:
        logger.info("Server status error: %s", str(e))
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
