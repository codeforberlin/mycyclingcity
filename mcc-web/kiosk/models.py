# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    models.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator, MaxValueValidator


class KioskDevice(models.Model):
    """Remote Kiosk device configuration and hardware control."""
    name = models.CharField(
        max_length=200,
        verbose_name=_("Gerätename"),
        help_text=_("Lesbarer Name für dieses Kiosk-Gerät")
    )
    uid = models.CharField(
        max_length=100,
        unique=True,
        verbose_name=_("Eindeutige ID"),
        help_text=_("Eindeutige Kennung für dieses Gerät (z.B. MAC-Adresse oder Seriennummer)")
    )
    brightness = models.IntegerField(
        default=100,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name=_("Helligkeit"),
        help_text=_("Helligkeitsstufe der Anzeige (0-100)")
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Aktiv"),
        help_text=_("Ob dieses Gerät derzeit aktiv ist und Inhalte anzeigen soll")
    )
    command_queue = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_("Befehls-Warteschlange"),
        help_text=_("JSON-Array mit ausstehenden Hardware-Befehlen (z.B. ['RELOAD', 'SET_BRIGHTNESS:50'])")
    )
    assigned_to_group = models.ForeignKey(
        'api.Group',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_kiosk_devices',
        verbose_name=_("Zugewiesene TOP-Gruppe"),
        help_text=_("TOP-Gruppe, der dieses Kiosk-Gerät zugewiesen ist. "
                   "Operatoren dieser TOP-Gruppe können das Gerät verwalten. "
                   "Kann vom System-Admin gesetzt werden, bevor Playlist-Einträge erstellt werden.")
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Erstellt am"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Aktualisiert am"))

    class Meta:
        verbose_name = _("Device")
        verbose_name_plural = _("Devices")
        ordering = ['name']

    def __str__(self):
        return self.name

    def add_command(self, command: str) -> None:
        """Adds a command to the queue."""
        if not isinstance(self.command_queue, list):
            self.command_queue = []
        self.command_queue.append(command)
        self.save(update_fields=['command_queue'])

    def clear_commands(self) -> None:
        """Clear all commands from the queue."""
        self.command_queue = []
        self.save(update_fields=['command_queue'])

    def pop_command(self) -> str | None:
        """Pop and return the first command from the queue, or None if empty."""
        if not isinstance(self.command_queue, list) or not self.command_queue:
            return None
        command = self.command_queue.pop(0)
        self.save(update_fields=['command_queue'])
        return command


class KioskPlaylistEntry(models.Model):
    """Playlist entry defining a view to display on a Kiosk device."""
    VIEW_TYPES = [
        ('leaderboard', _("Leaderboard")),
        ('eventboard', _("Eventboard")),
        ('map', _("Map")),
    ]

    device = models.ForeignKey(
        KioskDevice,
        on_delete=models.CASCADE,
        related_name='playlist_entries',
        verbose_name=_("Kiosk Device")
    )
    view_type = models.CharField(
        max_length=20,
        choices=VIEW_TYPES,
        default='leaderboard',
        verbose_name=_("Ansichtstyp"),
        help_text=_("Art der anzuzeigenden Ansicht")
    )
    event_filter = models.ForeignKey(
        'eventboard.Event',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='kiosk_playlist_entries',
        verbose_name=_("Event-Filter"),
        help_text=_("Optional: Inhalte nach spezifischem Event filtern")
    )
    group_filter = models.ForeignKey(
        'api.Group',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='kiosk_playlist_entries',
        verbose_name=_("Gruppen-Filter"),
        help_text=_("Optional: Inhalte filtern, um nur Gruppen und Radler anzuzeigen, die zu dieser Hauptgruppe gehören")
    )
    track_filter = models.ManyToManyField(
        'api.TravelTrack',
        blank=True,
        related_name='kiosk_playlist_entries',
        verbose_name=_("Routen-Filter"),
        help_text=_("Optional: Kartenansicht filtern, um nur ausgewählte Routen anzuzeigen (leer lassen, um alle Routen anzuzeigen)")
    )
    display_duration = models.IntegerField(
        default=30,
        validators=[MinValueValidator(1)],
        verbose_name=_("Anzeigedauer (Sekunden)"),
        help_text=_("Wie lange diese Ansicht angezeigt werden soll, bevor zur nächsten gewechselt wird")
    )
    order = models.PositiveIntegerField(
        default=1,
        verbose_name=_("Reihenfolge"),
        help_text=_("Anzeigereihenfolge in der Playlist (niedrigere Zahlen zuerst, beginnt bei 1)")
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Aktiv"),
        help_text=_("Ob dieser Eintrag in der Playlist aktiv ist")
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Erstellt am"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Aktualisiert am"))

    class Meta:
        verbose_name = _("Playlist Entry")
        verbose_name_plural = _("Playlist Entries")
        ordering = ['device', 'order', 'id']
        unique_together = [['device', 'order']]

    def __str__(self):
        filters = []
        
        # Safely access event_filter without triggering queries
        try:
            if self.event_filter_id:
                if hasattr(self, '_event_filter_cache'):
                    event_name = self._event_filter_cache.name
                else:
                    # Only query if we have a saved instance
                    if self.pk:
                        try:
                            event_name = self.event_filter.name if self.event_filter else None
                        except Exception:
                            event_name = None
                    else:
                        event_name = None
                if event_name:
                    filters.append(f"Event: {event_name}")
        except (AttributeError, Exception):
            pass
        
        # Safely access group_filter without triggering queries
        try:
            if self.group_filter_id:
                if hasattr(self, '_group_filter_cache'):
                    group_name = self._group_filter_cache.name
                else:
                    # Only query if we have a saved instance
                    if self.pk:
                        try:
                            group_name = self.group_filter.name if self.group_filter else None
                        except Exception:
                            group_name = None
                    else:
                        group_name = None
                if group_name:
                    filters.append(f"Group: {group_name}")
        except (AttributeError, Exception):
            pass
        
        # Safely access track_filter without triggering queries
        try:
            # Only query track_filter if we have a saved instance and can safely access it
            if self.pk:
                # Use a try-except to avoid recursion if the object is in an invalid state
                try:
                    track_count = self.track_filter.count()
                    if track_count > 0:
                        track_names = [t.name for t in self.track_filter.all()[:3]]
                        if track_count > 3:
                            track_names.append(f"... (+{track_count - 3} more)")
                        filters.append(f"Tracks: {', '.join(track_names)}")
                except (RecursionError, AttributeError, Exception):
                    # If we hit recursion or any error, just skip track_filter
                    pass
        except (AttributeError, Exception):
            pass
        
        filter_str = f" ({', '.join(filters)})" if filters else ""
        
        # Safely access device name
        try:
            if hasattr(self, 'device_id') and self.device_id:
                if hasattr(self, '_device_cache'):
                    device_name = self._device_cache.name
                else:
                    # Only query if we have a saved instance
                    if self.pk:
                        try:
                            device_name = self.device.name if self.device else f"Device {self.device_id}"
                        except Exception:
                            device_name = f"Device {self.device_id}"
                    else:
                        device_name = f"Device {self.device_id}"
            else:
                device_name = "Unknown Device"
        except (AttributeError, Exception):
            device_name = "Unknown Device"
        
        return f"{device_name} - {self.get_view_type_display()} (Order: {self.order}){filter_str}"

