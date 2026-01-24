# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    models.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
from django.db import models
from django.utils.translation import gettext_lazy as _
import secrets
import string


class GameRoom(models.Model):
    """Represents a shared game room where multiple players can participate."""
    
    room_code = models.CharField(
        max_length=8,
        unique=True,
        editable=False,
        verbose_name=_("Room Code"),
        help_text=_("Unique code for this game room")
    )
    
    master_session_key = models.CharField(
        max_length=40,
        null=True,
        blank=True,
        verbose_name=_("Master Session Key"),
        help_text=_("Session key of the game master")
    )
    
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Active"),
        help_text=_("Whether this room is active or has been ended")
    )
    
    device_assignments = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("Device Assignments"),
        help_text=_("Mapping of device names to cyclist user_id (e.g. {'device1': 'cyclist1'})")
    )
    
    start_distances = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("Start Distances"),
        help_text=_("Distances of cyclists at game start (e.g. {'cyclist1': 100.5})")
    )
    
    stop_distances = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("Stop Distances"),
        help_text=_("Distances of cyclists at game stop (e.g. {'cyclist1': 150.2})")
    )
    
    is_game_stopped = models.BooleanField(
        default=False,
        verbose_name=_("Game Stopped"),
        help_text=_("Whether the game has been stopped")
    )
    
    announced_winners = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_("Announced Winners"),
        help_text=_("List of user_ids of cyclists who have already been announced as winners")
    )
    
    current_target_km = models.FloatField(
        default=0.0,
        verbose_name=_("Current Target (km)"),
        help_text=_("The current target in kilometers for this game")
    )
    
    active_sessions = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_("Active Sessions"),
        help_text=_("List of session keys that have currently joined this room")
    )
    
    session_to_cyclist = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("Session to Cyclist Mapping"),
        help_text=_("Mapping of session keys to cyclist user_ids (for master transfer)")
    )
    
    last_activity = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Last Activity"),
        help_text=_("Time of last activity in this room")
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Created at")
    )
    
    class Meta:
        verbose_name = _("Game Room")
        verbose_name_plural = _("Game Rooms")
        ordering = ['-created_at']
    
    def __str__(self):
        from django.utils.translation import gettext_lazy as _
        return f"Room {self.room_code} ({_('Active') if self.is_active else _('Ended')})"
    
    def save(self, *args, **kwargs):
        """Override save to generate unique room_code if not set."""
        if not self.room_code:
            self.room_code = self._generate_room_code()
        super().save(*args, **kwargs)
    
    def _generate_room_code(self):
        """Generate a unique room code (8 characters, uppercase alphanumeric)."""
        alphabet = string.ascii_uppercase + string.digits
        # Exclude confusing characters: 0, O, I, 1
        alphabet = ''.join(c for c in alphabet if c not in '0O1I')
        
        max_attempts = 100
        for _ in range(max_attempts):
            code = ''.join(secrets.choice(alphabet) for _ in range(8))
            if not GameRoom.objects.filter(room_code=code).exists():
                return code
        
        # Fallback: if we can't generate a unique code after max_attempts, raise error
        raise ValueError("Could not generate unique room code after multiple attempts")


class GameSession(models.Model):
    """Tracks game sessions to enable efficient querying without decoding session data.
    
    This model provides a direct database reference for game sessions, making it
    much faster to query and filter game sessions in the Admin GUI.
    """
    
    session_key = models.CharField(
        max_length=40,
        unique=True,
        db_index=True,
        verbose_name=_("Session Key"),
        help_text=_("Django Session Key")
    )
    
    room_code = models.CharField(
        max_length=8,
        null=True,
        blank=True,
        db_index=True,
        verbose_name=_("Room Code"),
        help_text=_("Room code, if the session is in a room")
    )
    
    is_master = models.BooleanField(
        default=False,
        verbose_name=_("Master"),
        help_text=_("Whether this session is the master session")
    )
    
    has_assignments = models.BooleanField(
        default=False,
        verbose_name=_("Has Assignments"),
        help_text=_("Whether this session has device assignments")
    )
    
    has_target_km = models.BooleanField(
        default=False,
        verbose_name=_("Has Target KM"),
        help_text=_("Whether this session has set a target kilometer")
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Created at")
    )
    
    last_updated = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Last Updated")
    )
    
    class Meta:
        verbose_name = _("Game Session Tracking")
        verbose_name_plural = _("Game Session Tracking")
        ordering = ['-last_updated']
        indexes = [
            models.Index(fields=['room_code', 'is_master']),
            models.Index(fields=['has_assignments', 'has_target_km']),
        ]
    
    def __str__(self):
        room_info = f" (Room: {self.room_code})" if self.room_code else " (Single-Player)"
        master_info = " [Master]" if self.is_master else ""
        return f"Game Session {self.session_key[:10]}...{room_info}{master_info}"
