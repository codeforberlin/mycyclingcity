# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    dashboard.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.db.models import Count, Q, Avg
from django.db.models.functions import Extract
from .models import GameRoom
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


@staff_member_required
def game_dashboard(request):
    """Main game dashboard view showing statistics and active rooms."""
    
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=7)
    month_start = today_start - timedelta(days=30)
    
    # Statistics
    active_rooms = GameRoom.objects.filter(is_active=True)
    active_rooms_count = active_rooms.count()
    
    # Count active sessions across all rooms
    total_active_sessions = 0
    for room in active_rooms:
        if room.active_sessions:
            total_active_sessions += len(room.active_sessions)
    
    # Count active games (rooms with start_distances)
    active_games = active_rooms.filter(
        Q(start_distances__isnull=False) & ~Q(start_distances={})
    ).exclude(is_game_stopped=True)
    active_games_count = active_games.count()
    
    # Rooms created today
    rooms_created_today = GameRoom.objects.filter(created_at__gte=today_start).count()
    
    # Calculate average room lifetime (for ended rooms)
    ended_rooms = GameRoom.objects.filter(is_active=False)
    avg_lifetime = None
    if ended_rooms.exists():
        lifetimes = []
        for room in ended_rooms:
            if room.last_activity and room.created_at:
                lifetime = (room.last_activity - room.created_at).total_seconds() / 60  # in minutes
                lifetimes.append(lifetime)
        if lifetimes:
            avg_lifetime = sum(lifetimes) / len(lifetimes)
            # Convert to hours if > 60 minutes
            if avg_lifetime >= 60:
                avg_lifetime = avg_lifetime / 60
                avg_lifetime_unit = _("Stunden")
            else:
                avg_lifetime_unit = _("Minuten")
        else:
            avg_lifetime_unit = None
    else:
        avg_lifetime_unit = None
    
    # Get current active rooms with details
    current_rooms = []
    for room in active_rooms.order_by('-last_activity')[:20]:  # Top 20 most recent
        participants_count = len(room.active_sessions) if room.active_sessions else 0
        assignments_count = len(room.device_assignments) if room.device_assignments else 0
        
        # Calculate age
        age = now - room.created_at
        if age.days > 0:
            age_display = f"{age.days} {_('Tag(e)')}"
        elif age.seconds >= 3600:
            hours = age.seconds // 3600
            age_display = f"{hours} {_('Stunde(n)')}"
        else:
            minutes = age.seconds // 60
            age_display = f"{minutes} {_('Minute(n)')}"
        
        # Calculate time since last activity
        if room.last_activity:
            inactive = now - room.last_activity
            if inactive.days > 0:
                inactive_display = f"{inactive.days} {_('Tag(e)')}"
            elif inactive.seconds >= 3600:
                hours = inactive.seconds // 3600
                inactive_display = f"{hours} {_('Stunde(n)')}"
            else:
                minutes = inactive.seconds // 60
                inactive_display = f"{minutes} {_('Minute(n)')}"
        else:
            inactive_display = "-"
        
        # Game status
        if room.is_game_stopped:
            game_status = _("Gestoppt")
            game_status_color = "#dc3545"
        elif room.start_distances:
            game_status = _("Läuft")
            game_status_color = "#28a745"
        else:
            game_status = _("Nicht gestartet")
            game_status_color = "#6c757d"
        
        current_rooms.append({
            'id': room.pk,  # Database ID for admin change URL
            'room_code': room.room_code,
            'created_at': room.created_at,
            'last_activity': room.last_activity,
            'age_display': age_display,
            'inactive_display': inactive_display,
            'participants_count': participants_count,
            'assignments_count': assignments_count,
            'current_target_km': room.current_target_km,
            'game_status': game_status,
            'game_status_color': game_status_color,
            'is_master_active': room.master_session_key and room.master_session_key in (room.active_sessions or []),
        })
    
    # Rooms created in last 7 days (for chart)
    rooms_by_day = {}
    for i in range(7):
        day = today_start - timedelta(days=i)
        day_end = day + timedelta(days=1)
        count = GameRoom.objects.filter(created_at__gte=day, created_at__lt=day_end).count()
        rooms_by_day[day.strftime('%Y-%m-%d')] = count
    
    context = {
        'title': _('Game Dashboard'),
        'active_rooms_count': active_rooms_count,
        'total_active_sessions': total_active_sessions,
        'active_games_count': active_games_count,
        'rooms_created_today': rooms_created_today,
        'avg_lifetime': avg_lifetime,
        'avg_lifetime_unit': avg_lifetime_unit,
        'current_rooms': current_rooms,
        'rooms_by_day': rooms_by_day,
    }
    
    return render(request, 'admin/game/dashboard.html', context)
