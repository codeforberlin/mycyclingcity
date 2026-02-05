# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    models.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.core.files.images import get_image_dimensions
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal


# --- VALIDATION ---
def validate_logo_size(image):
    if image:
        width, height = get_image_dimensions(image)
        if width > 500 or height > 500:
            raise ValidationError(
                _("Das Logo ist mit %(w)spx x %(h)spx zu groß. Maximal 500x500px erlaubt."),
                params={'w': width, 'h': height},
            )


# --- EVENT MODELS ---

class Event(models.Model):
    """Events like school festivals, celebrations, fundraising based on kilometers, etc."""
    EVENT_TYPES = [
        ('school_festival', _("Schulfest")),
        ('celebration', _("Feier")),
        ('fundraising', _("Spendensammeln")),
        ('competition', _("Wettbewerb")),
        ('other', _("Sonstiges")),
    ]
    
    name = models.CharField(max_length=200, verbose_name=_("Event-Name"))
    top_group = models.ForeignKey(
        'api.Group',
        on_delete=models.CASCADE,
        related_name='events',
        verbose_name=_("TOP-Gruppe"),
        help_text=_("Die TOP-Gruppe (Hauptgruppe ohne übergeordnete Gruppe), der dieses Event zugeordnet ist. Operatoren können nur Events ihrer verwalteten TOP-Gruppen erstellen und bearbeiten.")
    )
    event_type = models.CharField(max_length=50, choices=EVENT_TYPES, default='other', verbose_name=_("Event-Typ"))
    description = models.TextField(blank=True, null=True, verbose_name=_("Beschreibung"))
    is_active = models.BooleanField(default=True, verbose_name=_("Aktiv"))
    is_visible_on_map = models.BooleanField(default=True, verbose_name=_("In Map/Game anzeigen"))
    start_time = models.DateTimeField(null=True, blank=True, verbose_name=_("Startzeitpunkt"))
    end_time = models.DateTimeField(null=True, blank=True, verbose_name=_("Endzeitpunkt"))
    hide_after_date = models.DateTimeField(null=True, blank=True, verbose_name=_("Ab diesem Datum nicht mehr anzeigen"), help_text=_("Events werden nach diesem Datum nicht mehr in der Karte angezeigt, auch wenn sie noch aktiv sind"))
    target_distance_km = models.DecimalField(
        max_digits=15, 
        decimal_places=5, 
        null=True, 
        blank=True, 
        verbose_name=_("Kilometerziel"), 
        help_text=_("Gesamtes Kilometerziel für dieses Event (optional). Wird für Fortschrittsanzeige verwendet.")
    )
    update_interval_seconds = models.IntegerField(
        default=30,
        validators=[MinValueValidator(5), MaxValueValidator(300)],
        verbose_name=_("Update-Intervall (Sekunden)"),
        help_text=_("Aktualisierungsintervall für das Eventboard in Sekunden (5-300). Standard: 30 Sekunden.")
    )
    left_logo = models.ImageField(
        upload_to='event_logos/',
        null=True,
        blank=True,
        validators=[validate_logo_size],
        verbose_name=_("Logo links"),
        help_text=_("Logo/Bild, das links neben dem Event-Titel angezeigt wird (max. 500x500px)")
    )
    right_logo = models.ImageField(
        upload_to='event_logos/',
        null=True,
        blank=True,
        validators=[validate_logo_size],
        verbose_name=_("Logo rechts"),
        help_text=_("Logo/Bild, das rechts neben dem Event-Titel angezeigt wird (max. 500x500px)")
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Erstellt am"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Aktualisiert am"))

    class Meta:
        verbose_name = _("Event")
        verbose_name_plural = _("Events")
        ordering = ['-start_time', 'name']

    def __str__(self):
        return self.name

    def is_currently_active(self):
        """Check if the event is currently active and should collect kilometers."""
        # First check if event is active (enabled)
        if not self.is_active:
            return False
        # Then check time constraints
        now = timezone.now()
        if self.start_time and now < self.start_time:
            return False  # Not started yet
        if self.end_time and now > self.end_time:
            return False  # Already ended - stop collecting kilometers
        return True

    def should_be_displayed(self):
        """Check if the event should be displayed on the map."""
        if not self.is_visible_on_map:
            return False
        if not self.is_active:
            return False
        now = timezone.now()
        if self.hide_after_date and now > self.hide_after_date:
            return False  # Hide after configured date
        # Events can be displayed even after end_time (to show results)
        # Only check if start_time has passed (if set)
        if self.start_time and now < self.start_time:
            return False  # Don't show before start
        return True

    def get_total_distance_km(self):
        """Calculate total kilometers collected by all groups in this event."""
        from django.db.models import Sum
        total = self.group_statuses.aggregate(
            total=Sum('current_distance_km')
        )['total'] or Decimal('0.00000')
        return total

    def save_event_to_history(self):
        """Save current event progress to history for all participating groups."""
        now = timezone.now()
        for status in self.group_statuses.select_related('group', 'best_leaf_group').all():
            # Use get_or_create to avoid duplicate entries
            # If an entry with the same event, group, and start_time exists, update it instead
            start_time = self.start_time or now
            history_entry, created = EventHistory.objects.get_or_create(
                event=self,
                group=status.group,
                start_time=start_time,
                defaults={
                    'end_time': now,
                    'total_distance_km': status.current_distance_km,
                    'best_leaf_group': status.best_leaf_group,
                    'best_leaf_group_goal_reached_at': status.best_leaf_group_goal_reached_at
                }
            )
            # If entry already exists, update it with current data
            if not created:
                history_entry.end_time = now
                history_entry.total_distance_km = status.current_distance_km
                history_entry.best_leaf_group = status.best_leaf_group
                history_entry.best_leaf_group_goal_reached_at = status.best_leaf_group_goal_reached_at
                history_entry.save()
        # Reset event statuses after saving to history
        self.group_statuses.update(
            current_distance_km=Decimal('0.00000'),
            start_km_offset=Decimal('0.00000'),
            best_leaf_group=None,
            best_leaf_group_goal_reached_at=None
        )
        # Also reset leaf group contributions
        LeafGroupEventContribution.objects.filter(event=self).update(
            current_event_distance=Decimal('0.00000')
        )
    
    def restart_event(self):
        """
        Reset all event statuses for this event.
        
        Note: This does NOT delete EventHistory records, so groups
        keep their historical event achievements.
        
        Current progress is saved to history before resetting.
        """
        # Save current progress to history before resetting
        self.save_event_to_history()
        
        # Reset all group event statuses
        self.group_statuses.update(
            current_distance_km=Decimal('0.00000'),
            start_km_offset=Decimal('0.00000'),
            goal_reached_at=None,
            best_leaf_group=None,
            best_leaf_group_goal_reached_at=None
        )
        # Also reset leaf group contributions
        LeafGroupEventContribution.objects.filter(event=self).update(
            current_event_distance=Decimal('0.00000')
        )
    
    def get_progress_percentage(self):
        """Calculate progress percentage towards target distance."""
        if not self.target_distance_km:
            return None
        total = self.get_total_distance_km()
        if total == 0:
            return Decimal('0.00')
        percentage = (total / self.target_distance_km) * Decimal('100.00')
        return min(percentage, Decimal('100.00'))  # Cap at 100%
    
    def get_top_groups(self, limit=3):
        """
        Get top N groups that have reached the goal, sorted by goal_reached_at (who reached first).
        Only returns groups that have reached the target_distance_km.
        """
        if not self.target_distance_km:
            return self.group_statuses.none()
        
        # Filter groups that have reached the goal (current_distance_km >= target_distance_km)
        # Sort by goal_reached_at (who reached first - earliest goal_reached_at = first place)
        # If goal_reached_at is None, use a very late date to push them to the end
        reached_groups = self.group_statuses.filter(
            current_distance_km__gte=self.target_distance_km,
            goal_reached_at__isnull=False
        ).select_related('group', 'best_leaf_group').order_by(
            'goal_reached_at',  # Who reached first (earliest goal_reached_at = first place)
            '-current_distance_km'  # Fallback: higher distance if same time
        )[:limit]
        
        return reached_groups


class GroupEventStatus(models.Model):
    """Tracks a group's participation and kilometers in an event."""
    group = models.ForeignKey(
        'api.Group',
        on_delete=models.CASCADE,
        related_name='event_statuses',
        verbose_name=_("Gruppe")
    )
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name='group_statuses',
        verbose_name=_("Event")
    )
    current_distance_km = models.DecimalField(
        max_digits=15,
        decimal_places=5,
        default=Decimal('0.00000'),
        verbose_name=_("Aktuelle Distanz (km)")
    )
    start_km_offset = models.DecimalField(
        max_digits=15,
        decimal_places=5,
        default=Decimal('0.00000'),
        verbose_name=_("Start-Offset (km)")
    )
    goal_reached_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Ziel erreicht am"),
        help_text=_("Zeitpunkt, zu dem die Gruppe das Event-Ziel erreicht hat. Wird für die Sortierung auf dem Podest verwendet.")
    )
    best_leaf_group = models.ForeignKey(
        'api.Group',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='event_statuses_as_best_leaf',
        verbose_name=_("Beste Leaf-Gruppe"),
        help_text=_("Die Leaf-Gruppe (z.B. Klasse) mit den meisten gestrampelten Kilometern in dieser TOP-Gruppe")
    )
    best_leaf_group_goal_reached_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Ziel erreicht am (Beste Leaf-Gruppe)"),
        help_text=_("Zeitpunkt, zu dem die beste Leaf-Gruppe das Event-Ziel erreicht hat")
    )
    joined_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Beigetreten am"))

    class Meta:
        verbose_name = _("Gruppen-Event-Status")
        verbose_name_plural = _("Gruppen-Event-Status")
        unique_together = [['group', 'event']]

    def __str__(self):
        return f"{self.group.name} - {self.event.name} ({self.current_distance_km:.5f} km)"


class LeafGroupEventContribution(models.Model):
    """
    Tracks the event distance contribution of each leaf group during an event.
    
    This model allows tracking which leaf group (e.g., class) contributed the most
    kilometers to a parent group's (e.g., school) event. This is used for:
    - Podest display: The leaf group with the highest contribution is displayed
    - Goal achievement: The leaf group with the highest contribution is shown when goal is reached
    
    IMPORTANT: This is separate from GroupEventStatus, which tracks the parent group's
    total event distance. Leaf groups contribute to the parent's distance, but their
    individual contributions are tracked here.
    """
    leaf_group = models.ForeignKey(
        'api.Group',
        on_delete=models.CASCADE,
        related_name='event_contributions',
        verbose_name=_("Leaf-Gruppe"),
        help_text=_("Die Leaf-Gruppe (z.B. Klasse), die Kilometer beiträgt")
    )
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name='leaf_group_contributions',
        verbose_name=_("Event")
    )
    current_event_distance = models.DecimalField(
        max_digits=15,
        decimal_places=5,
        default=Decimal('0.00000'),
        verbose_name=_("Aktuelle Event-Distanz (km)"),
        help_text=_("Die von dieser Leaf-Gruppe während des aktuellen Events zurückgelegte Distanz")
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Aktualisiert am")
    )
    
    class Meta:
        verbose_name = _("Leaf-Gruppe Event-Beitrag")
        verbose_name_plural = _("Leaf-Gruppe Event-Beiträge")
        unique_together = [['leaf_group', 'event']]
        indexes = [
            models.Index(fields=['leaf_group', 'event']),
            models.Index(fields=['event', '-current_event_distance']),  # For finding highest contributor
        ]
    
    def __str__(self):
        return f"{self.leaf_group.name} - {self.event.name}: {self.current_event_distance} km"


class EventHistory(models.Model):
    """Stores completed events with collected kilometers per group."""
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name='history_entries',
        verbose_name=_("Event")
    )
    group = models.ForeignKey(
        'api.Group',
        on_delete=models.CASCADE,
        related_name='event_history',
        verbose_name=_("Gruppe")
    )
    start_time = models.DateTimeField(verbose_name=_("Startzeitpunkt"))
    end_time = models.DateTimeField(verbose_name=_("Endzeitpunkt"))
    total_distance_km = models.DecimalField(max_digits=15, decimal_places=5, default=Decimal('0.00000'), verbose_name=_("Gesammelte Kilometer"))
    best_leaf_group = models.ForeignKey(
        'api.Group',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='event_history_as_best_leaf',
        verbose_name=_("Beste Leaf-Gruppe"),
        help_text=_("Die Leaf-Gruppe (z.B. Klasse) mit den meisten gestrampelten Kilometern in dieser TOP-Gruppe")
    )
    best_leaf_group_goal_reached_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Ziel erreicht am (Beste Leaf-Gruppe)"),
        help_text=_("Zeitpunkt, zu dem die beste Leaf-Gruppe das Event-Ziel erreicht hat")
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Erstellt am"))

    class Meta:
        verbose_name = _("Events - History")
        verbose_name_plural = _("Events - Histories")
        ordering = ['-end_time']
        unique_together = [['event', 'group', 'start_time']]

    def __str__(self):
        return f"{self.group.name} - {self.event.name} ({self.total_distance_km:.5f} km)"
