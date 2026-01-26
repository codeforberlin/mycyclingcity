# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    middleware_maintenance.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
"""
Middleware to handle maintenance mode with IP whitelist.

Checks if maintenance mode is active and if the client IP
is in the whitelist. If not, redirects to maintenance page.
"""

from django.shortcuts import redirect
from django.http import HttpResponse
from ipaddress import ip_address, ip_network
import logging

logger = logging.getLogger(__name__)


class MaintenanceModeMiddleware:
    """
    Middleware to handle maintenance mode with IP whitelist.
    
    Checks if maintenance mode is active and if the client IP
    is in the whitelist. If not, redirects to maintenance page.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        from mgmt.models import MaintenanceConfig
        from mgmt.maintenance_control import get_maintenance_flag_path
        from django.db import OperationalError
        
        flag_path = get_maintenance_flag_path()
        
        # Prüfe ob Maintenance aktiv ist
        if flag_path.exists():
            try:
                # Prüfe ob Tabelle existiert (Migration möglicherweise noch nicht ausgeführt)
                try:
                    config = MaintenanceConfig.get_config()
                except OperationalError as e:
                    # Tabelle existiert noch nicht - Fallback: Nur Superuser erlauben
                    if 'no such table' in str(e).lower() or 'does not exist' in str(e).lower():
                        logger.warning(f"[MaintenanceMode] MaintenanceConfig table does not exist yet (migration not run). Allowing superuser access only.")
                        # Prüfe ob es statische Dateien oder Maintenance-Seite ist
                        if request.path.startswith('/static/') or request.path == '/maintenance.html' or request.path.startswith('/media/'):
                            return self.get_response(request)
                        # Admin-Login und Logout immer erlauben
                        if '/admin/login/' in request.path or '/admin/logout/' in request.path:
                            return self.get_response(request)
                        # Nur Superuser erlauben (Fallback)
                        if request.user.is_authenticated and request.user.is_superuser:
                            return self.get_response(request)
                        # Alle anderen blockieren
                        return redirect('/maintenance.html')
                    else:
                        raise  # Re-raise if it's a different OperationalError
                
                client_ip = self.get_client_ip(request)
                
                # Prüfe IP-Whitelist
                if not self.is_ip_whitelisted(client_ip, config):
                    # Prüfe ob es eine statische Datei, Media-Datei oder Maintenance-Seite selbst ist
                    if request.path.startswith('/static/') or request.path == '/maintenance.html' or request.path.startswith('/media/'):
                        return self.get_response(request)
                    
                    # Admin-Bereich immer erlauben (damit sich Admins einloggen können)
                    # Django leitet /admin/ automatisch zu /admin/login/ um, wenn nicht eingeloggt
                    # Unterstützt sowohl /admin/ als auch /de/admin/ (mit Sprach-Präfix)
                    if '/admin/' in request.path:
                        logger.debug(f"[MaintenanceMode] Allowing admin access (path: {request.path})")
                        return self.get_response(request)
                    
                    # Prüfe ob Admin-Zugriff erlaubt ist (für alle Seiten, nicht nur /admin/)
                    if config.allow_admin_during_maintenance:
                        # Superuser können auf alle Seiten zugreifen (auch /de/map/, /de/game/, etc.)
                        if request.user.is_authenticated and request.user.is_superuser:
                            logger.debug(f"[MaintenanceMode] Allowing access for superuser {request.user.username} from IP {client_ip} (path: {request.path})")
                            return self.get_response(request)
                    
                    # Alle anderen Pfade blockieren
                    logger.info(f"[MaintenanceMode] Redirecting IP {client_ip} to maintenance page (path: {request.path})")
                    return redirect('/maintenance.html')
            except Exception as e:
                # Bei Fehlern: Maintenance-Mode trotzdem aktivieren (Fail-Safe)
                logger.error(f"[MaintenanceMode] Error checking maintenance config: {e}")
                # Prüfe ob es statische Dateien oder Maintenance-Seite ist
                if request.path.startswith('/static/') or request.path == '/maintenance.html' or request.path.startswith('/media/'):
                    return self.get_response(request)
                # Admin-Bereich immer erlauben (auch bei Fehlern)
                # Unterstützt sowohl /admin/ als auch /de/admin/ (mit Sprach-Präfix)
                if '/admin/' in request.path:
                    logger.warning(f"[MaintenanceMode] Error occurred, but allowing admin access (path: {request.path})")
                    return self.get_response(request)
                # Bei Fehlern: Zugriff für Superuser auf alle Seiten erlauben (Fail-Safe)
                if request.user.is_authenticated and request.user.is_superuser:
                    logger.warning(f"[MaintenanceMode] Error occurred, but allowing access for superuser {request.user.username} (path: {request.path})")
                    return self.get_response(request)
                # Alle anderen Pfade blockieren
                return redirect('/maintenance.html')
        
        return self.get_response(request)
    
    def get_client_ip(self, request):
        """Get client IP address from request."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            # Bei Proxy: Erste IP ist die Client-IP
            ip = x_forwarded_for.split(',')[0].strip()
            return ip
        return request.META.get('REMOTE_ADDR')
    
    def is_ip_whitelisted(self, ip_str, config):
        """
        Check if IP is in whitelist.
        
        Supports:
        - Single IP addresses (e.g., 192.168.1.100)
        - CIDR blocks (e.g., 192.168.1.0/24, 10.0.0.0/8)
        """
        if not ip_str:
            return False
        
        ip_list = config.get_ip_list()
        if not ip_list:
            return False
        
        try:
            client_ip = ip_address(ip_str)
            for whitelist_entry in ip_list:
                try:
                    # Prüfe einzelne IP
                    if '/' not in whitelist_entry:
                        if ip_address(whitelist_entry) == client_ip:
                            logger.debug(f"[MaintenanceMode] IP {ip_str} matches whitelist entry {whitelist_entry}")
                            return True
                    else:
                        # Prüfe CIDR-Block
                        if client_ip in ip_network(whitelist_entry, strict=False):
                            logger.debug(f"[MaintenanceMode] IP {ip_str} matches CIDR block {whitelist_entry}")
                            return True
                except ValueError as e:
                    logger.warning(f"[MaintenanceMode] Invalid whitelist entry '{whitelist_entry}': {e}")
                    continue
        except ValueError as e:
            logger.warning(f"[MaintenanceMode] Invalid client IP '{ip_str}': {e}")
            return False
        
        return False
