# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    wsgi.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

application = get_wsgi_application()

# Import key modules at startup to trigger logger initialization
# This ensures that logger initialization logs are written at startup,
# not just when the first request arrives
try:
    # Import api.views to trigger logger initialization
    import api.views  # noqa: F401
except Exception:
    # Silently fail if import fails (e.g., during migrations)
    pass
