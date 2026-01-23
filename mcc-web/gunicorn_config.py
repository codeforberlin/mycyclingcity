# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    gunicorn_config.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
"""
Gunicorn configuration file for MCC-Web production deployment.

Usage:
    gunicorn -c gunicorn_config.py config.wsgi:application
"""

import multiprocessing
import os

# Server socket
# Can be overridden by environment variable from database config
bind = os.environ.get("GUNICORN_BIND", "127.0.0.1:8001")
backlog = 2048

# Worker processes
# These can be overridden by environment variables from database config
workers_env = os.environ.get("GUNICORN_WORKERS", "")
if workers_env and workers_env != "0":
    workers = int(workers_env)
else:
    # If 0 or not set, use auto-calculation
    workers = multiprocessing.cpu_count() * 2 + 1
worker_class = os.environ.get("GUNICORN_WORKER_CLASS", "gthread")
# Threads only work with gthread worker class
if worker_class == "gthread":
    threads = int(os.environ.get("GUNICORN_THREADS", 2))
else:
    threads = 1  # sync worker class doesn't use threads
worker_connections = 1000
timeout = 30
keepalive = 2

# Logging
# Log to files when running as daemon, stdout/stderr when running in foreground
LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

accesslog = os.path.join(LOG_DIR, "gunicorn_access.log")
errorlog = os.path.join(LOG_DIR, "gunicorn_error.log")
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = "mcc-web"

# Server mechanics
daemon = False  # Set to True when using --daemon flag in script
pidfile = None  # Set via script or systemd
umask = 0
user = None  # Set via script or systemd
group = None  # Set via script or systemd
tmp_upload_dir = None

# SSL (if needed, uncomment and configure)
# keyfile = "/path/to/keyfile"
# certfile = "/path/to/certfile"

# Performance tuning
max_requests = 1000  # Restart worker after this many requests
max_requests_jitter = 50  # Add randomness to max_requests
preload_app = True  # Load application code before forking workers

# Graceful timeout
graceful_timeout = 30


def on_reload(server):
    """Called when Gunicorn reloads workers."""
    # This is called in the master process before forking new workers
    pass


def when_ready(server):
    """Called just after the server is started."""
    # This is called in the master process after all workers are forked
    pass


def post_fork(server, worker):
    """
    Called just after a worker has been forked.
    
    This ensures that each worker process has its own background thread
    for checking LoggingConfig changes, even with preload_app=True.
    """
    # Import here to avoid circular dependencies
    try:
        from django.apps import apps
        # Get the MgmtConfig instance and ensure the background thread is running
        mgmt_config = apps.get_app_config('mgmt')
        if hasattr(mgmt_config, '_start_level_check_thread'):
            # Reset the flag to allow thread restart in this worker
            mgmt_config._level_check_running = False
            mgmt_config._start_level_check_thread()
    except Exception:
        # Silently ignore errors (app might not be ready yet)
        pass

