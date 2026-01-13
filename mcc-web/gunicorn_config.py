# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    gunicorn_config.py
# @author  Roland Rutz

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
accesslog = "-"  # Log to stdout
errorlog = "-"  # Log to stderr
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = "mcc-web"

# Server mechanics
daemon = False
pidfile = None  # Set via systemd or supervisor
umask = 0
user = None  # Set via systemd
group = None  # Set via systemd
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

