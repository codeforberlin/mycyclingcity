# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    maintenance_control.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
"""
Admin views for maintenance mode control.

Allows superusers to activate/deactivate maintenance mode from the Admin GUI.
"""

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import render
from django.http import JsonResponse
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from pathlib import Path
import os
import logging

logger = logging.getLogger(__name__)


def is_superuser(user):
    """Check if user is superuser."""
    return user.is_superuser


def get_maintenance_flag_path():
    """
    Get path to maintenance flag file.
    
    Returns:
        Path object to maintenance flag file
    """
    # Production: /data/var/mcc/apache/.maintenance_mode
    # Development: data/apache/.maintenance_mode
    if '/data/appl/mcc' in str(settings.BASE_DIR) or os.environ.get('MCC_ENV') == 'production':
        apache_dir = Path('/data/var/mcc/apache')
    else:
        apache_dir = settings.DATA_DIR / 'apache'
    
    # Ensure directory exists
    apache_dir.mkdir(parents=True, exist_ok=True)
    return apache_dir / '.maintenance_mode'


@user_passes_test(is_superuser)
@staff_member_required
def maintenance_control(request):
    """Main maintenance control page."""
    flag_path = get_maintenance_flag_path()
    is_active = flag_path.exists()
    
    context = {
        'title': _('Maintenance Mode Control'),
        'is_active': is_active,
        'flag_path': flag_path,
    }
    
    return render(request, 'admin/mgmt/maintenance_control.html', context)


@user_passes_test(is_superuser)
@staff_member_required
def maintenance_action(request, action):
    """
    Activate or deactivate maintenance mode.
    
    Actions:
        - 'activate': Create maintenance flag file
        - 'deactivate': Remove maintenance flag file
    """
    logger.info("Maintenance action requested: action=%s user=%s method=%s", action, request.user, request.method)
    
    if request.method != 'POST':
        logger.info("Maintenance action rejected: non-POST method=%s", request.method)
        return JsonResponse({'error': 'Only POST requests allowed'}, status=405)
    
    if action not in ['activate', 'deactivate']:
        logger.info("Maintenance action rejected: invalid action=%s", action)
        return JsonResponse({'error': 'Invalid action'}, status=400)
    
    flag_path = get_maintenance_flag_path()
    
    try:
        if action == 'activate':
            # Create flag file
            flag_path.touch()
            # Ensure Apache can read it (group readable)
            flag_path.chmod(0o644)
            logger.info("Maintenance mode activated by user=%s flag_path=%s", request.user, flag_path)
            return JsonResponse({
                'success': True,
                'message': _('Maintenance mode activated'),
                'is_active': True
            })
        else:  # deactivate
            # Remove flag file if it exists
            if flag_path.exists():
                flag_path.unlink()
            logger.info("Maintenance mode deactivated by user=%s flag_path=%s", request.user, flag_path)
            return JsonResponse({
                'success': True,
                'message': _('Maintenance mode deactivated'),
                'is_active': False
            })
    except PermissionError as e:
        logger.error("Maintenance action permission error: action=%s error=%s", action, str(e))
        return JsonResponse({
            'success': False,
            'error': _('Permission denied. Please check file permissions.')
        }, status=403)
    except Exception as e:
        logger.error("Maintenance action failed: action=%s error=%s", action, str(e))
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
