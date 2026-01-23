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
bind = "127.0.0.1:8001"
backlog = 2048

# Worker processes
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
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

