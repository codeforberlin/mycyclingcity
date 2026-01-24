# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    admin.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
from django.contrib import admin
from django.utils.safestring import mark_safe
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from django.urls import reverse, path
from .models import GameRoom, GameSession
from .dashboard import game_dashboard
import json
from datetime import timedelta


@admin.register(GameRoom)
class GameRoomAdmin(admin.ModelAdmin):
    """Admin interface for GameRoom management."""
    
    list_display = (
        'room_code',
        'status_display',
        'created_at',
        'last_activity',
        'age_display',
        'participants_count',
        'participants_display',
        'assignments_count',
        'current_target_km_display',
        'game_status_display',
        'room_link',
    )
    
    list_filter = (
        'is_active',
        'is_game_stopped',
        'created_at',
        'last_activity',
    )
    
    search_fields = (
        'room_code',
        'master_session_key',
    )
    
    date_hierarchy = 'created_at'
    
    ordering = ['-created_at']
    
    readonly_fields = (
        'room_code',
        'created_at',
        'last_activity',
        'device_assignments_display',
        'start_distances_display',
        'stop_distances_display',
        'active_sessions_display',
        'session_to_cyclist_display',
        'announced_winners_display',
        'statistics_display',
        'participants_count',
        'participants_display',
        'assignments_count',
        'room_link',
    )
    
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('room_code', 'is_active', 'master_session_key', 'created_at', 'last_activity', 'room_link')
        }),
        (_('Game Status'), {
            'fields': ('is_game_stopped', 'current_target_km', 'announced_winners_display')
        }),
        (_('Participants & Sessions'), {
            'fields': ('participants_count', 'participants_display', 'active_sessions_display', 'session_to_cyclist_display')
        }),
        (_('Device Assignments'), {
            'fields': ('device_assignments_display', 'assignments_count')
        }),
        (_('Distances'), {
            'fields': ('start_distances_display', 'stop_distances_display')
        }),
        (_('Statistics'), {
            'fields': ('statistics_display',)
        }),
    )
    
    actions = [
        'end_rooms',
        'delete_old_rooms',
        'cleanup_inactive_rooms',
        'activate_rooms',
        'become_master',
        'force_become_master',
    ]
    
    def status_display(self, obj):
        """Display room status with color coding."""
        if obj.is_active:
            color = '#28a745'  # Green
            text = _('🟢 Active')
        else:
            color = '#6c757d'  # Gray
            text = _('⚫ Ended')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, text
        )
    status_display.short_description = _('Status')
    status_display.admin_order_field = 'is_active'
    
    def age_display(self, obj):
        """Display room age in human-readable format."""
        age = timezone.now() - obj.created_at
        if age.days > 0:
            return _("{count} day(s)").format(count=age.days)
        elif age.seconds >= 3600:
            hours = age.seconds // 3600
            return _("{count} hour(s)").format(count=hours)
        elif age.seconds >= 60:
            minutes = age.seconds // 60
            return _("{count} minute(s)").format(count=minutes)
        else:
            return _("< 1 minute")
    age_display.short_description = _('Age')
    age_display.admin_order_field = 'created_at'
    
    def participants_count(self, obj):
        """Display number of active participants."""
        count = len(obj.active_sessions) if obj.active_sessions else 0
        return count
    participants_count.short_description = _('Participants')
    participants_count.admin_order_field = 'active_sessions'
    
    def participants_display(self, obj):
        """Display list of participants (cyclists) in the room."""
        if not obj.session_to_cyclist:
            return "-"
        
        # Get unique cyclists from session_to_cyclist mapping
        cyclists = list(set(obj.session_to_cyclist.values()))
        
        if not cyclists:
            return "-"
        
        # Sort for consistent display
        cyclists.sort()
        
        # Display as formatted HTML list (works well in both list and detail view)
        html = '<ul style="margin: 0; padding-left: 20px;">'
        for cyclist in cyclists:
            html += f'<li>{cyclist}</li>'
        html += '</ul>'
        return mark_safe(html)
    participants_display.short_description = _('Participants (Cyclists)')
    
    def room_link(self, obj):
        """Display link to enter the room."""
        if not obj.is_active:
            return format_html('<span style="color: #6c757d;">{}</span>', _('Room ended'))
        
        room_url = reverse('game:room_page', args=[obj.room_code])
        return format_html(
            '<a href="{}" target="_blank" style="background-color: #28a745; color: white; padding: 6px 12px; '
            'text-decoration: none; border-radius: 4px; font-weight: bold; display: inline-block;">'
            '🚪 {}</a>',
            room_url, _('Enter Room')
        )
    room_link.short_description = _('Enter Room')
    
    def assignments_count(self, obj):
        """Display number of device assignments."""
        count = len(obj.device_assignments) if obj.device_assignments else 0
        return count
    assignments_count.short_description = _('Assignments')
    
    def current_target_km_display(self, obj):
        """Display current target kilometers."""
        if obj.current_target_km and obj.current_target_km > 0:
            return f"{obj.current_target_km:.1f} km"
        return "-"
    current_target_km_display.short_description = _('Target (km)')
    current_target_km_display.admin_order_field = 'current_target_km'
    
    def game_status_display(self, obj):
        """Display game status."""
        if obj.is_game_stopped:
            return format_html('<span style="color: #dc3545;">⏸ {}</span>', _('Stopped'))
        elif obj.start_distances:
            return format_html('<span style="color: #28a745;">▶ {}</span>', _('Running'))
        else:
            return format_html('<span style="color: #6c757d;">⏹ {}</span>', _('Not Started'))
    game_status_display.short_description = _('Game Status')
    
    def device_assignments_display(self, obj):
        """Display device assignments as formatted table."""
        if not obj.device_assignments:
            return "-"
        
        html = '<table style="width: 100%; border-collapse: collapse;">'
        html += f'<thead><tr style="background-color: #f8f9fa;"><th style="padding: 8px; border: 1px solid #dee2e6;">{_("Device")}</th><th style="padding: 8px; border: 1px solid #dee2e6;">{_("Cyclist")}</th></tr></thead>'
        html += '<tbody>'
        
        for device, cyclist in obj.device_assignments.items():
            html += f'<tr><td style="padding: 8px; border: 1px solid #dee2e6;">{device}</td><td style="padding: 8px; border: 1px solid #dee2e6;">{cyclist}</td></tr>'
        
        html += '</tbody></table>'
        return mark_safe(html)
    device_assignments_display.short_description = _('Device Assignments')
    
    def start_distances_display(self, obj):
        """Display start distances as formatted table."""
        if not obj.start_distances:
            return "-"
        
        html = '<table style="width: 100%; border-collapse: collapse;">'
        html += f'<thead><tr style="background-color: #f8f9fa;"><th style="padding: 8px; border: 1px solid #dee2e6;">{_("Cyclist")}</th><th style="padding: 8px; border: 1px solid #dee2e6;">{_("Start Distance (km)")}</th></tr></thead>'
        html += '<tbody>'
        
        for cyclist, distance in obj.start_distances.items():
            html += f'<tr><td style="padding: 8px; border: 1px solid #dee2e6;">{cyclist}</td><td style="padding: 8px; border: 1px solid #dee2e6;">{distance:.2f}</td></tr>'
        
        html += '</tbody></table>'
        return mark_safe(html)
    start_distances_display.short_description = _('Start Distances')
    
    def stop_distances_display(self, obj):
        """Display stop distances as formatted table."""
        if not obj.stop_distances:
            return "-"
        
        html = '<table style="width: 100%; border-collapse: collapse;">'
        html += f'<thead><tr style="background-color: #f8f9fa;"><th style="padding: 8px; border: 1px solid #dee2e6;">{_("Cyclist")}</th><th style="padding: 8px; border: 1px solid #dee2e6;">{_("Stop Distance (km)")}</th></tr></thead>'
        html += '<tbody>'
        
        for cyclist, distance in obj.stop_distances.items():
            html += f'<tr><td style="padding: 8px; border: 1px solid #dee2e6;">{cyclist}</td><td style="padding: 8px; border: 1px solid #dee2e6;">{distance:.2f}</td></tr>'
        
        html += '</tbody></table>'
        return mark_safe(html)
    stop_distances_display.short_description = _('Stop Distances')
    
    def active_sessions_display(self, obj):
        """Display active sessions as list."""
        if not obj.active_sessions:
            return "-"
        
        html = '<ul style="margin: 0; padding-left: 20px;">'
        for session in obj.active_sessions:
            html += f'<li>{session[:20]}...</li>'
        html += '</ul>'
        return mark_safe(html)
    active_sessions_display.short_description = _('Active Sessions')
    
    def session_to_cyclist_display(self, obj):
        """Display session to cyclist mapping as formatted table."""
        if not obj.session_to_cyclist:
            return "-"
        
        html = '<table style="width: 100%; border-collapse: collapse;">'
        html += f'<thead><tr style="background-color: #f8f9fa;"><th style="padding: 8px; border: 1px solid #dee2e6;">{_("Session Key")}</th><th style="padding: 8px; border: 1px solid #dee2e6;">{_("Cyclist")}</th></tr></thead>'
        html += '<tbody>'
        
        for session, cyclist in obj.session_to_cyclist.items():
            session_short = session[:20] + '...' if len(session) > 20 else session
            html += f'<tr><td style="padding: 8px; border: 1px solid #dee2e6;">{session_short}</td><td style="padding: 8px; border: 1px solid #dee2e6;">{cyclist}</td></tr>'
        
        html += '</tbody></table>'
        return mark_safe(html)
    session_to_cyclist_display.short_description = _('Session → Cyclist Mapping')
    
    def announced_winners_display(self, obj):
        """Display announced winners as list."""
        if not obj.announced_winners:
            return "-"
        
        html = '<ul style="margin: 0; padding-left: 20px;">'
        for winner in obj.announced_winners:
            html += f'<li>🏆 {winner}</li>'
        html += '</ul>'
        return mark_safe(html)
    announced_winners_display.short_description = _('Announced Winners')
    
    def statistics_display(self, obj):
        """Display room statistics."""
        stats = []
        
        # Room age
        age = timezone.now() - obj.created_at
        if age.days > 0:
            stats.append(f"<strong>{_('Age')}:</strong> {_('{count} day(s)').format(count=age.days)}")
        else:
            hours = age.seconds // 3600
            minutes = (age.seconds % 3600) // 60
            stats.append(f"<strong>{_('Age')}:</strong> {hours}h {minutes}m")
        
        # Time since last activity
        if obj.last_activity:
            inactive = timezone.now() - obj.last_activity
            if inactive.days > 0:
                stats.append(f"<strong>{_('Inactive since')}:</strong> {_('{count} day(s)').format(count=inactive.days)}")
            elif inactive.seconds >= 3600:
                hours = inactive.seconds // 3600
                stats.append(f"<strong>{_('Inactive since')}:</strong> {_('{count} hour(s)').format(count=hours)}")
            else:
                minutes = inactive.seconds // 60
                stats.append(f"<strong>{_('Inactive since')}:</strong> {_('{count} minute(s)').format(count=minutes)}")
        
        # Participants
        participants = len(obj.active_sessions) if obj.active_sessions else 0
        stats.append(f"<strong>{_('Participants')}:</strong> {participants}")
        
        # Assignments
        assignments = len(obj.device_assignments) if obj.device_assignments else 0
        stats.append(f"<strong>{_('Assignments')}:</strong> {assignments}")
        
        # Game status
        if obj.is_game_stopped:
            stats.append(f"<strong>{_('Game Status')}:</strong> {_('Stopped')}")
        elif obj.start_distances:
            stats.append(f"<strong>{_('Game Status')}:</strong> {_('Running')}")
        else:
            stats.append(f"<strong>{_('Game Status')}:</strong> {_('Not Started')}")
        
        html = '<div style="padding: 10px; background-color: #f8f9fa; border-radius: 4px;">'
        html += '<br>'.join(stats)
        html += '</div>'
        return mark_safe(html)
    statistics_display.short_description = _('Statistics')
    
    # --- Bulk Actions ---
    
    def end_rooms(self, request, queryset):
        """End selected rooms (set is_active=False)."""
        count = 0
        for room in queryset:
            if room.is_active:
                room.is_active = False
                room.save()
                count += 1
        
        self.message_user(
            request,
            _("{count} room(s) have been ended.").format(count=count)
        )
    end_rooms.short_description = _("End selected rooms")
    
    def activate_rooms(self, request, queryset):
        """Activate selected rooms (set is_active=True)."""
        count = 0
        for room in queryset:
            if not room.is_active:
                room.is_active = True
                room.save()
                count += 1
        
        self.message_user(
            request,
            _("{count} room(s) have been activated.").format(count=count)
        )
    activate_rooms.short_description = _("Activate selected rooms")
    
    def delete_old_rooms(self, request, queryset):
        """Delete rooms older than 7 days."""
        cutoff_date = timezone.now() - timedelta(days=7)
        old_rooms = queryset.filter(created_at__lt=cutoff_date)
        count = old_rooms.count()
        old_rooms.delete()
        
        self.message_user(
            request,
            _("{count} room(s) older than 7 days have been deleted.").format(count=count)
        )
    delete_old_rooms.short_description = _("Delete rooms older than 7 days")
    
    def cleanup_inactive_rooms(self, request, queryset):
        """Delete rooms inactive for more than 24 hours."""
        cutoff_time = timezone.now() - timedelta(hours=24)
        inactive_rooms = queryset.filter(
            last_activity__lt=cutoff_time,
            is_active=False
        )
        count = inactive_rooms.count()
        inactive_rooms.delete()
        
        self.message_user(
            request,
            _("{count} inactive room(s) (no activity for 24h) have been deleted.").format(count=count)
        )
    cleanup_inactive_rooms.short_description = _("Delete inactive rooms (>24h)")
    
    def become_master(self, request, queryset):
        """Set the current admin user as master of selected rooms (only if no active master exists).
        
        This sets a special flag that will make the admin automatically become master
        when they enter the room, but only if there's no active master session.
        """
        count = 0
        skipped_with_master = 0
        
        for room in queryset:
            if not room.is_active:
                continue
            
            # Check if there's an active master
            current_master = room.master_session_key
            if current_master and not current_master.startswith('admin_pending_'):
                # There's already an active master, check if session is still active
                active_sessions = room.active_sessions or []
                if current_master in active_sessions:
                    # Active master exists, skip this room
                    skipped_with_master += 1
                    continue
            
            # No active master or master session is inactive - set admin as pending master
            # Format: "admin_pending_{user_id}_{username}"
            # This will be replaced with the actual session key when admin enters the room
            room.master_session_key = f"admin_pending_{request.user.id}_{request.user.username}"
            
            # Update last_activity to trigger sync
            room.last_activity = timezone.now()
            room.save()
            count += 1
        
        messages = []
        if count > 0:
            messages.append(_("You will be automatically set as master when you enter {count} room(s) via the 'Enter Room' link (only if no active master exists).").format(count=count))
        if skipped_with_master > 0:
            messages.append(_("{count} room(s) were skipped because an active master already exists.").format(count=skipped_with_master))
        
        if messages:
            self.message_user(request, " ".join(messages), level='success' if count > 0 else 'info')
        else:
            self.message_user(
                request,
                _("No active rooms selected or all rooms are already ended."),
                level='warning'
            )
    become_master.short_description = _("Set as Master (Admin, only if no master exists)")
    
    def force_become_master(self, request, queryset):
        """Force set the current admin user as master of selected rooms, even if a master already exists.
        
        This will override any existing master when the admin enters the room.
        Use with caution - this will replace the current master.
        """
        count = 0
        replaced_masters = 0
        
        for room in queryset:
            if not room.is_active:
                continue
            
            # Check if there's an active master that will be replaced
            current_master = room.master_session_key
            has_active_master = False
            if current_master and not current_master.startswith('admin_pending_'):
                active_sessions = room.active_sessions or []
                if current_master in active_sessions:
                    has_active_master = True
                    replaced_masters += 1
            
            # Force set admin as pending master (will override existing master)
            # Format: "admin_pending_force_{user_id}_{username}"
            # The "force" marker indicates this should override existing master
            room.master_session_key = f"admin_pending_force_{request.user.id}_{request.user.username}"
            
            # Update last_activity to trigger sync
            room.last_activity = timezone.now()
            room.save()
            count += 1
        
        messages = []
        if count > 0:
            messages.append(_("You will be set as master when you enter {count} room(s) via the 'Enter Room' link.").format(count=count))
        if replaced_masters > 0:
            messages.append(_("⚠️ {count} room(s) already had an active master, which will be replaced.").format(count=replaced_masters))
        
        if messages:
            self.message_user(request, " ".join(messages), level='warning' if replaced_masters > 0 else 'success')
        else:
            self.message_user(
                request,
                _("No active rooms selected or all rooms are already ended."),
                level='warning'
            )
    force_become_master.short_description = _("Force Master Role (replaces current master)")
    
    def get_queryset(self, request):
        """Optimize queryset."""
        return super().get_queryset(request)
    
    def get_urls(self):
        """Add dashboard URL to admin."""
        urls = super().get_urls()
        custom_urls = [
            path('dashboard/', self.admin_site.admin_view(game_dashboard), name='game_gameroom_dashboard'),
        ]
        return custom_urls + urls


@admin.register(GameSession)
class GameSessionModelAdmin(admin.ModelAdmin):
    """Admin interface for GameSession model (tracking game sessions)."""
    
    list_display = (
        'session_key_short',
        'room_code',
        'is_master',
        'has_assignments',
        'has_target_km',
        'created_at',
        'last_updated',
    )
    
    list_filter = (
        'room_code',
        'is_master',
        'has_assignments',
        'has_target_km',
        'created_at',
        'last_updated',
    )
    
    search_fields = (
        'session_key',
        'room_code',
    )
    
    readonly_fields = (
        'session_key',
        'created_at',
        'last_updated',
    )
    
    date_hierarchy = 'created_at'
    
    ordering = ['-last_updated']
    
    def session_key_short(self, obj):
        """Display shortened session key."""
        return f"{obj.session_key[:20]}..."
    session_key_short.short_description = _('Session Key')
