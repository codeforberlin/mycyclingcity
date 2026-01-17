# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    models.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
import secrets
import string


def generate_room_code():
    """Generates a unique 6-character room code (uppercase letters and numbers)."""
    while True:
        code = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))
        if not GameRoom.objects.filter(room_code=code).exists():
            return code


class GameRoom(models.Model):
    """Represents a shared game room where multiple players can join and see the same game state."""
    room_code = models.CharField(
        max_length=6,
        unique=True,
        default=generate_room_code,
        verbose_name=_("Raum-Code"),
        help_text=_("6-stelliger Code zum Beitreten des Raums")
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Erstellt am")
    )
    last_activity = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Letzte Aktivität")
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Aktiv"),
        help_text=_("Ob der Raum noch aktiv ist")
    )
    
    # Game state stored in JSON format
    device_assignments = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("Geräte-Zuweisungen"),
        help_text=_("Dictionary: {device_name: cyclist_user_id}")
    )
    start_distances = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("Start-Distanzen"),
        help_text=_("Dictionary: {cyclist_user_id: start_distance}")
    )
    stop_distances = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("Stop-Distanzen"),
        help_text=_("Dictionary: {cyclist_user_id: stop_distance}")
    )
    is_game_stopped = models.BooleanField(
        default=False,
        verbose_name=_("Spiel gestoppt")
    )
    announced_winners = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_("Bereits angekündigte Gewinner"),
        help_text=_("Liste von cyclist_user_id, die bereits ein Popup erhalten haben")
    )
    current_target_km = models.FloatField(
        default=0.0,
        verbose_name=_("Aktuelles Ziel (km)")
    )
    master_session_key = models.CharField(
        max_length=40,
        null=True,
        blank=True,
        verbose_name=_("Master Session Key"),
        help_text=_("Session-Key des Raum-Masters (Spielleiter)")
    )
    active_sessions = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_("Aktive Sessions"),
        help_text=_("Liste von Session-Keys der aktiven Teilnehmer")
    )
    session_to_cyclist = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("Session zu Cyclist Mapping"),
        help_text=_("Dictionary: {session_key: cyclist_user_id} - Mapping von Session zu zugewiesenem Cyclist")
    )

    class Meta:
        verbose_name = _("Spiel-Raum")
        verbose_name_plural = _("Spiel-Räume")
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['room_code']),
            models.Index(fields=['is_active', '-last_activity']),
        ]

    def __str__(self):
        return f"Raum {self.room_code} ({'aktiv' if self.is_active else 'inaktiv'})"

    def save(self, *args, **kwargs):
        """Override save to ensure room_code is generated if not set."""
        if not self.room_code:
            self.room_code = generate_room_code()
        super().save(*args, **kwargs)
