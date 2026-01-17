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
        verbose_name=_("Raum-Code"),
        help_text=_("Eindeutiger Code für diesen Spiel-Raum")
    )
    
    master_session_key = models.CharField(
        max_length=40,
        null=True,
        blank=True,
        verbose_name=_("Master Session Key"),
        help_text=_("Session-Key des Spielleiters (Masters)")
    )
    
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Aktiv"),
        help_text=_("Ob dieser Raum aktiv ist oder beendet wurde")
    )
    
    device_assignments = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("Geräte-Zuweisungen"),
        help_text=_("Mapping von Gerätenamen zu Cyclist user_id (z.B. {'device1': 'cyclist1'})")
    )
    
    start_distances = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("Start-Distanzen"),
        help_text=_("Distanzen der Cyclists beim Spielstart (z.B. {'cyclist1': 100.5})")
    )
    
    stop_distances = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("Stop-Distanzen"),
        help_text=_("Distanzen der Cyclists beim Spielstopp (z.B. {'cyclist1': 150.2})")
    )
    
    is_game_stopped = models.BooleanField(
        default=False,
        verbose_name=_("Spiel gestoppt"),
        help_text=_("Ob das Spiel gestoppt wurde")
    )
    
    announced_winners = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_("Angekündigte Gewinner"),
        help_text=_("Liste der user_ids von Cyclists, die bereits als Gewinner angekündigt wurden")
    )
    
    current_target_km = models.FloatField(
        default=0.0,
        verbose_name=_("Aktuelles Ziel (km)"),
        help_text=_("Das aktuelle Ziel in Kilometern für dieses Spiel")
    )
    
    active_sessions = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_("Aktive Sessions"),
        help_text=_("Liste der Session-Keys, die aktuell diesem Raum beigetreten sind")
    )
    
    session_to_cyclist = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("Session zu Cyclist Mapping"),
        help_text=_("Mapping von Session-Keys zu Cyclist user_ids (für Master-Transfer)")
    )
    
    last_activity = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Letzte Aktivität"),
        help_text=_("Zeitpunkt der letzten Aktivität in diesem Raum")
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Erstellt am")
    )
    
    class Meta:
        verbose_name = _("Spiel-Raum")
        verbose_name_plural = _("Spiel-Räume")
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Room {self.room_code} ({'Aktiv' if self.is_active else 'Beendet'})"
    
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
