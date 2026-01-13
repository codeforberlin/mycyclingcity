# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    context_processors.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
"""
Project: MyCyclingCity
Generation: AI-based

Custom context processors for the MCC application.
"""
from django.conf import settings


def languages(request):
    """
    Add LANGUAGES to template context.

    Args:
        request: HTTP request object.

    Returns:
        dict: Dictionary containing LANGUAGES from settings.
    """
    return {
        'LANGUAGES': settings.LANGUAGES,
    }


def kiosk_update_intervals(request):
    """
    Add Kiosk update intervals to template context.

    Args:
        request: HTTP request object.

    Returns:
        dict: Dictionary containing update intervals from settings.
    """
    return {
        'KIOSK_TICKER_UPDATE_INTERVAL': getattr(settings, 'MCC_KIOSK_TICKER_UPDATE_INTERVAL', 5),
        'KIOSK_BANNER_UPDATE_INTERVAL': getattr(settings, 'MCC_KIOSK_BANNER_UPDATE_INTERVAL', 20),
        'KIOSK_CONTENT_UPDATE_INTERVAL': getattr(settings, 'MCC_KIOSK_CONTENT_UPDATE_INTERVAL', 20),
        'KIOSK_FOOTER_UPDATE_INTERVAL': getattr(settings, 'MCC_KIOSK_FOOTER_UPDATE_INTERVAL', 20),
    }


def project_version(request):
    """
    Add PROJECT_VERSION to template context.

    Args:
        request: HTTP request object.

    Returns:
        dict: Dictionary containing PROJECT_VERSION from settings.
    """
    return {
        'PROJECT_VERSION': getattr(settings, 'PROJECT_VERSION', 'dev'),
    }
