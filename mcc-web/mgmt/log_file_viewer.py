# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    log_file_viewer.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
"""
Admin views for viewing log files directly in the Admin GUI.

Provides functionality to browse, search, and filter log files with
scrollable interface and real-time updates.
"""

from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponse
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from pathlib import Path
import re
import os
from datetime import datetime


# Available log files
LOG_FILES = {
    'api': {
        'name': 'api.log',
        'display_name': _('API Application Logs'),
        'description': _('Alle Logs der API-Anwendung'),
    },
    'mgmt': {
        'name': 'mgmt.log',
        'display_name': _('Management Application Logs'),
        'description': _('Alle Logs der Management-Anwendung'),
    },
    'iot': {
        'name': 'iot.log',
        'display_name': _('IoT Application Logs'),
        'description': _('Alle Logs der IoT-Anwendung'),
    },
    'kiosk': {
        'name': 'kiosk.log',
        'display_name': _('Kiosk Application Logs'),
        'description': _('Alle Logs der Kiosk-Anwendung'),
    },
    'game': {
        'name': 'game.log',
        'display_name': _('Game Application Logs'),
        'description': _('Alle Logs der Game-Anwendung'),
    },
    'map': {
        'name': 'map.log',
        'display_name': _('Map Application Logs'),
        'description': _('Alle Logs der Map-Anwendung'),
    },
    'leaderboard': {
        'name': 'leaderboard.log',
        'display_name': _('Leaderboard Application Logs'),
        'description': _('Alle Logs der Leaderboard-Anwendung'),
    },
    'django': {
        'name': 'django.log',
        'display_name': _('Django Framework Logs'),
        'description': _('Nur WARNING, ERROR und CRITICAL Logs vom Django-Framework'),
    },
}


def get_log_file_path(file_key):
    """Get the full path to a log file."""
    logs_dir = Path(settings.BASE_DIR) / 'logs'
    if file_key in LOG_FILES:
        return logs_dir / LOG_FILES[file_key]['name']
    return None


def parse_log_line(line):
    """Parse a log line and extract level, timestamp, module, message."""
    # Try to match verbose format: LEVEL YYYY-MM-DD HH:MM:SS,mmm MODULE PID TID MESSAGE
    verbose_pattern = r'^(\w+)\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2},\d{3})\s+(\S+)\s+\d+\s+\d+\s+(.+)$'
    match = re.match(verbose_pattern, line)
    
    if match:
        level, timestamp, module, message = match.groups()
        return {
            'level': level,
            'timestamp': timestamp,
            'module': module,
            'message': message,
            'raw': line
        }
    
    # Try to match simple format: [LEVEL] YYYY-MM-DD HH:MM:SS LOGGER: MESSAGE
    simple_pattern = r'^\[(\w+)\]\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+(\S+):\s+(.+)$'
    match = re.match(simple_pattern, line)
    
    if match:
        level, timestamp, logger, message = match.groups()
        return {
            'level': level,
            'timestamp': timestamp,
            'module': logger,
            'message': message,
            'raw': line
        }
    
    # Fallback: return raw line
    return {
        'level': 'UNKNOWN',
        'timestamp': '',
        'module': '',
        'message': line,
        'raw': line
    }


@staff_member_required
def log_file_list(request):
    """List available log files."""
    logs_dir = Path(settings.BASE_DIR) / 'logs'
    logs_dir.mkdir(exist_ok=True)
    
    log_files_info = []
    for key, info in LOG_FILES.items():
        file_path = get_log_file_path(key)
        exists = file_path.exists() if file_path else False
        size = file_path.stat().st_size if exists and file_path else 0
        
        # Check for rotated files
        rotated_files = []
        if exists:
            base_name = file_path.stem
            for i in range(1, 20):  # Check up to 20 rotated files
                rotated = logs_dir / f"{base_name}.{i}"
                if rotated.exists():
                    rotated_files.append({
                        'name': rotated.name,
                        'size': rotated.stat().st_size,
                        'modified': datetime.fromtimestamp(rotated.stat().st_mtime)
                    })
        
        log_files_info.append({
            'key': key,
            'name': info['name'],
            'display_name': info['display_name'],
            'description': info['description'],
            'exists': exists,
            'size': size,
            'size_mb': round(size / (1024 * 1024), 2),
            'rotated_files': rotated_files,
            'url': f'/admin/mgmt/logs/view/{key}/' if exists else None,
        })
    
    context = {
        'title': _('Log File Viewer'),
        'log_files': log_files_info,
    }
    
    return render(request, 'admin/mgmt/log_file_list.html', context)


@staff_member_required
def log_file_viewer(request, file_key, rotated_index=None):
    """View a log file with scrolling, filtering, and search."""
    if file_key not in LOG_FILES:
        return redirect('admin:mgmt_log_file_list')
    
    file_path = get_log_file_path(file_key)
    if rotated_index is not None:
        # View rotated file
        base_name = file_path.stem
        logs_dir = file_path.parent
        file_path = logs_dir / f"{base_name}.{rotated_index}"
    
    if not file_path or not file_path.exists():
        return redirect('admin:mgmt_log_file_list')
    
    # Get parameters
    lines_per_page = int(request.GET.get('lines', 100))
    page = int(request.GET.get('page', 1))
    search = request.GET.get('search', '').strip()
    level_filter = request.GET.get('level', '').strip()
    tail = request.GET.get('tail', '').strip().lower() == 'true'
    auto_refresh = request.GET.get('auto_refresh', '').strip().lower() == 'true'
    
    # Read file
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            all_lines = f.readlines()
    except Exception as e:
        return render(request, 'admin/mgmt/log_file_viewer.html', {
            'title': _('Error Reading Log File'),
            'error': str(e),
        })
    
    # Parse and filter lines
    parsed_lines = []
    for line_num, line in enumerate(all_lines, 1):
        parsed = parse_log_line(line.rstrip('\n\r'))
        parsed['line_number'] = line_num
        
        # Apply filters
        if search and search.lower() not in parsed['raw'].lower():
            continue
        if level_filter and parsed['level'] != level_filter:
            continue
        
        parsed_lines.append(parsed)
    
    total_lines = len(parsed_lines)
    
    # Handle tail mode (show last N lines)
    if tail:
        parsed_lines = parsed_lines[-lines_per_page:]
        page = 1
    else:
        # Pagination
        start = (page - 1) * lines_per_page
        end = start + lines_per_page
        parsed_lines = parsed_lines[start:end]
    
    # Get file info
    file_stat = file_path.stat()
    file_size_mb = round(file_stat.st_size / (1024 * 1024), 2)
    file_modified = datetime.fromtimestamp(file_stat.st_mtime)
    
    # Check for rotated files
    rotated_files = []
    base_name = file_path.stem
    logs_dir = file_path.parent
    for i in range(1, 20):
        rotated = logs_dir / f"{base_name}.{i}"
        if rotated.exists():
            rotated_files.append({
                'index': i,
                'name': rotated.name,
                'size_mb': round(rotated.stat().st_size / (1024 * 1024), 2),
            })
    
    context = {
        'title': _('Log File Viewer') + f' - {LOG_FILES[file_key]["display_name"]}',
        'file_key': file_key,
        'file_name': file_path.name,
        'file_size_mb': file_size_mb,
        'file_modified': file_modified,
        'total_lines': total_lines,
        'parsed_lines': parsed_lines,
        'lines_per_page': lines_per_page,
        'page': page,
        'total_pages': (total_lines + lines_per_page - 1) // lines_per_page if total_lines > 0 else 1,
        'search': search,
        'level_filter': level_filter,
        'tail': tail,
        'auto_refresh': auto_refresh,
        'rotated_files': rotated_files,
        'rotated_index': rotated_index,
    }
    
    return render(request, 'admin/mgmt/log_file_viewer.html', context)


@staff_member_required
def log_file_api(request, file_key):
    """API endpoint for AJAX requests to get new log lines."""
    file_path = get_log_file_path(file_key)
    if not file_path or not file_path.exists():
        return JsonResponse({'error': 'File not found'}, status=404)
    
    # Get last N lines
    lines_count = int(request.GET.get('lines', 50))
    
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            all_lines = f.readlines()
        
        # Get last N lines
        last_lines = all_lines[-lines_count:]
        parsed_lines = [parse_log_line(line.rstrip('\n\r')) for line in last_lines]
        
        return JsonResponse({
            'lines': parsed_lines,
            'total_lines': len(all_lines),
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
