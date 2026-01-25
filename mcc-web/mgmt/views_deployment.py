# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    views_deployment.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
"""
Views for deployment and backup management.
"""

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import user_passes_test
from django.http import JsonResponse
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from pathlib import Path
import subprocess
import os
import json
from datetime import datetime
import logging
logger = logging.getLogger(__name__)



def is_superuser(user):
    """Check if user is superuser."""
    return user.is_superuser


@user_passes_test(is_superuser)
@staff_member_required
def backup_control(request):
    """Backup management page."""
    # Prüfe ob wir in Produktion sind
    if '/data/appl/mcc' in str(settings.BASE_DIR) or os.environ.get('MCC_ENV') == 'production':
        backups_dir = Path('/data/var/mcc/backups')
    else:
        # Entwicklung: lokales Verzeichnis
        backups_dir = Path(settings.BASE_DIR) / 'backups'
    backups_dir.mkdir(parents=True, exist_ok=True)
    
    # List backup files (exclude WAL and SHM files)
    backups = []
    # Find all backup files (both .sqlite3 and .db extensions)
    backup_patterns = ['*.sqlite3', '*.db', '*.sqlite3.gz', '*.db.gz']
    backup_files = []
    for pattern in backup_patterns:
        backup_files.extend(backups_dir.glob(pattern))
    
    # Filter out WAL and SHM files
    backup_files = [f for f in backup_files if not f.name.endswith('-wal') and not f.name.endswith('-shm')]
    
    # Sort by modification time (newest first)
    for backup_file in sorted(backup_files, key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            stat = backup_file.stat()
            backups.append({
                'filename': backup_file.name,
                'size_mb': stat.st_size / 1024 / 1024,
                'created': datetime.fromtimestamp(stat.st_mtime),
                'path': str(backup_file),
            })
        except (OSError, ValueError) as e:
            # Skip files that can't be accessed
            continue
    
    context = {
        'title': _('Backup Management'),
        'backups': backups,
        'backups_dir': backups_dir,
    }
    return render(request, 'admin/mgmt/backup_control.html', context)


@user_passes_test(is_superuser)
@staff_member_required
def create_backup(request):
    """Create a database backup."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST requests allowed'}, status=405)
    
    try:
        from utils.backup_database import create_backup as backup_func, get_database_path
        
        # Get database path
        project_dir = Path(settings.BASE_DIR)
        db_path = get_database_path(project_dir)
        if not db_path:
            return JsonResponse({
                'success': False,
                'error': _('Could not determine database path')
            }, status=500)
        
        # Get backup directory
        # Prüfe ob wir in Produktion sind
        if '/data/appl/mcc' in str(project_dir) or os.environ.get('MCC_ENV') == 'production':
            backup_dir = Path('/data/var/mcc/backups')
        else:
            # Entwicklung: lokales Verzeichnis
            backup_dir = project_dir / 'backups'
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        # Create backup
        backup_path = backup_func(db_path, backup_dir, compress=False)
        
        if not backup_path:
            return JsonResponse({
                'success': False,
                'error': _('Failed to create backup')
            }, status=500)
        
        return JsonResponse({
            'success': True,
            'message': _('Backup created successfully'),
            'backup_path': str(backup_path),
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@user_passes_test(is_superuser)
@staff_member_required
def download_backup(request, filename):
    """Download a backup file."""
    from django.http import FileResponse, Http404
    from urllib.parse import quote
    
    backups_dir = Path(settings.BASE_DIR) / 'backups'
    backup_path = backups_dir / filename
    
    # Security: Only allow files from backups directory
    try:
        backup_path_resolved = backup_path.resolve()
        backups_dir_resolved = backups_dir.resolve()
        if not str(backup_path_resolved).startswith(str(backups_dir_resolved)):
            raise Http404("Invalid backup path")
    except (ValueError, OSError) as e:
        raise Http404(f"Invalid backup path: {e}")
    
    if not backup_path.exists() or not backup_path.is_file():
        raise Http404("Backup file not found")
    
    # Check if file is a backup file (security)
    if not (backup_path.suffix in ['.sqlite3', '.db'] or backup_path.name.endswith('.sqlite3.gz') or backup_path.name.endswith('.db.gz')):
        raise Http404("Invalid file type")
    
    # Filter out WAL and SHM files
    if backup_path.name.endswith('-wal') or backup_path.name.endswith('-shm'):
        raise Http404("Invalid backup file")
    
    try:
        file_handle = open(backup_path, 'rb')
        response = FileResponse(
            file_handle,
            content_type='application/octet-stream',
            as_attachment=True,
            filename=backup_path.name
        )
        # Set filename for download (URL-encoded)
        encoded_filename = quote(backup_path.name)
        response['Content-Disposition'] = f'attachment; filename="{encoded_filename}"; filename*=UTF-8\'\'{encoded_filename}'
        return response
    except (IOError, OSError) as e:
        raise Http404(f"Backup file could not be opened: {e}")


