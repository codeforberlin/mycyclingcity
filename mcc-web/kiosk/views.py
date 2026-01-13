# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    views.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
"""
Project: MyCyclingCity
Generation: AI-based

Views for kiosk app - handles kiosk device playlist display.
"""

from django.http import HttpRequest, HttpResponse, Http404
from django.shortcuts import render
from django.urls import reverse
from .models import KioskDevice


def kiosk_playlist_page(request: HttpRequest, uid: str) -> HttpResponse:
    """
    Main Kiosk page that loads playlist and displays views in rotation.
    The JavaScript controller handles the playlist rotation locally.
    Shows maintenance page if device is inactive or no active playlist entries.
    
    Args:
        request: HTTP request object
        uid: Unique identifier for the kiosk device
        
    Returns:
        HTTP response with kiosk playlist page or error page
    """
    try:
        device = KioskDevice.objects.select_related().get(uid=uid)
    except KioskDevice.DoesNotExist:
        # Device not found - show 404
        raise Http404(f"Kiosk device with UID '{uid}' not found.")
    
    # Check if device is active
    if not device.is_active:
        # Device exists but is inactive - show maintenance page
        context = {
            'device_uid': uid,
            'device_name': device.name,
        }
        return render(request, 'kiosk/kiosk_maintenance.html', context, status=503)
    
    # Check if there are any active playlist entries
    if not device.playlist_entries.filter(is_active=True).exists():
        # Device is active but has no active playlist entries - show configuration page
        context = {
            'device_uid': uid,
            'device_name': device.name,
            'admin_url': reverse('admin:kiosk_kioskdevice_change', args=[device.id]),
        }
        return render(request, 'kiosk/kiosk_no_playlist.html', context, status=200)
    
    context = {
        'device': device,
        'device_uid': uid,
    }
    
    return render(request, 'kiosk/kiosk_playlist.html', context)
