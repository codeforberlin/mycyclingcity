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
        help_text=_("Eindeutiger Code für diesen Spielraum")
    )
    
    master_session_key = models.CharField(
        max_length=40,
        null=True,
        blank=True,
        verbose_name=_("Spielleiter-Sitzungsschlüssel"),
        help_text=_("Sitzungsschlüssel des Spielleiters")
    )
    
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Aktiv"),
        help_text=_("Ob dieser Raum aktiv ist oder beendet wurde")
    )
    
    device_assignments = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("Gerätezuweisungen"),
        help_text=_("Zuordnung von Gerätenamen zu Radfahrer-User-IDs (z.B. {'device1': 'cyclist1'})")
    )
    
    start_distances = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("Startentfernungen"),
        help_text=_("Entfernungen der Radfahrer beim Spielstart (z.B. {'cyclist1': 100.5})")
    )
    
    stop_distances = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("Stoppentfernungen"),
        help_text=_("Entfernungen der Radfahrer beim Spielstopp (z.B. {'cyclist1': 150.2})")
    )
    
    is_game_stopped = models.BooleanField(
        default=False,
        verbose_name=_("Spiel gestoppt"),
        help_text=_("Ob das Spiel gestoppt wurde")
    )
    
    announced_winners = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_("Bekanntgegebene Gewinner"),
        help_text=_("Liste von User-IDs der Radfahrer, die bereits als Gewinner bekanntgegeben wurden")
    )
    
    current_target_km = models.FloatField(
        default=0.0,
        verbose_name=_("Aktuelles Ziel (km)"),
        help_text=_("Das aktuelle Ziel in Kilometern für dieses Spiel")
    )
    
    active_sessions = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_("Aktive Sitzungen"),
        help_text=_("Liste von Sitzungsschlüsseln, die diesem Raum aktuell beigetreten sind")
    )
    
    session_to_cyclist = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("Sitzung zu Radfahrer Zuordnung"),
        help_text=_("Zuordnung von Sitzungsschlüsseln zu Radfahrer-User-IDs (für Spielleiter-Übertragung)")
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
        verbose_name = _("Spielraum")
        verbose_name_plural = _("Spielräume")
        ordering = ['-created_at']
    
    def __str__(self):
        from django.utils.translation import gettext_lazy as _
        return f"Raum {self.room_code} ({_('Aktiv') if self.is_active else _('Beendet')})"
    
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
        verbose_name=_("Sitzungsschlüssel"),
        help_text=_("Django Sitzungsschlüssel")
    )
    
    room_code = models.CharField(
        max_length=8,
        null=True,
        blank=True,
        db_index=True,
        verbose_name=_("Raum-Code"),
        help_text=_("Raum-Code, falls die Sitzung in einem Raum ist")
    )
    
    is_master = models.BooleanField(
        default=False,
        verbose_name=_("Spielleiter"),
        help_text=_("Ob diese Sitzung die Spielleiter-Sitzung ist")
    )
    
    has_assignments = models.BooleanField(
        default=False,
        verbose_name=_("Hat Zuweisungen"),
        help_text=_("Ob diese Sitzung Gerätezuweisungen hat")
    )
    
    has_target_km = models.BooleanField(
        default=False,
        verbose_name=_("Hat Ziel-KM"),
        help_text=_("Ob diese Sitzung ein Zielkilometer gesetzt hat")
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Erstellt am")
    )
    
    last_updated = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Zuletzt aktualisiert")
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
