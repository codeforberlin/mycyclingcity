# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    session_dashboard.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.sessions.models import Session
from django.shortcuts import render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from .models import GameRoom
from .session_admin import decode_session_data, is_game_session
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


@staff_member_required
def session_dashboard(request):
    """Main session dashboard view showing statistics and active sessions."""
    
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Get all non-expired sessions
    all_sessions = Session.objects.filter(expire_date__gt=now)
    
    # Filter game sessions
    game_sessions = []
    for session in all_sessions:
        if is_game_session(session):
            game_sessions.append(session)
    
    # Statistics
    total_game_sessions = len(game_sessions)
    
    # Count sessions in rooms
    sessions_in_rooms = 0
    sessions_without_rooms = 0
    master_sessions = 0
    sessions_with_assignments = 0
    
    for session in game_sessions:
        try:
            session_dict = decode_session_data(session.session_data)
            if session_dict.get('room_code'):
                sessions_in_rooms += 1
            else:
                sessions_without_rooms += 1
            
            if session_dict.get('is_master'):
                master_sessions += 1
            
            device_assignments = session_dict.get('device_assignments', {})
            if device_assignments and len(device_assignments) > 0:
                sessions_with_assignments += 1
        except Exception as e:
            logger.error(f"Error processing session: {e}")
    
    # Get current active sessions with details
    current_sessions = []
    for session in game_sessions[:50]:  # Top 50 most recent
        try:
            session_dict = decode_session_data(session.session_data)
            
            # Get room info
            room_code = session_dict.get('room_code')
            room_info = None
            if room_code:
                try:
                    room = GameRoom.objects.get(room_code=room_code)
                    room_info = {
                        'code': room_code,
                        'is_active': room.is_active,
                        'pk': room.pk,
                    }
                except GameRoom.DoesNotExist:
                    room_info = {'code': room_code, 'is_active': False, 'pk': None}
            
            # Get cyclist info
            device_assignments = session_dict.get('device_assignments', {})
            cyclists = list(set(device_assignments.values())) if device_assignments else []
            
            # Master status
            is_master = session_dict.get('is_master', False)
            
            # Calculate age (approximate)
            age = now - (session.expire_date - timedelta(weeks=2))
            if age.days > 0:
                age_display = f"{age.days} Tag(e)"
            elif age.seconds >= 3600:
                hours = age.seconds // 3600
                age_display = f"{hours} Stunde(n)"
            else:
                minutes = age.seconds // 60
                age_display = f"{minutes} Minute(n)"
            
            current_sessions.append({
                'id': session.pk,
                'session_key': session.session_key,
                'session_key_short': session.session_key[:20] + '...' if len(session.session_key) > 20 else session.session_key,
                'room_info': room_info,
                'cyclists': cyclists,
                'is_master': is_master,
                'assignments_count': len(device_assignments) if device_assignments else 0,
                'age_display': age_display,
                'expire_date': session.expire_date,
            })
        except Exception as e:
            logger.error(f"Error processing session for dashboard: {e}")
    
    # Sessions created today (approximate)
    # Since we don't have created_at, we estimate based on expire_date
    sessions_created_today = 0
    for session in game_sessions:
        # Approximate: if expire_date is close to 2 weeks from now, session was created recently
        days_until_expiry = (session.expire_date - now).days
        if 13 <= days_until_expiry <= 14:  # Close to 2 weeks (default session age)
            sessions_created_today += 1
    
    context = {
        'title': _('Session Dashboard'),
        'total_game_sessions': total_game_sessions,
        'sessions_in_rooms': sessions_in_rooms,
        'sessions_without_rooms': sessions_without_rooms,
        'master_sessions': master_sessions,
        'sessions_with_assignments': sessions_with_assignments,
        'sessions_created_today': sessions_created_today,
        'current_sessions': current_sessions,
    }
    
    return render(request, 'admin/game/session_dashboard.html', context)
