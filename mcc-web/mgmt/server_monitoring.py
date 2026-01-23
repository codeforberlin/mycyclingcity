# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    server_monitoring.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
"""
Server monitoring and metrics collection for Gunicorn server.

Provides functionality to collect server metrics, worker information,
and performance data for display in the Admin GUI.
"""

import psutil
import os
import subprocess
from pathlib import Path
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
import time


def get_gunicorn_master_pid():
    """Get the PID of the Gunicorn master process."""
    pidfile = Path(settings.BASE_DIR) / 'mcc-web.pid'
    if pidfile.exists():
        try:
            with open(pidfile, 'r') as f:
                pid = int(f.read().strip())
                # Verify it's actually a gunicorn process
                try:
                    proc = psutil.Process(pid)
                    if 'gunicorn' in proc.name().lower() or 'gunicorn' in ' '.join(proc.cmdline()).lower():
                        return pid
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except (ValueError, IOError):
            pass
    return None


def get_server_metrics():
    """
    Collect comprehensive server metrics.
    
    Returns:
        dict: Dictionary containing server metrics
    """
    metrics = {
        'timestamp': timezone.now(),
        'server_running': False,
        'master_pid': None,
        'workers': [],
        'system': {},
        'errors': []
    }
    
    try:
        master_pid = get_gunicorn_master_pid()
        if master_pid:
            metrics['master_pid'] = master_pid
            metrics['server_running'] = True
            
            try:
                master_proc = psutil.Process(master_pid)
                
                # Master process info
                metrics['master'] = {
                    'pid': master_pid,
                    'cpu_percent': master_proc.cpu_percent(interval=0.1),
                    'memory_mb': master_proc.memory_info().rss / 1024 / 1024,
                    'memory_percent': master_proc.memory_percent(),
                    'create_time': master_proc.create_time(),
                    'uptime_seconds': time.time() - master_proc.create_time(),
                    'status': master_proc.status(),
                }
                
                # Get worker processes (children of master)
                workers = []
                for child in master_proc.children(recursive=False):
                    try:
                        worker_info = {
                            'pid': child.pid,
                            'cpu_percent': child.cpu_percent(interval=0.1),
                            'memory_mb': child.memory_info().rss / 1024 / 1024,
                            'memory_percent': child.memory_percent(),
                            'status': child.status(),
                            'num_threads': child.num_threads(),
                            'create_time': child.create_time(),
                            'uptime_seconds': time.time() - child.create_time(),
                        }
                        workers.append(worker_info)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                
                metrics['workers'] = workers
                metrics['worker_count'] = len(workers)
                
            except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                metrics['errors'].append(f"Error accessing process: {str(e)}")
        
        # System metrics
        try:
            metrics['system'] = {
                'cpu_percent': psutil.cpu_percent(interval=0.1),
                'cpu_count': psutil.cpu_count(),
                'memory_total_mb': psutil.virtual_memory().total / 1024 / 1024,
                'memory_available_mb': psutil.virtual_memory().available / 1024 / 1024,
                'memory_used_mb': psutil.virtual_memory().used / 1024 / 1024,
                'memory_percent': psutil.virtual_memory().percent,
                'disk_usage': {
                    'total_gb': psutil.disk_usage('/').total / 1024 / 1024 / 1024,
                    'used_gb': psutil.disk_usage('/').used / 1024 / 1024 / 1024,
                    'free_gb': psutil.disk_usage('/').free / 1024 / 1024 / 1024,
                    'percent': psutil.disk_usage('/').percent,
                },
                'load_avg': os.getloadavg() if hasattr(os, 'getloadavg') else None,
            }
        except Exception as e:
            metrics['errors'].append(f"Error collecting system metrics: {str(e)}")
        
    except Exception as e:
        metrics['errors'].append(f"Error collecting metrics: {str(e)}")
    
    return metrics


def get_health_checks():
    """
    Perform comprehensive health checks.
    
    Returns:
        dict: Dictionary containing health check results
    """
    from django.db import connection
    from django.core.cache import cache
    
    checks = {
        'timestamp': timezone.now(),
        'overall_status': 'healthy',
        'checks': {}
    }
    
    # Database check
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        checks['checks']['database'] = {
            'status': 'ok',
            'message': 'Database connection successful'
        }
    except Exception as e:
        checks['checks']['database'] = {
            'status': 'error',
            'message': f'Database error: {str(e)}'
        }
        checks['overall_status'] = 'unhealthy'
    
    # Cache check
    try:
        cache.set('health_check', 'ok', 10)
        if cache.get('health_check') == 'ok':
            checks['checks']['cache'] = {
                'status': 'ok',
                'message': 'Cache is working'
            }
        else:
            checks['checks']['cache'] = {
                'status': 'warning',
                'message': 'Cache test failed'
            }
    except Exception as e:
        checks['checks']['cache'] = {
            'status': 'warning',
            'message': f'Cache error: {str(e)}'
        }
    
    # Disk space check
    try:
        disk = psutil.disk_usage('/')
        disk_percent = disk.percent
        if disk_percent > 90:
            checks['checks']['disk'] = {
                'status': 'error',
                'message': f'Disk usage critical: {disk_percent:.1f}%'
            }
            checks['overall_status'] = 'unhealthy'
        elif disk_percent > 80:
            checks['checks']['disk'] = {
                'status': 'warning',
                'message': f'Disk usage high: {disk_percent:.1f}%'
            }
        else:
            checks['checks']['disk'] = {
                'status': 'ok',
                'message': f'Disk usage: {disk_percent:.1f}%'
            }
    except Exception as e:
        checks['checks']['disk'] = {
            'status': 'warning',
            'message': f'Could not check disk: {str(e)}'
        }
    
    # Memory check
    try:
        memory = psutil.virtual_memory()
        if memory.percent > 90:
            checks['checks']['memory'] = {
                'status': 'error',
                'message': f'Memory usage critical: {memory.percent:.1f}%'
            }
            checks['overall_status'] = 'unhealthy'
        elif memory.percent > 80:
            checks['checks']['memory'] = {
                'status': 'warning',
                'message': f'Memory usage high: {memory.percent:.1f}%'
            }
        else:
            checks['checks']['memory'] = {
                'status': 'ok',
                'message': f'Memory usage: {memory.percent:.1f}%'
            }
    except Exception as e:
        checks['checks']['memory'] = {
            'status': 'warning',
            'message': f'Could not check memory: {str(e)}'
        }
    
    # Static files check
    try:
        static_root = Path(settings.STATIC_ROOT)
        if static_root.exists():
            checks['checks']['static_files'] = {
                'status': 'ok',
                'message': f'Static files directory exists: {static_root}'
            }
        else:
            checks['checks']['static_files'] = {
                'status': 'warning',
                'message': f'Static files directory not found: {static_root}'
            }
    except Exception as e:
        checks['checks']['static_files'] = {
            'status': 'warning',
            'message': f'Could not check static files: {str(e)}'
        }
    
    # Media files check
    try:
        media_root = Path(settings.MEDIA_ROOT)
        if media_root.exists():
            checks['checks']['media_files'] = {
                'status': 'ok',
                'message': f'Media files directory exists: {media_root}'
            }
        else:
            checks['checks']['media_files'] = {
                'status': 'warning',
                'message': f'Media files directory not found: {media_root}'
            }
    except Exception as e:
        checks['checks']['media_files'] = {
            'status': 'warning',
            'message': f'Could not check media files: {str(e)}'
        }
    
    return checks
