# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    session_admin.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
from django.contrib import admin
from django.contrib.sessions.models import Session
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.exceptions import SuspiciousSession
from django.utils.safestring import mark_safe
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from django.urls import reverse, path
from django.db.models import Q
from .models import GameRoom
import base64
import pickle
import json
import zlib
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


def decode_session_data(session_data):
    """Decode Django session data using Django's SessionStore.
    
    This uses Django's SessionStore to decode session data, which handles
    all the complexity of compression, base64 encoding, and serialization.
    """
    if not session_data:
        logger.debug("decode_session_data: session_data is empty or None")
        return {}
    
    try:
        # Method 1: Use SessionStore.decode() - same as Session.get_decoded()
        # This is the most reliable method as it uses Django's own decoding logic
        # NOTE: SessionStore.decode() uses signing.loads() which validates signatures
        # If signature is invalid, it returns {} and logs a warning, but doesn't raise an exception
        try:
            from django.contrib.sessions.backends.db import SessionStore
            # Create a temporary SessionStore and use its decode method
            # This handles compression, base64, serialization, and signature validation
            store = SessionStore()
            session_dict = store.decode(session_data)
            
            # If decode returns empty dict, it might be due to invalid signature
            # Try manual decoding as fallback (which doesn't validate signatures)
            if session_dict:
                logger.debug(f"decode_session_data: Successfully decoded using SessionStore.decode(), dict_keys={list(session_dict.keys())}")
                return session_dict
            else:
                # Empty dict might mean invalid signature - try manual decoding
                logger.debug(f"decode_session_data: SessionStore.decode() returned empty dict (possibly invalid signature), trying manual decode")
                return _manual_decode_session_data(session_data)
        except Exception as e:
            logger.debug(f"decode_session_data: SessionStore.decode() failed: {e}, trying manual decode")
            return _manual_decode_session_data(session_data)
    except Exception as e:
        logger.error(f"Unexpected error decoding session data: {e}", exc_info=True)
        return {}


def is_game_session(session):
    """Check if a session is a game session (has game-related data).
    
    A session is recognized as a game session if ANY of the following conditions are met:
    1. User is in a room (room_code is set and not empty)
    2. User has device assignments (device_assignments is set and not empty) - works for both room and single-player mode
    3. User is a master (is_master is True) - only relevant in room mode
    4. User has set a target (current_target_km is set and > 0) - works for both room and single-player mode
    
    Recognition happens:
    - Immediately when creating/joining a room (room_code + is_master set)
    - When assigning a device to a cyclist (device_assignments set) - works for both room and single-player mode
    - When setting a target kilometer (current_target_km > 0) - works for both room and single-player mode
    
    Single-player games (without room) are recognized as soon as:
    - A device is assigned to a cyclist, OR
    - A target kilometer is set (> 0)
    """
    try:
        session_dict = decode_session_data(session.session_data)
        
        # Log ALL sessions for debugging (we need to see what's happening)
        logger.info(f"🔍 Checking session: {session.session_key[:10]}..., "
                   f"session_dict_keys={list(session_dict.keys())}, "
                   f"session_dict_len={len(session_dict)}")
        
        # Check for game-related keys
        
        # 1. User is in a room
        has_room_code = 'room_code' in session_dict and session_dict.get('room_code')
        
        # 2. User has device assignments (works for both room and single-player mode)
        device_assignments = session_dict.get('device_assignments', {})
        has_assignments = isinstance(device_assignments, dict) and len(device_assignments) > 0
        
        # 3. User is a master (only relevant in room mode)
        has_master = 'is_master' in session_dict and session_dict.get('is_master')
        
        # 4. User has set a target (works for both room and single-player mode)
        target_km = session_dict.get('current_target_km', 0.0)
        has_target_km = 'current_target_km' in session_dict and target_km and target_km > 0
        
        # Debug logging for troubleshooting (use INFO level for visibility during debugging)
        if has_room_code or has_assignments or has_master or has_target_km:
            logger.info(f"✅ Game session detected: session_key={session.session_key[:10]}..., "
                       f"has_room_code={has_room_code}, has_assignments={has_assignments} "
                       f"(count={len(device_assignments) if isinstance(device_assignments, dict) else 0}, "
                       f"value={device_assignments}), has_master={has_master}, has_target_km={has_target_km} (value={target_km})")
        else:
            # Log why it's not a game session
            logger.info(f"❌ Not a game session: session_key={session.session_key[:10]}..., "
                       f"session_keys={list(session_dict.keys())}, "
                       f"device_assignments={device_assignments} (type={type(device_assignments)}, "
                       f"isinstance_dict={isinstance(device_assignments, dict)}, "
                       f"len={len(device_assignments) if isinstance(device_assignments, dict) else 'N/A'}), "
                       f"has_room_code={has_room_code}, has_master={has_master}, has_target_km={has_target_km} (value={target_km})")
        
        # Session is a game session if ANY condition is met
        # This includes single-player games (without room) that have assignments
        return has_room_code or has_assignments or has_master or has_target_km
    except Exception as e:
        logger.error(f"Error checking game session: {e}", exc_info=True)
        return False


def _manual_decode_session_data(session_data):
    """Manual fallback for decoding session data if Django's decoder fails.
    
    This implements the same logic as Django's decoder but with better error handling.
    """
    data_length = len(session_data)
    logger.info(f"decode_session_data: Starting manual decode, length={data_length}, first_100_chars={repr(session_data[:100])}")
    
    try:
        # Django sessions can be compressed (zlib) and then base64-encoded
        # Compressed sessions start with '.' (Django's compression marker)
        is_compressed = session_data.startswith('.')
        
        if is_compressed:
            session_data = session_data[1:]  # Remove the '.' prefix
            logger.info(f"decode_session_data: Detected compressed session data, removed '.' prefix")
        
        # Clean and decode Base64
        # CRITICAL: Remove non-base64 characters BEFORE calculating padding
        # But preserve '=' characters as they are part of Base64 padding
        import re
        # First, strip whitespace and newlines
        session_data_stripped = session_data.strip().replace('\n', '').replace('\r', '')
        # Remove non-base64 characters (but keep = for padding)
        session_data_cleaned = re.sub(r'[^A-Za-z0-9+/=]', '', session_data_stripped)
        
        # Calculate padding needed (Base64 strings must be multiples of 4)
        # CRITICAL: Count only non-padding characters for padding calculation
        # Base64 padding uses '=' characters, but we need to count data characters separately
        data_chars = session_data_cleaned.rstrip('=')
        data_length = len(data_chars)
        padding_needed = (4 - (data_length % 4)) % 4
        
        # Ensure the string has the correct padding
        # Remove existing padding and add correct padding
        session_data_cleaned = data_chars + '=' * padding_needed
        
        # Verify the length is now a multiple of 4
        final_length = len(session_data_cleaned)
        if final_length % 4 != 0:
            # Still not a multiple of 4, this should not happen but add more padding just in case
            additional_padding = (4 - (final_length % 4)) % 4
            session_data_cleaned += '=' * additional_padding
            logger.warning(f"decode_session_data: Had to add additional padding, final_length={len(session_data_cleaned)}")
        
        # Try to decode with validate=False first (more lenient)
        try:
            decoded = base64.b64decode(session_data_cleaned, validate=False)
            logger.info(f"decode_session_data: Successfully decoded base64 (lenient), decoded_length={len(decoded)}, data_length={data_length}, padding_needed={padding_needed}, final_length={len(session_data_cleaned)}")
        except Exception as e:
            # If lenient decoding fails, try with binascii.a2b_base64 which is more forgiving
            try:
                import binascii
                # binascii.a2b_base64 ignores invalid characters and handles padding more leniently
                decoded = binascii.a2b_base64(session_data_cleaned)
                logger.info(f"decode_session_data: Successfully decoded base64 (binascii), decoded_length={len(decoded)}, data_length={data_length}, padding_needed={padding_needed}, final_length={len(session_data_cleaned)}")
            except Exception as e2:
                logger.info(f"Could not decode base64 session data: base64.b64decode error={e}, binascii.a2b_base64 error={e2}, data_length={data_length}, padding_needed={padding_needed}, final_length={len(session_data_cleaned)}, first_20_chars={repr(session_data_cleaned[:20])}, last_20_chars={repr(session_data_cleaned[-20:])}")
                return {}
        
        # Decompress if needed
        # CRITICAL: If decompression fails, the data might not actually be compressed
        # even though it starts with '.'. This can happen if Django's compression
        # threshold wasn't met or if the data is corrupted.
        decompression_successful = False
        if is_compressed:
            # Check if the decoded data starts with zlib header (0x78 0x9c)
            if len(decoded) >= 2 and decoded[0] == 0x78 and decoded[1] == 0x9c:
                # Valid zlib header, try decompression
                try:
                    decompressed = zlib.decompress(decoded)
                    decoded = decompressed
                    decompression_successful = True
                    logger.info(f"decode_session_data: Successfully decompressed, decompressed_length={len(decoded)}")
                except zlib.error as e:
                    # Decompression failed - the data might be corrupted or incomplete
                    # Try different zlib window sizes
                    logger.info(f"decode_session_data: Standard decompression failed: {e}, first_bytes={decoded[:10] if len(decoded) >= 10 else decoded}")
                    # Try with different zlib window sizes
                    for wbits in [15, 15+16, 15+32]:  # Standard, gzip, raw
                        try:
                            decompressed = zlib.decompress(decoded, wbits)
                            decoded = decompressed
                            decompression_successful = True
                            logger.info(f"decode_session_data: Successfully decompressed with wbits={wbits}, decompressed_length={len(decoded)}")
                            break
                        except zlib.error:
                            continue
                    
                    if not decompression_successful:
                        logger.warning(f"decode_session_data: All decompression attempts failed, data might be corrupted")
            else:
                # No valid zlib header, data might not be compressed
                logger.info(f"decode_session_data: No valid zlib header (first bytes: {decoded[:2] if len(decoded) >= 2 else 'too short'}), treating as uncompressed")
                decompression_successful = True  # Treat as already decompressed
        else:
            # Not compressed, treat as successful
            decompression_successful = True
        
        # Try pickle first (default Django serializer)
        # Only try to decode if decompression was successful or data was not compressed
        if decompression_successful:
            try:
                session_dict = pickle.loads(decoded)
                logger.info(f"decode_session_data: Successfully decoded with pickle, dict_keys={list(session_dict.keys())}")
                return session_dict
            except (pickle.UnpicklingError, TypeError, ValueError) as e:
                # Try JSON
                try:
                    session_dict = json.loads(decoded.decode('utf-8'))
                    logger.info(f"decode_session_data: Successfully decoded with JSON, dict_keys={list(session_dict.keys())}")
                    return session_dict
                except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as e2:
                    logger.info(f"Could not decode session data with pickle or JSON. Pickle error: {e}, JSON error: {e2}")
                    return {}
        else:
            # Decompression failed and data is compressed
            # Try to decode the compressed data directly as if it were uncompressed
            # This might work if the data is actually uncompressed despite the '.' prefix
            logger.warning(f"decode_session_data: Decompression failed, trying to decode compressed data as uncompressed")
            try:
                # Try to decode the compressed bytes directly with pickle
                session_dict = pickle.loads(decoded)
                logger.info(f"decode_session_data: Successfully decoded compressed data as uncompressed pickle, dict_keys={list(session_dict.keys())}")
                return session_dict
            except (pickle.UnpicklingError, TypeError, ValueError) as e:
                logger.warning(f"decode_session_data: Cannot decode compressed data - decompression failed and direct decode failed: {e}")
                return {}
    except Exception as e:
        logger.error(f"Error in manual decode: {e}", exc_info=True)
        return {}


class GameSessionAdmin(admin.ModelAdmin):
    """Admin interface for Game Session management."""
    
    list_display = (
        'session_key_short',
        'room_code_display',
        'cyclist_display',
        'is_master_display',
        'assignments_count',
        'last_activity_display',
        'age_display',
        'expire_date',
        'actions_display',
    )
    
    list_filter = (
        'expire_date',
        ('expire_date', admin.DateFieldListFilter),
    )
    
    search_fields = (
        'session_key',
    )
    
    date_hierarchy = 'expire_date'
    
    ordering = ['-expire_date']
    
    readonly_fields = (
        'session_key',
        'session_data_display',
        'expire_date',
        'room_code_display',
        'cyclist_display',
        'is_master_display',
        'assignments_display',
        'game_data_display',
        'statistics_display',
    )
    
    fieldsets = (
        (_('Basis-Informationen'), {
            'fields': ('session_key', 'expire_date', 'room_code_display', 'cyclist_display', 'is_master_display')
        }),
        (_('Session-Daten'), {
            'fields': ('session_data_display', 'game_data_display', 'assignments_display')
        }),
        (_('Statistiken'), {
            'fields': ('statistics_display',)
        }),
    )
    
    actions = [
        'delete_sessions',
        'remove_from_rooms',
        'cleanup_expired_sessions',
        'export_sessions',
    ]
    
    def get_queryset(self, request):
        """Filter to show only game sessions using GameSession model."""
        from .models import GameSession
        
        qs = super().get_queryset(request)
        # Filter sessions that are not expired
        now = timezone.now()
        qs = qs.filter(expire_date__gt=now)
        
        # Use GameSession model for efficient filtering
        # Get all session keys that are tracked as game sessions
        game_session_keys = list(GameSession.objects.values_list('session_key', flat=True))
        
        total_sessions = qs.count()
        logger.info(f"🔍 get_queryset: Checking {total_sessions} active sessions, {len(game_session_keys)} tracked as game sessions")
        
        # Return only game sessions
        return qs.filter(session_key__in=game_session_keys)
    
    def session_key_short(self, obj):
        """Display shortened session key."""
        key = obj.session_key
        if len(key) > 20:
            return f"{key[:20]}..."
        return key
    session_key_short.short_description = _('Session Key')
    session_key_short.admin_order_field = 'session_key'
    
    def room_code_display(self, obj):
        """Display room code if session is in a room."""
        try:
            session_dict = decode_session_data(obj.session_data)
            room_code = session_dict.get('room_code')
            if room_code:
                try:
                    room = GameRoom.objects.get(room_code=room_code)
                    room_url = reverse('admin:game_gameroom_change', args=[room.pk])
                    return format_html(
                        '<a href="{}" target="_blank">{}</a>',
                        room_url, room_code
                    )
                except GameRoom.DoesNotExist:
                    return format_html('<span style="color: #dc3545;">{} (Raum nicht gefunden)</span>', room_code)
            return "-"
        except Exception as e:
            logger.error(f"Error getting room code: {e}")
            return "-"
    room_code_display.short_description = _('Raum')
    
    def cyclist_display(self, obj):
        """Display assigned cyclist(s)."""
        try:
            session_dict = decode_session_data(obj.session_data)
            device_assignments = session_dict.get('device_assignments', {})
            if device_assignments:
                cyclists = list(set(device_assignments.values()))
                if cyclists:
                    return ", ".join(cyclists)
            return "-"
        except Exception as e:
            logger.error(f"Error getting cyclist: {e}")
            return "-"
    cyclist_display.short_description = _('Radler')
    
    def is_master_display(self, obj):
        """Display master status."""
        try:
            session_dict = decode_session_data(obj.session_data)
            is_master = session_dict.get('is_master', False)
            if is_master:
                return format_html('<span style="color: #28a745; font-weight: bold;">👑 Master</span>')
            return "-"
        except Exception as e:
            logger.error(f"Error getting master status: {e}")
            return "-"
    is_master_display.short_description = _('Master')
    
    def assignments_count(self, obj):
        """Display number of device assignments."""
        try:
            session_dict = decode_session_data(obj.session_data)
            device_assignments = session_dict.get('device_assignments', {})
            return len(device_assignments) if device_assignments else 0
        except Exception as e:
            logger.error(f"Error getting assignments count: {e}")
            return 0
    assignments_count.short_description = _('Zuweisungen')
    
    def last_activity_display(self, obj):
        """Display last activity (based on expire_date)."""
        # Approximate last activity from expire_date
        # Django sessions expire after SESSION_COOKIE_AGE (default 2 weeks)
        # This is an approximation
        return obj.expire_date.strftime('%Y-%m-%d %H:%M')
    last_activity_display.short_description = _('Ablauf')
    last_activity_display.admin_order_field = 'expire_date'
    
    def age_display(self, obj):
        """Display session age."""
        # Approximate age from expire_date
        # Sessions expire after SESSION_COOKIE_AGE, so we can estimate creation time
        age = timezone.now() - (obj.expire_date - timedelta(weeks=2))
        if age.days > 0:
            return f"{age.days} Tag(e)"
        elif age.seconds >= 3600:
            hours = age.seconds // 3600
            return f"{hours} Stunde(n)"
        elif age.seconds >= 60:
            minutes = age.seconds // 60
            return f"{minutes} Minute(n)"
        else:
            return "< 1 Minute"
    age_display.short_description = _('Alter')
    
    def actions_display(self, obj):
        """Display action buttons."""
        try:
            session_dict = decode_session_data(obj.session_data)
            room_code = session_dict.get('room_code')
            
            html = '<div style="display: flex; gap: 5px;">'
            
            # View details link
            detail_url = reverse('admin:game_session_change', args=[obj.pk])
            html += format_html(
                '<a href="{}" class="button" style="padding: 4px 8px; background: #417690; color: white; text-decoration: none; border-radius: 3px; font-size: 0.85em;">Details</a>',
                detail_url
            )
            
            # Enter room link (if in room)
            if room_code:
                try:
                    room = GameRoom.objects.get(room_code=room_code, is_active=True)
                    room_url = reverse('game:room_page', args=[room_code])
                    html += format_html(
                        '<a href="{}" target="_blank" class="button" style="padding: 4px 8px; background: #28a745; color: white; text-decoration: none; border-radius: 3px; font-size: 0.85em;">Raum betreten</a>',
                        room_url
                    )
                except GameRoom.DoesNotExist:
                    pass
            
            html += '</div>'
            return mark_safe(html)
        except Exception as e:
            logger.error(f"Error generating actions: {e}")
            return "-"
    actions_display.short_description = _('Aktionen')
    
    def session_data_display(self, obj):
        """Display formatted session data."""
        try:
            session_dict = decode_session_data(obj.session_data)
            # Format as JSON for readability
            formatted = json.dumps(session_dict, indent=2, ensure_ascii=False, default=str)
            return format_html('<pre style="background: #f8f9fa; padding: 10px; border-radius: 4px; overflow-x: auto;">{}</pre>', formatted)
        except Exception as e:
            logger.error(f"Error displaying session data: {e}")
            return format_html('<span style="color: #dc3545;">Fehler beim Dekodieren: {}</span>', str(e))
    session_data_display.short_description = _('Session-Daten (vollständig)')
    
    def game_data_display(self, obj):
        """Display only game-related session data."""
        try:
            session_dict = decode_session_data(obj.session_data)
            game_keys = ['room_code', 'is_master', 'device_assignments', 'current_target_km', 
                          'start_distances', 'stop_distances', 'is_game_stopped', 'announced_winners']
            game_data = {k: v for k, v in session_dict.items() if k in game_keys}
            
            if not game_data:
                return "-"
            
            formatted = json.dumps(game_data, indent=2, ensure_ascii=False, default=str)
            return format_html('<pre style="background: #f8f9fa; padding: 10px; border-radius: 4px; overflow-x: auto;">{}</pre>', formatted)
        except Exception as e:
            logger.error(f"Error displaying game data: {e}")
            return format_html('<span style="color: #dc3545;">Fehler: {}</span>', str(e))
    game_data_display.short_description = _('Game-Daten')
    
    def assignments_display(self, obj):
        """Display device assignments as formatted table."""
        try:
            session_dict = decode_session_data(obj.session_data)
            device_assignments = session_dict.get('device_assignments', {})
            
            if not device_assignments:
                return "-"
            
            html = '<table style="width: 100%; border-collapse: collapse;">'
            html += '<thead><tr style="background-color: #f8f9fa;"><th style="padding: 8px; border: 1px solid #dee2e6;">Gerät</th><th style="padding: 8px; border: 1px solid #dee2e6;">Radler</th></tr></thead>'
            html += '<tbody>'
            
            for device, cyclist in device_assignments.items():
                html += f'<tr><td style="padding: 8px; border: 1px solid #dee2e6;">{device}</td><td style="padding: 8px; border: 1px solid #dee2e6;">{cyclist}</td></tr>'
            
            html += '</tbody></table>'
            return mark_safe(html)
        except Exception as e:
            logger.error(f"Error displaying assignments: {e}")
            return format_html('<span style="color: #dc3545;">Fehler: {}</span>', str(e))
    assignments_display.short_description = _('Geräte-Zuweisungen')
    
    def statistics_display(self, obj):
        """Display session statistics."""
        try:
            session_dict = decode_session_data(obj.session_data)
            stats = []
            
            # Room info
            room_code = session_dict.get('room_code')
            if room_code:
                stats.append(f"<strong>Raum:</strong> {room_code}")
            
            # Master status
            is_master = session_dict.get('is_master', False)
            stats.append(f"<strong>Master:</strong> {'Ja' if is_master else 'Nein'}")
            
            # Assignments
            device_assignments = session_dict.get('device_assignments', {})
            stats.append(f"<strong>Zuweisungen:</strong> {len(device_assignments)}")
            
            # Target KM
            target_km = session_dict.get('current_target_km', 0)
            if target_km:
                stats.append(f"<strong>Ziel (km):</strong> {target_km:.1f}")
            
            # Game status
            is_stopped = session_dict.get('is_game_stopped', False)
            if is_stopped:
                stats.append(f"<strong>Spiel-Status:</strong> Gestoppt")
            elif session_dict.get('start_distances'):
                stats.append(f"<strong>Spiel-Status:</strong> Läuft")
            
            html = '<div style="padding: 10px; background-color: #f8f9fa; border-radius: 4px;">'
            html += '<br>'.join(stats)
            html += '</div>'
            return mark_safe(html)
        except Exception as e:
            logger.error(f"Error displaying statistics: {e}")
            return format_html('<span style="color: #dc3545;">Fehler: {}</span>', str(e))
    statistics_display.short_description = _('Statistiken')
    
    # --- Bulk Actions ---
    
    def delete_sessions(self, request, queryset):
        """Delete selected sessions (users will be logged out)."""
        # CRITICAL: Exclude the current admin's session to prevent logout
        current_session_key = request.session.session_key
        if current_session_key:
            queryset = queryset.exclude(session_key=current_session_key)
        
        count = queryset.count()
        if count > 0:
            queryset.delete()
            self.message_user(
                request,
                _("{} Session(s) wurden gelöscht. Die Benutzer wurden ausgeloggt.").format(count)
            )
        else:
            self.message_user(
                request,
                _("Keine Sessions gelöscht. Ihre eigene Session kann nicht gelöscht werden."),
                level='warning'
            )
    delete_sessions.short_description = _("Ausgewählte Sessions löschen")
    
    def remove_from_rooms(self, request, queryset):
        """Remove sessions from their rooms (clear room_code from session)."""
        # CRITICAL: Exclude the current admin's session to prevent logout
        current_session_key = request.session.session_key
        if current_session_key:
            queryset = queryset.exclude(session_key=current_session_key)
        
        count = 0
        skipped_own = 0
        for session in queryset:
            try:
                session_dict = decode_session_data(session.session_data)
                if 'room_code' in session_dict:
                    # We can't directly modify session_data here, so we delete the session
                    # The user will be logged out and can rejoin if needed
                    session.delete()
                    count += 1
            except Exception as e:
                logger.error(f"Error removing from room: {e}")
        
        messages = []
        if count > 0:
            messages.append(_("{} Session(s) wurden aus Räumen entfernt (Sessions gelöscht).").format(count))
        if skipped_own > 0:
            messages.append(_("Ihre eigene Session wurde übersprungen."))
        
        if messages:
            self.message_user(request, " ".join(messages))
        else:
            self.message_user(
                request,
                _("Keine Sessions entfernt. Ihre eigene Session kann nicht entfernt werden."),
                level='warning'
            )
    remove_from_rooms.short_description = _("Aus Räumen entfernen")
    
    def cleanup_expired_sessions(self, request, queryset):
        """Delete expired sessions."""
        # CRITICAL: Exclude the current admin's session to prevent logout
        current_session_key = request.session.session_key
        if current_session_key:
            queryset = queryset.exclude(session_key=current_session_key)
        
        now = timezone.now()
        expired = queryset.filter(expire_date__lt=now)
        count = expired.count()
        if count > 0:
            expired.delete()
            self.message_user(
                request,
                _("{} abgelaufene Session(s) wurden gelöscht.").format(count)
            )
        else:
            self.message_user(
                request,
                _("Keine abgelaufenen Sessions gefunden."),
                level='info'
            )
    cleanup_expired_sessions.short_description = _("Abgelaufene Sessions löschen")
    
    def export_sessions(self, request, queryset):
        """Export session data as JSON."""
        from django.http import HttpResponse
        
        sessions_data = []
        for session in queryset:
            try:
                session_dict = decode_session_data(session.session_data)
                sessions_data.append({
                    'session_key': session.session_key,
                    'expire_date': session.expire_date.isoformat(),
                    'data': session_dict
                })
            except Exception as e:
                logger.error(f"Error exporting session: {e}")
        
        response = HttpResponse(
            json.dumps({'sessions': sessions_data}, indent=2, ensure_ascii=False, default=str),
            content_type='application/json; charset=utf-8'
        )
        response['Content-Disposition'] = f'attachment; filename="game_sessions_export_{timezone.now().strftime("%Y%m%d_%H%M%S")}.json"'
        return response
    export_sessions.short_description = _("Sessions als JSON exportieren")
    
    def get_urls(self):
        """Add custom URLs for session management."""
        from .session_dashboard import session_dashboard
        
        urls = super().get_urls()
        custom_urls = [
            path('dashboard/', self.admin_site.admin_view(session_dashboard), name='game_session_dashboard'),
            path('<path:object_id>/edit-data/', self.admin_site.admin_view(self.edit_session_data_view), name='game_session_edit_data'),
            path('<path:object_id>/delete-data-key/', self.admin_site.admin_view(self.delete_session_data_key_view), name='game_session_delete_data_key'),
        ]
        return custom_urls + urls
    
    def edit_session_data_view(self, request, object_id):
        """View for editing session data."""
        from django.shortcuts import render, redirect
        from django.contrib import messages
        
        try:
            session = Session.objects.get(pk=object_id)
            session_dict = decode_session_data(session.session_data)
            
            if request.method == 'POST':
                # Handle form submission
                key = request.POST.get('key')
                value = request.POST.get('value')
                
                if key:
                    try:
                        # Try to parse as JSON if value is provided
                        if value:
                            # Try to parse as JSON first
                            try:
                                parsed_value = json.loads(value)
                                session_dict[key] = parsed_value
                            except (json.JSONDecodeError, ValueError):
                                # If not valid JSON, store as string
                                session_dict[key] = value
                        elif key in session_dict:
                            del session_dict[key]
                        
                        # Re-encode and save
                        encoded = base64.b64encode(pickle.dumps(session_dict)).decode('ascii')
                        session.session_data = encoded
                        session.save()
                        
                        messages.success(request, _("Session-Daten wurden aktualisiert."))
                        return redirect('admin:sessions_session_change', object_id=object_id)
                    except Exception as e:
                        messages.error(request, _("Fehler beim Speichern: {}").format(str(e)))
            
            context = {
                'session': session,
                'session_dict': session_dict,
                'title': _('Session-Daten bearbeiten'),
            }
            return render(request, 'admin/game/edit_session_data.html', context)
        except Session.DoesNotExist:
            messages.error(request, _("Session nicht gefunden."))
            return redirect('admin:game_session_changelist')
    
    def delete_session_data_key_view(self, request, object_id):
        """Delete a specific key from session data."""
        from django.shortcuts import redirect
        from django.contrib import messages
        
        try:
            session = Session.objects.get(pk=object_id)
            session_dict = decode_session_data(session.session_data)
            
            key = request.GET.get('key')
            if key and key in session_dict:
                del session_dict[key]
                
                # Re-encode and save
                encoded = base64.b64encode(pickle.dumps(session_dict)).decode('ascii')
                session.session_data = encoded
                session.save()
                
                messages.success(request, _("Schlüssel '{}' wurde aus der Session entfernt.").format(key))
            else:
                messages.error(request, _("Schlüssel nicht gefunden."))
        except Session.DoesNotExist:
            messages.error(request, _("Session nicht gefunden."))
        
        return redirect('admin:sessions_session_change', object_id=object_id)
