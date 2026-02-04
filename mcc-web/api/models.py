# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    models.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
from django.db import models, transaction
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.core.files.images import get_image_dimensions
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from decimal import Decimal
from PIL import Image  # Pillow for image processing
import os
from django.db.models import F

# --- VALIDATION ---
def validate_logo_size(image):
    if image:
        width, height = get_image_dimensions(image)
        if width > 500 or height > 500:
            raise ValidationError(
                _("Das Logo ist mit %(w)spx x %(h)spx zu groß. Maximal 500x500px erlaubt."),
                params={'w': width, 'h': height},
            )

# --- MAP POPUP SETTINGS ---
class MapPopupSettings(models.Model):
    """Global settings for map popup display times, colors, and transparency."""
    weltmeister_popup_duration_seconds = models.IntegerField(
        default=6,
        validators=[MinValueValidator(1), MaxValueValidator(300)],
        verbose_name=_("Kilometer-Weltmeister Popup Dauer (Sekunden)"),
        help_text=_("Anzeigedauer des Kilometer-Weltmeister Popups in Sekunden (1-300)")
    )
    
    milestone_popup_duration_seconds = models.IntegerField(
        default=30,
        validators=[MinValueValidator(1), MaxValueValidator(300)],
        verbose_name=_("Meilenstein Popup Dauer (Sekunden)"),
        help_text=_("Anzeigedauer des Meilenstein Popups in Sekunden (1-300)")
    )
    
    weltmeister_popup_background_color = models.CharField(
        max_length=7,
        default='#ffd700',
        verbose_name=_("Kilometer-Weltmeister Popup Hintergrundfarbe"),
        help_text=_("Hintergrundfarbe des Kilometer-Weltmeister Popups (Hex-Farbe, z.B. #ffd700 für Gold)")
    )
    
    weltmeister_popup_background_color_end = models.CharField(
        max_length=7,
        default='#ffed4e',
        verbose_name=_("Kilometer-Weltmeister Popup Hintergrundfarbe Ende (Gradient)"),
        help_text=_("Endfarbe für den Gradient-Hintergrund (Hex-Farbe, z.B. #ffed4e für helles Gold)")
    )
    
    weltmeister_popup_opacity = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=1.00,
        validators=[MinValueValidator(0.01), MaxValueValidator(1.00)],
        verbose_name=_("Kilometer-Weltmeister Popup Transparenz"),
        help_text=_("Transparenz des Kilometer-Weltmeister Popups (0.01 = fast transparent, 1.00 = vollständig opak)")
    )
    
    milestone_popup_background_color = models.CharField(
        max_length=7,
        default='#007bff',
        verbose_name=_("Meilenstein Popup Hintergrundfarbe"),
        help_text=_("Hintergrundfarbe des Meilenstein Popups (Hex-Farbe, z.B. #007bff für Blau)")
    )
    
    milestone_popup_opacity = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=1.00,
        validators=[MinValueValidator(0.01), MaxValueValidator(1.00)],
        verbose_name=_("Meilenstein Popup Transparenz"),
        help_text=_("Transparenz des Meilenstein Popups (0.01 = fast transparent, 1.00 = vollständig opak)")
    )
    
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Aktualisiert am"))
    
    class Meta:
        verbose_name = _("Map Popup Einstellungen")
        verbose_name_plural = _("Map Popup Einstellungen")
    
    def __str__(self):
        return _("Popup-Einstellungen (Weltmeister: %(weltmeister)s, Meilenstein: %(meilenstein)s)") % {
            'weltmeister': f"{self.weltmeister_popup_duration_seconds}s",
            'meilenstein': f"{self.milestone_popup_duration_seconds}s"
        }
    
    @classmethod
    def get_settings(cls):
        """Get or create the singleton settings instance."""
        settings, _ = cls.objects.get_or_create(pk=1)
        return settings

# --- GROUP TYPE ---
class GroupType(models.Model):
    """Defines the type of a group (e.g., 'Schule', 'Klasse')."""
    name = models.CharField(max_length=50, unique=True, verbose_name=_("Typ-Name"))
    description = models.TextField(blank=True, null=True, verbose_name=_("Beschreibung"))
    is_active = models.BooleanField(default=True, verbose_name=_("Aktiv"))
    
    class Meta:
        verbose_name = _("Group Type")
        verbose_name_plural = _("Group Types")
        ordering = ['name']
    
    def __str__(self):
        return self.name

# --- GROUP ---
class Group(models.Model):
    group_type = models.ForeignKey(
        GroupType,
        on_delete=models.PROTECT,
        related_name='groups',
        verbose_name=_("Gruppentyp")
    )
    name = models.CharField(max_length=100, verbose_name=_("Gruppenname"))
    distance_total = models.DecimalField(max_digits=15, decimal_places=5, default=Decimal('0.00000'), verbose_name=_("Gesamt-KM"))
    coins_total = models.IntegerField(default=0, verbose_name=_("Gesamt-Coins"))

    logo = models.ImageField(
        upload_to='group_logos/',
        null=True, blank=True,
        verbose_name=_("Logo für Karte")
    )

    def save(self, *args, **kwargs):
        # First save normally so the file exists on disk
        super().save(*args, **kwargs)

        if self.logo:
            self._process_image(self.logo.path, (400, 400))

    def _process_image(self, path, size):
        img = Image.open(path)
        # If the image is larger than allowed or not square
        if img.height > size[0] or img.width > size[1]:
            # thumbnail() preserves aspect ratio
            img.thumbnail(size, Image.Resampling.LANCZOS)
            img.save(path, quality=85, optimize=True)

    parent = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='children', verbose_name=_("Übergeordnete Gruppe")
    )
    managers = models.ManyToManyField(User, related_name='managed_groups', blank=True, verbose_name=_("Manager"))
    comments = models.TextField(blank=True, null=True, verbose_name=_("Interne Kommentare (Admin)"))

    class Meta:
        unique_together = ('group_type', 'name')
        verbose_name = _("Group")
        verbose_name_plural = _("Groups")
        indexes = [
            models.Index(fields=['group_type', 'name']),
        ]

    def __str__(self):
        if self.name:
            if self.group_type:
                return f"{self.group_type.name}: {self.name}"
            return self.name
        return f"Gruppe #{self.pk}" if self.pk else "Neue Gruppe"

    def add_to_totals(self, delta_km, delta_coins):
        # Convert delta_km to Decimal if it's not already
        if not isinstance(delta_km, Decimal):
            delta_km = Decimal(str(delta_km))
        if delta_km == 0 and delta_coins == 0: return
        Group.objects.filter(pk=self.pk).update(
            distance_total=models.F('distance_total') + delta_km,
            coins_total=models.F('coins_total') + delta_coins
        )
        if self.parent:
            self.parent.add_to_totals(delta_km, delta_coins)

    is_visible = models.BooleanField(default=True, verbose_name=_("In Map/Game anzeigen"))
    
    short_name = models.CharField(
        max_length=15,
        blank=True,
        null=True,
        verbose_name=_("Kurzname (z.B. 1a)"),
        help_text=_("Wird auf den Kiosk-Kacheln verwendet")
    )
    
    color = models.CharField(
        max_length=7,
        blank=True,
        null=True,
        verbose_name=_("Farbe (Hex-Code)"),
        help_text=_("Hex-Farbcode (z.B. #3b82f6) für die Darstellung im Kiosk-Leaderboard. Wird für alle Untergruppen verwendet. "
                   "Farbwähler: <a href='https://htmlcolorcodes.com/color-picker/' target='_blank'>HTML Color Codes</a> | "
                   "<a href='https://colorpicker.me/' target='_blank'>Color Picker</a> | "
                   "<a href='https://coolors.co/' target='_blank'>Coolors</a>")
    )

    def recalculate_totals(self):
        """Recalculates the kilometers of this group based on its members or subgroups."""
        # 1. Sum of direct members (participants)
        from django.db.models import Sum
        member_total = self.members.aggregate(total=Sum('distance_total'))['total'] or Decimal('0.00000')

        # 2. Sum of subgroups
        child_total = Decimal('0.00000')
        for child in self.children.all():
            child.recalculate_totals()  # Recursively downward
            child_total += child.distance_total

        # 3. Save the consolidated sum
        self.distance_total = member_total + child_total
        Group.objects.filter(pk=self.pk).update(distance_total=self.distance_total)
    
    def get_kiosk_label(self) -> str:
        """Returns the short name if present, otherwise the full name. Used for kiosk tiles."""
        # Check if short_name exists and is not empty (not None and not empty string)
        if self.short_name and self.short_name.strip():
            return self.short_name.strip()
        return self.name
    
    @property
    def top_parent_name(self) -> str:
        """Recursively finds the top-most parent group's name."""
        # Prevent infinite recursion by tracking visited groups
        visited = set()
        current = self
        while current and current.parent and current.id not in visited:
            visited.add(current.id)
            current = current.parent
        return current.name if current else self.name
    
    @property
    def school_name(self) -> str:
        """Deprecated: Use top_parent_name instead. Recursively finds the top-most parent group's name."""
        return self.top_parent_name
    
    def get_achieved_milestones(self, track=None):
        """
        Get all milestones achieved by this group.
        
        Args:
            track: Optional TravelTrack to filter by specific track.
        
        Returns:
            QuerySet of GroupMilestoneAchievement objects.
        """
        achievements = self.milestone_achievements.all()
        if track:
            achievements = achievements.filter(track=track)
        return achievements.select_related('milestone', 'track').order_by('-reached_at')
    
    def has_achieved_milestone(self, milestone):
        """
        Check if this group has achieved a specific milestone.
        
        Args:
            milestone: Milestone instance or milestone ID.
        
        Returns:
            bool: True if the milestone was achieved, False otherwise.
        """
        if isinstance(milestone, Milestone):
            milestone_id = milestone.id
        else:
            milestone_id = milestone
        return self.milestone_achievements.filter(milestone_id=milestone_id).exists()
    
    def get_achieved_milestones_count(self, track=None):
        """
        Get the count of milestones achieved by this group.
        
        Args:
            track: Optional TravelTrack to filter by specific track.
        
        Returns:
            int: Number of achieved milestones.
        """
        return self.get_achieved_milestones(track=track).count()
    
    def is_leaf_group(self):
        """
        Check if this group is a leaf group (smallest unit).
        
        A leaf group is a group that has no children (subgroups) or has direct members.
        This represents the smallest organizational unit (e.g., a class in a school).
        
        Returns:
            bool: True if this is a leaf group, False otherwise.
        """
        # A leaf group has no children OR has direct members
        return not self.children.exists() or self.members.exists()
    
    def get_leaf_groups(self):
        """
        Get all leaf groups (smallest units) that belong to this group hierarchy.
        
        Returns:
            QuerySet of Group objects that are leaf groups.
        """
        from django.db.models import Q
        # Get all descendant groups recursively
        def get_all_descendants(group_id, visited=None):
            if visited is None:
                visited = set()
            if group_id in visited:
                return set()
            visited.add(group_id)
            
            descendants = set()
            children = Group.objects.filter(parent_id=group_id, is_visible=True).values_list('id', flat=True)
            descendants.update(children)
            
            for child_id in children:
                descendants.update(get_all_descendants(child_id, visited))
            
            return descendants
        
        # Start with this group and all its descendants
        all_group_ids = {self.id}
        all_group_ids.update(get_all_descendants(self.id))
        
        # Filter to only leaf groups (no children or has members)
        leaf_groups = Group.objects.filter(
            id__in=all_group_ids,
            is_visible=True
        ).filter(
            Q(children__isnull=True) | Q(members__isnull=False)
        ).distinct()
        
        return leaf_groups

# --- CYCLIST ---
class Cyclist(models.Model):
    user_id = models.CharField(max_length=20, verbose_name=_("Symbolischer Name"))
    ##RRavatar = models.ImageField(upload_to='cyclist_avatars/', null=True, blank=True)
    avatar = models.ImageField(
        upload_to='cyclist_avatars/',
        null=True, blank=True,
        verbose_name=_("Radler Avatar")
    )
    id_tag = models.CharField(max_length=50, unique=True, verbose_name=_("RFID-UID"))
    mc_username = models.CharField(max_length=100, null=True, blank=True, verbose_name=_("Minecraft-Name"))

    distance_total = models.DecimalField(max_digits=15, decimal_places=5, default=Decimal('0.00000'), verbose_name=_("Gesamt-KM"))
    coins_total = models.IntegerField(default=0, verbose_name=_("Gesamt-Coins"))
    coins_spendable = models.IntegerField(default=0, verbose_name=_("Ausgebbare Coins"))
    coin_conversion_factor = models.FloatField(default=100.0, verbose_name=_("Coin-Faktor"))

    groups = models.ManyToManyField(Group, related_name='members', blank=True, verbose_name=_("Gruppen"))
    last_active = models.DateTimeField(null=True, blank=True, verbose_name=_("Zuletzt aktiv"))

    class Meta:
        verbose_name = _("Cyclist")
        verbose_name_plural = _("Cyclists")

    def __str__(self):
        return f"{self.user_id} ({self.id_tag})"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        if self.avatar:
            self._process_image(self.avatar.path, (200, 200))

    def _process_image(self, path, size):
        img = Image.open(path)
        if img.height > size[0] or img.width > size[1]:
            img.thumbnail(size, Image.Resampling.LANCZOS)
            img.save(path, quality=85, optimize=True)

    is_visible = models.BooleanField(default=True, verbose_name=_("In Map/Game anzeigen"))
    is_km_collection_enabled = models.BooleanField(default=True, verbose_name=_("Kilometer-Erfassung aktiv"), help_text=_("Wenn deaktiviert, werden keine Kilometer für diesen Radler erfasst"))

# --- DEVICE ---
# --- DEVICE moved to iot app ---
# --- HISTORY & SESSIONS ---
class HourlyMetric(models.Model):
    device = models.ForeignKey('iot.Device', on_delete=models.CASCADE, related_name='metrics', verbose_name=_("Gerät"))
    cyclist = models.ForeignKey(Cyclist, on_delete=models.SET_NULL, null=True, blank=True, related_name='metrics', verbose_name=_("Radler"))
    timestamp = models.DateTimeField(db_index=True, verbose_name=_("Zeitpunkt"))
    distance_km = models.DecimalField(max_digits=15, decimal_places=5, verbose_name=_("Intervall-Distanz (km)"))
    group_at_time = models.ForeignKey(Group, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("Gruppe"))
    last_session_start_time = models.DateTimeField(null=True, blank=True, verbose_name=_("Letzte Session Startzeit"), 
                                                   help_text=_("Startzeit der zuletzt verarbeiteten Session für diese Stunde. Wird verwendet, um zu erkennen, ob eine Session bereits verarbeitet wurde."))
    last_session_distance_km = models.DecimalField(max_digits=15, decimal_places=5, null=True, blank=True, 
                                                   verbose_name=_("Letzte Session Distanz (km)"),
                                                   help_text=_("Distanz der zuletzt verarbeiteten Session für diese Stunde. Wird verwendet, um zu erkennen, ob eine Session gewachsen ist."))

    class Meta:
        verbose_name = _("Hourly Metric")
        verbose_name_plural = _("Hourly Metrics")

class CyclistDeviceCurrentMileage(models.Model):
    cyclist = models.OneToOneField(Cyclist, on_delete=models.CASCADE, primary_key=True, verbose_name=_("Radler"))
    device = models.ForeignKey('iot.Device', on_delete=models.CASCADE, verbose_name=_("Gerät"))
    cumulative_mileage = models.DecimalField(max_digits=15, decimal_places=5, default=Decimal('0.00000'), verbose_name=_("Sitzungs-Distanz (km)"))
    start_time = models.DateTimeField(default=timezone.now, verbose_name=_("Startzeit"))
    last_activity = models.DateTimeField(auto_now=True)  # Updates on every save()

    class Meta:
        verbose_name = _("Cyclist - Active Session")
        verbose_name_plural = _("Cyclists - Active Sessions")

# --- TRAVEL SYSTEM ---
class TravelTrack(models.Model):
    name = models.CharField(max_length=100, verbose_name=_("Name der Route"))
    track_file = models.FileField(upload_to='tracks/', null=True, blank=True, verbose_name=_("GPX-Datei"))
    geojson_data = models.TextField(blank=True, verbose_name=_("GeoJSON Daten"))
    total_length_km = models.DecimalField(max_digits=15, decimal_places=5, default=Decimal('0.00000'), verbose_name=_("Gesamtlänge (km)"))
    is_active = models.BooleanField(default=True, verbose_name=_("Aktiv"))
    is_visible_on_map = models.BooleanField(default=True, verbose_name=_("Auf Karte anzeigen"))
    auto_start = models.BooleanField(
        default=False,
        verbose_name=_("Automatischer Start"),
        help_text=_("Wenn aktiviert, startet die Reise automatisch beim Eintreffen der ersten Kilometer. "
                    "Wenn deaktiviert, muss eine Startzeit definiert werden.")
    )
    start_time = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Startzeitpunkt"),
        help_text=_("Optional: Definiert den Startzeitpunkt der Reise. Wird ignoriert, wenn 'Automatischer Start' aktiviert ist.")
    )
    end_time = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Endzeitpunkt"),
        help_text=_("Optional: Definiert den Endzeitpunkt der Reise. Wenn nicht gesetzt, läuft die Reise unbegrenzt.")
    )
    assigned_to_group = models.ForeignKey(
        'Group',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_travel_tracks',
        verbose_name=_("Zugewiesene TOP-Gruppe"),
        help_text=_("TOP-Gruppe, der diese Reiseroute zugewiesen ist. "
                   "Operatoren dieser TOP-Gruppe können die Route verwalten. "
                   "Kann vom System-Admin gesetzt werden, bevor GroupTravelStatus Einträge erstellt werden.")
    )

    class Meta:
        verbose_name = _("Travels - Route")
        verbose_name_plural = _("Travels - Routes")

    def __str__(self):
        return self.name

    def is_currently_active(self):
        """
        Check if the trip is currently active based on start_time and end_time.
        
        If auto_start is enabled, the trip is active if:
        - No end_time is set, OR
        - end_time is in the future
        
        If auto_start is disabled, the trip is active if:
        - start_time is set and in the past (or not set), AND
        - end_time is not set or in the future
        """
        now = timezone.now()
        
        if self.auto_start:
            # Auto-start mode: trip is active if not ended yet
            if self.end_time and now > self.end_time:
                return False  # Already ended
            return True  # Active (will start automatically on first kilometer)
        else:
            # Manual start mode: check start_time and end_time
            if self.start_time and now < self.start_time:
                return False  # Not started yet
            if self.end_time and now > self.end_time:
                return False  # Already ended
            return True

    def restart_trip(self):
        """
        Reset all travel statuses and current milestone winners for this track.
        
        Note: This does NOT delete GroupMilestoneAchievement records, so groups
        keep their historical milestone achievements and rewards.
        
        If auto_start is enabled, start_time is reset to None so it can auto-start again.
        If auto_start is disabled, start_time is preserved (manual start time remains).
        """
        # Reset all group travel statuses
        GroupTravelStatus.objects.filter(track=self).update(
            current_travel_distance=Decimal('0.00000'),
            start_km_offset=Decimal('0.00000')
        )
        # Delete all leaf group travel contributions for this track
        # IMPORTANT: Delete instead of reset to 0, so they don't appear in the admin table after restart
        LeafGroupTravelContribution.objects.filter(track=self).delete()
        # Reset goal_reached_at for all groups on this track
        GroupTravelStatus.objects.filter(track=self).update(
            goal_reached_at=None
        )
        # Reset current milestone winners (for the current trip)
        # Historical achievements in GroupMilestoneAchievement are preserved
        Milestone.objects.filter(track=self).update(
            winner_group=None,
            reached_at=None
        )
        
        # If auto_start is enabled, reset start_time to None so it can auto-start again
        if self.auto_start:
            self.start_time = None
            self.save(update_fields=['start_time'])

class Milestone(models.Model):
    track = models.ForeignKey(TravelTrack, on_delete=models.CASCADE, related_name='milestones', verbose_name=_("Route"))
    name = models.CharField(max_length=100, verbose_name=_("Bezeichnung"))
    description = models.TextField(blank=True, null=True, verbose_name=_("Beschreibung"))
    external_link = models.URLField(blank=True, null=True, verbose_name=_("Info-Link"))
    reward_text = models.CharField(max_length=200, blank=True, null=True, verbose_name=_("Belohnung"))
    distance_km = models.DecimalField(max_digits=15, decimal_places=5, default=Decimal('0.00000'), verbose_name=_("KM-Marke"))
    gps_latitude = models.DecimalField(max_digits=8, decimal_places=6, verbose_name=_("Breitengrad"))
    gps_longitude = models.DecimalField(max_digits=9, decimal_places=6, verbose_name=_("Längengrad"))
    winner_group = models.ForeignKey(Group, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("Gewinner"))
    reached_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Erreicht am"))
    assigned_to_group = models.ForeignKey(
        'Group',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_milestones',
        verbose_name=_("Zugewiesene TOP-Gruppe"),
        help_text=_("TOP-Gruppe, der dieser Meilenstein zugewiesen ist. "
                   "Operatoren dieser TOP-Gruppe können den Meilenstein verwalten. "
                   "Kann vom System-Admin gesetzt werden. Falls nicht gesetzt, wird die Zugehörigkeit über die Route bestimmt.")
    )

    class Meta:
        ordering = ['distance_km']
        verbose_name = _("Travels - Milestone")
        verbose_name_plural = _("Travels - Milestones")

    def __str__(self):
        """Return only the name to avoid duplicate display in admin inline tables."""
        return self.name


class GroupMilestoneAchievement(models.Model):
    """
    Persistent storage of milestone achievements per group.
    
    This model stores historical milestone achievements that persist even after
    a track is reset. This allows groups to keep their milestone rewards.
    
    The reward_text is stored at the time of achievement, so it remains unchanged
    even if the milestone's reward is later modified.
    """
    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name='milestone_achievements',
        verbose_name=_("Gruppe")
    )
    milestone = models.ForeignKey(
        Milestone,
        on_delete=models.CASCADE,
        related_name='achievements',
        verbose_name=_("Meilenstein")
    )
    track = models.ForeignKey(
        TravelTrack,
        on_delete=models.CASCADE,
        related_name='milestone_achievements',
        verbose_name=_("Route")
    )
    reached_at = models.DateTimeField(
        verbose_name=_("Erreicht am")
    )
    # Store the distance at which the milestone was reached (for historical reference)
    reached_distance = models.DecimalField(
        max_digits=15,
        decimal_places=5,
        null=True,
        blank=True,
        verbose_name=_("Erreichte Distanz (km)")
    )
    # Store the reward text at the time of achievement (persistent, even if milestone reward changes)
    reward_text = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        verbose_name=_("Belohnung"),
        help_text=_("Die Belohnung, die zum Zeitpunkt des Erreichens des Meilensteins definiert war. "
                   "Diese bleibt unverändert, auch wenn die Meilenstein-Belohnung später geändert wird.")
    )
    # Track if the reward has been redeemed (can only be redeemed once)
    is_redeemed = models.BooleanField(
        default=False,
        verbose_name=_("Eingelöst"),
        help_text=_("Gibt an, ob die Belohnung bereits eingelöst wurde. Eine Belohnung kann nur einmal eingelöst werden.")
    )
    redeemed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Eingelöst am"),
        help_text=_("Zeitpunkt, zu dem die Belohnung eingelöst wurde.")
    )

    class Meta:
        ordering = ['-reached_at']
        verbose_name = _("Reisen - erreichte Meilensteine")
        verbose_name_plural = _("Reisen - erreichte Meilensteine")
        # Prevent duplicate achievements (same group, same milestone)
        unique_together = [['group', 'milestone']]
        indexes = [
            models.Index(fields=['group', 'reached_at']),
            models.Index(fields=['track', 'reached_at']),
            models.Index(fields=['group', 'is_redeemed']),
        ]

    def __str__(self):
        return f"{self.group.name} - {self.milestone.name} ({self.reached_at})"


class GroupTravelStatus(models.Model):
    # A group always has only ONE status (OneToOne),
    # but this status can point to any track (ForeignKey).
    group = models.OneToOneField(
        Group,
        on_delete=models.CASCADE,
        related_name='travel_status',
        verbose_name=_("Gruppe")
    )
    # IMPORTANT: ForeignKey allows multiple group statuses to point to the same track
    track = models.ForeignKey(
        TravelTrack,
        on_delete=models.CASCADE,
        related_name='group_statuses',
        verbose_name=_("Reisen-Track")
    )
    current_travel_distance = models.DecimalField(
        max_digits=15,
        decimal_places=5,
        default=Decimal('0.00000'),
        verbose_name=_("Aktuelle Reisen-Distanz (km)")
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
        help_text=_("Zeitpunkt, zu dem die Gruppe das Ziel erreicht hat. Wird für die Sortierung am Ziel verwendet.")
    )

    class Meta:
        verbose_name = _("Travels - Status")
        verbose_name_plural = _("Travels - Status")

    def save(self, *args, **kwargs):
        """
        Override save to reset current_travel_distance when group is assigned to a track.
        
        When a group is assigned to a track (new or changed), reset the travel distance
        to zero so all groups start at the same point.
        
        Note: If the group has existing travel kilometers, the save should be prevented
        and handled via the admin confirmation view instead.
        """
        # Store if this is a new object (before save)
        is_new = self.pk is None
        
        # Check if this is a new object or if the track has changed
        if self.pk:
            # Existing object - check if track changed
            try:
                old_instance = GroupTravelStatus.objects.get(pk=self.pk)
                if old_instance.track_id != self.track_id:
                    # Track changed - check if group has existing kilometers
                    # This should be handled via admin confirmation, but as fallback reset to zero
                    # The admin formset will prevent this via validation
                    self.current_travel_distance = Decimal('0.00000')
                    self.start_km_offset = Decimal('0.00000')
            except GroupTravelStatus.DoesNotExist:
                # Object was deleted, treat as new
                is_new = True
                self.current_travel_distance = Decimal('0.00000')
                self.start_km_offset = Decimal('0.00000')
        else:
            # New object - ensure distance starts at zero
            self.current_travel_distance = Decimal('0.00000')
            self.start_km_offset = Decimal('0.00000')
        
        super().save(*args, **kwargs)
        
        # Store flag for signal handler
        self._was_new = is_new

    def __str__(self):
        """Returns a readable string representation of the travel status."""
        # Return empty string to avoid duplicate display in TabularInline
        # The group field will display the group name
        return ""


class LeafGroupTravelContribution(models.Model):
    """
    Tracks the travel distance contribution of each leaf group during a trip.
    
    This model allows tracking which leaf group (e.g., class) contributed the most
    kilometers to a parent group's (e.g., school) trip. This is used for:
    - Milestone assignment: The leaf group with the highest contribution wins
    - Goal achievement: The leaf group with the highest contribution is displayed at the finish
    
    IMPORTANT: This is separate from GroupTravelStatus, which tracks the parent group's
    total travel distance. Leaf groups contribute to the parent's distance, but their
    individual contributions are tracked here.
    """
    leaf_group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name='travel_contributions',
        verbose_name=_("Leaf-Gruppe"),
        help_text=_("Die Leaf-Gruppe (z.B. Klasse), die Kilometer beiträgt")
    )
    track = models.ForeignKey(
        TravelTrack,
        on_delete=models.CASCADE,
        related_name='leaf_group_contributions',
        verbose_name=_("Reisen-Track")
    )
    current_travel_distance = models.DecimalField(
        max_digits=15,
        decimal_places=5,
        default=Decimal('0.00000'),
        verbose_name=_("Aktuelle Reise-Distanz (km)"),
        help_text=_("Die von dieser Leaf-Gruppe während der aktuellen Reise zurückgelegte Distanz")
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Aktualisiert am")
    )
    
    class Meta:
        verbose_name = _("Leaf-Gruppe Reise-Beitrag")
        verbose_name_plural = _("Leaf-Gruppe Reise-Beiträge")
        unique_together = [['leaf_group', 'track']]
        indexes = [
            models.Index(fields=['leaf_group', 'track']),
            models.Index(fields=['track', '-current_travel_distance']),  # For finding highest contributor
        ]
    
    def __str__(self):
        return f"{self.leaf_group.name} - {self.track.name}: {self.current_travel_distance} km"


# THIS FUNCTION MUST BE OUTSIDE THE CLASS:
class TravelHistory(models.Model):
    """Stores completed trips with collected kilometers per group."""
    ACTION_TYPES = [
        ('assigned', _("Zuordnung")),
        ('aborted', _("Abgebrochen")),
        ('completed', _("Beendet")),
        ('restarted', _("Neu gestartet")),
        ('removed', _("Entfernt")),
    ]
    
    track = models.ForeignKey(
        TravelTrack,
        on_delete=models.CASCADE,
        related_name='history_entries',
        verbose_name=_("Reisen - Route")
    )
    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name='travel_history',
        verbose_name=_("Gruppe")
    )
    start_time = models.DateTimeField(verbose_name=_("Startzeitpunkt"))
    end_time = models.DateTimeField(verbose_name=_("Endzeitpunkt"))
    total_distance_km = models.DecimalField(max_digits=15, decimal_places=5, default=Decimal('0.00000'), verbose_name=_("Gesammelte Kilometer"))
    action_type = models.CharField(
        max_length=20,
        choices=ACTION_TYPES,
        default='completed',
        verbose_name=_("Aktionstyp"),
        help_text=_("Art der Aktion, die zu diesem Historieeintrag geführt hat")
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Erstellt am"))

    class Meta:
        verbose_name = _("Travels - History")
        verbose_name_plural = _("Travels - Histories")
        ordering = ['-end_time']
        # Note: No unique_together constraint to allow multiple trips of the same track
        # with the same group (e.g., same route run multiple times with different groups or at different times)

    def __str__(self):
        action_display = dict(self.ACTION_TYPES).get(self.action_type, self.action_type)
        return f"{self.group.name} - {self.track.name} ({self.total_distance_km:.5f} km) - {action_display}"


# --- SIGNALS FOR TRAVEL HISTORY ---

@receiver(post_save, sender=GroupTravelStatus)
def create_travel_history_on_assignment(sender, instance, created, **kwargs):
    """
    Create a travel history entry when a group is assigned to a track.
    This records the start of a trip for the group.
    
    Note: Multiple trips of the same track with the same group are allowed,
    as a track can be run multiple times (e.g., with different groups or at different times).
    """
    if created:
        # New assignment - create history entry with action_type 'assigned'
        # Use current time for start_time to ensure uniqueness for multiple trips
        assignment_time = timezone.now()
        TravelHistory.objects.create(
            track=instance.track,
            group=instance.group,
            start_time=assignment_time,  # Use actual assignment time, not track.start_time
            end_time=assignment_time,  # Same as start for assignment
            total_distance_km=Decimal('0.00000'),  # No distance yet
            action_type='assigned'
        )


@receiver(pre_delete, sender=GroupTravelStatus)
def create_travel_history_on_removal(sender, instance, **kwargs):
    """
    Create a travel history entry when a group is removed from a track.
    This records the end/abort of a trip for the group.
    
    Note: Multiple trips of the same track with the same group are allowed,
    as a track can be run multiple times.
    """
    # Skip if history entry was already created explicitly (e.g., in admin actions)
    if hasattr(instance, '_skip_history_creation') and instance._skip_history_creation:
        return
    
    # Determine action type based on whether group has kilometers
    if instance.current_travel_distance and instance.current_travel_distance > 0:
        # Group has kilometers - this is an abort or removal
        action_type = 'aborted'
    else:
        # No kilometers - this is just a removal
        action_type = 'removed'
    
    # Find the most recent 'assigned' entry for this track/group to get the correct start_time
    # This ensures we link the end to the correct trip instance
    removal_time = timezone.now()
    assigned_entry = TravelHistory.objects.filter(
        track=instance.track,
        group=instance.group,
        action_type='assigned'
    ).order_by('-start_time').first()
    
    # Use the start_time from the assigned entry if found, otherwise use track.start_time or current time
    if assigned_entry:
        start_time = assigned_entry.start_time
    else:
        start_time = instance.track.start_time or removal_time
    
    # Create history entry
    TravelHistory.objects.create(
        track=instance.track,
        group=instance.group,
        start_time=start_time,
        end_time=removal_time,
        total_distance_km=instance.current_travel_distance or Decimal('0.00000'),
        action_type=action_type
    )


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
        Group,
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
        Group,
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
        Group,
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
        Group,
        on_delete=models.CASCADE,
        related_name='event_history',
        verbose_name=_("Gruppe")
    )
    start_time = models.DateTimeField(verbose_name=_("Startzeitpunkt"))
    end_time = models.DateTimeField(verbose_name=_("Endzeitpunkt"))
    total_distance_km = models.DecimalField(max_digits=15, decimal_places=5, default=Decimal('0.00000'), verbose_name=_("Gesammelte Kilometer"))
    best_leaf_group = models.ForeignKey(
        Group,
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


def update_group_hierarchy_progress(group, delta_km):
    """
    Adds the delta to the group's travel status and propagates
    upward through the hierarchy (recursively).
    Only updates if the group's track is currently active.
    Each group is checked individually - if a group has reached the goal,
    no more kilometers are added to its travel distance, but other groups
    can still collect kilometers.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # Convert delta_km to Decimal if it's not already
    if not isinstance(delta_km, Decimal):
        delta_km = Decimal(str(delta_km))
    
    if not group or delta_km <= 0:
        logger.debug(f"[update_group_hierarchy_progress] Skipping - group={group}, delta_km={delta_km}")
        return
    
    logger.info(f"[update_group_hierarchy_progress] Processing group '{group.name}' (ID: {group.id}) with delta_km={delta_km}")

    # Get the group's travel status (if exists)
    travel_status = None
    track = None
    should_update_travel_status = False
    
    try:
        travel_status = group.travel_status
        track = travel_status.track
        logger.debug(f"[update_group_hierarchy_progress] Group '{group.name}' has travel_status for track '{track.name}'")

        # Check if track is currently active (considering start_time and end_time)
        if track.is_currently_active():
            should_update_travel_status = True
            logger.debug(f"[update_group_hierarchy_progress] Track '{track.name}' is active - will update travel_status for group '{group.name}'")
            
            # Auto-start: If auto_start is enabled and start_time is not set, set it now (first kilometer)
            if track.auto_start and not track.start_time:
                now = timezone.now()
                track.start_time = now
                track.save(update_fields=['start_time'])
                logger.info(f"[update_group_hierarchy_progress] Auto-started track '{track.name}' at {now} (first kilometer received)")
        else:
            logger.debug(f"[update_group_hierarchy_progress] Track '{track.name}' is not currently active - will skip travel_status update for group '{group.name}', but still update distance_total")
    except GroupTravelStatus.DoesNotExist:
        # Group has no travel_status - this is normal, not all groups need to be assigned to a track
        logger.debug(f"[update_group_hierarchy_progress] Group '{group.name}' has no travel_status - will only update distance_total")

    # 1. Update GroupTravelStatus (for avatars on the map) - only if travel_status exists and track is active
    # IMPORTANT: Each group is checked individually - if THIS group has reached the goal,
    # don't add more kilometers to THIS group's travel distance
    if should_update_travel_status and travel_status:
        old_travel_distance = travel_status.current_travel_distance
        
        # Check if THIS group has already reached the goal (total_length_km)
        if track.total_length_km > 0 and old_travel_distance >= track.total_length_km:
            logger.debug(f"[update_group_hierarchy_progress] Group '{group.name}' has already reached the goal ({old_travel_distance:.5f} km >= {track.total_length_km:.5f} km) - not adding more kilometers to THIS group's travel distance")
            # Don't update current_travel_distance for THIS group if goal is already reached
            # But continue to propagate to parent groups (they might not have reached the goal)
        else:
            # Calculate new distance for THIS group
            new_travel_distance = old_travel_distance + delta_km
            
            # Cap at total_length_km if goal is reached with this update
            goal_reached = False
            # IMPORTANT: Check if goal is reached (>= total_length_km) and wasn't reached before
            if track.total_length_km > 0:
                if new_travel_distance >= track.total_length_km and old_travel_distance < track.total_length_km:
                    # Goal is reached for the first time with this update
                    logger.info(f"[update_group_hierarchy_progress] Group '{group.name}' reached the goal! Capping at {track.total_length_km:.5f} km (was {old_travel_distance:.5f} km, would be {new_travel_distance:.5f} km)")
                    new_travel_distance = track.total_length_km
                    goal_reached = True
                elif new_travel_distance > track.total_length_km:
                    # Goal was already reached, but new distance exceeds it - cap it
                    logger.debug(f"[update_group_hierarchy_progress] Group '{group.name}' already at goal, capping excess distance at {track.total_length_km:.5f} km")
                    new_travel_distance = track.total_length_km
            
            # Update travel status
            # IMPORTANT: If goal is reached for the first time, record the finish time
            update_fields = {'current_travel_distance': new_travel_distance}
            if goal_reached:
                # Goal was just reached - record finish time (only once, when first reaching the goal)
                update_fields['goal_reached_at'] = timezone.now()
                logger.info(f"[update_group_hierarchy_progress] Group '{group.name}' reached goal at {update_fields['goal_reached_at']}")
            
            GroupTravelStatus.objects.filter(group=group).update(**update_fields)
            travel_status.refresh_from_db()
            logger.debug(f"[update_group_hierarchy_progress] Updated GroupTravelStatus for '{group.name}' - old: {old_travel_distance}, new: {travel_status.current_travel_distance}")

    # 1.5. IMPORTANT: If this is a leaf group and parent has travel_status, update leaf group's travel contribution
    # This tracks which leaf group contributed the most kilometers during the trip
    # IMPORTANT: Don't update if parent group has already reached the goal
    if group.is_leaf_group() and group.parent:
        try:
            parent_travel_status = group.parent.travel_status
            parent_track = parent_travel_status.track
            parent_current_distance = parent_travel_status.current_travel_distance or Decimal('0.00000')
            
            # Only update if parent's track is active AND parent hasn't reached the goal yet
            if parent_track.is_currently_active():
                # Check if parent group has already reached the goal
                if parent_track.total_length_km > 0 and parent_current_distance >= parent_track.total_length_km:
                    logger.debug(f"[update_group_hierarchy_progress] Parent group '{group.parent.name}' has already reached the goal ({parent_current_distance:.5f} km >= {parent_track.total_length_km:.5f} km) - not updating LeafGroupTravelContribution for '{group.name}'")
                else:
                    # Get or create LeafGroupTravelContribution for this leaf group and track
                    contribution, created = LeafGroupTravelContribution.objects.get_or_create(
                        leaf_group=group,
                        track=parent_track,
                        defaults={'current_travel_distance': Decimal('0.00000')}
                    )
                    
                    # Update the contribution (add delta_km)
                    # IMPORTANT: Cap at parent's total_length_km to prevent exceeding track length
                    old_contribution = contribution.current_travel_distance
                    new_contribution = old_contribution + delta_km
                    
                    # Cap at parent track's total_length_km if goal is reached
                    if parent_track.total_length_km > 0 and new_contribution > parent_track.total_length_km:
                        new_contribution = parent_track.total_length_km
                        logger.debug(f"[update_group_hierarchy_progress] Capping LeafGroupTravelContribution for '{group.name}' at {parent_track.total_length_km:.5f} km (parent track goal)")
                    
                    LeafGroupTravelContribution.objects.filter(pk=contribution.pk).update(
                        current_travel_distance=new_contribution
                    )
                    contribution.refresh_from_db()
                    logger.debug(f"[update_group_hierarchy_progress] Updated LeafGroupTravelContribution for '{group.name}' on track '{parent_track.name}' - old: {old_contribution}, new: {contribution.current_travel_distance}")
        except (GroupTravelStatus.DoesNotExist, AttributeError):
            # Parent has no travel_status or no parent - skip leaf group contribution tracking
            pass
    
    # 2. Always update Group distance_total (for statistics/leaderboard) - regardless of travel_status or goal
    # This ensures total statistics continue to accumulate even after goal is reached
    old_group_distance = group.distance_total
    Group.objects.filter(pk=group.pk).update(
        distance_total=models.F('distance_total') + delta_km
    )
    group.refresh_from_db()
    logger.debug(f"[update_group_hierarchy_progress] Updated Group distance_total for '{group.name}' - old: {old_group_distance}, new: {group.distance_total}")

    # 2.5. IMPORTANT: Track leaf group contributions for events
    # This must be done BEFORE the event_statuses loop, because leaf groups might not have event_statuses themselves
    # Two scenarios:
    # 1. Leaf group is directly assigned to an event -> track its own contribution
    # 2. Leaf group's parent (TOP-group) is assigned to an event -> track contribution to parent's event
    if group.is_leaf_group():
        # Scenario 1: Leaf group directly participates in events
        leaf_event_statuses = group.event_statuses.select_related('event').all()
        if leaf_event_statuses.exists():
            logger.debug(f"[update_group_hierarchy_progress] Leaf group '{group.name}' directly participates in {leaf_event_statuses.count()} event(s)")
            for leaf_event_status in leaf_event_statuses:
                event = leaf_event_status.event
                if not event.is_currently_active():
                    continue
                
                # Track this leaf group's own contribution to the event
                # Check if leaf group has already reached the goal
                leaf_goal_reached = (
                    leaf_event_status.goal_reached_at is not None or
                    (event.target_distance_km and event.target_distance_km > 0 and leaf_event_status.current_distance_km >= event.target_distance_km)
                )
                
                if not leaf_goal_reached:
                    # Get or create LeafGroupEventContribution for this leaf group's direct participation
                    contribution, created = LeafGroupEventContribution.objects.get_or_create(
                        leaf_group=group,
                        event=event,
                        defaults={'current_event_distance': delta_km}
                    )
                    
                    if not created:
                        old_contribution = contribution.current_event_distance
                        new_contribution = old_contribution + delta_km
                        
                        # Cap at target_distance_km if goal is reached with this update
                        if event.target_distance_km and event.target_distance_km > 0:
                            if new_contribution >= event.target_distance_km and old_contribution < event.target_distance_km:
                                # Goal is reached for the first time - cap at target
                                new_contribution = event.target_distance_km
                                logger.debug(f"[update_group_hierarchy_progress] Leaf group '{group.name}' reached event goal in '{event.name}'! Capping contribution at {new_contribution:.5f} km")
                            elif new_contribution > event.target_distance_km:
                                # Goal was already reached, but new contribution exceeds it - cap it
                                new_contribution = event.target_distance_km
                                logger.debug(f"[update_group_hierarchy_progress] Leaf group '{group.name}' already at goal in event '{event.name}', capping excess contribution at {new_contribution:.5f} km")
                        
                        LeafGroupEventContribution.objects.filter(pk=contribution.pk).update(
                            current_event_distance=new_contribution
                        )
                        contribution.refresh_from_db()
                        logger.debug(f"[update_group_hierarchy_progress] Updated LeafGroupEventContribution for direct participation: '{group.name}' on event '{event.name}' - old: {old_contribution}, new: {contribution.current_event_distance}")
        
        # Scenario 2: Leaf group's parent (TOP-group) participates in events
        if group.parent:
            logger.debug(f"[update_group_hierarchy_progress] Leaf group '{group.name}' (parent: {group.parent.name}) - checking for parent event statuses")
            # Get all events where the parent group participates
            parent_event_statuses = GroupEventStatus.objects.filter(
                group=group.parent
            ).select_related('event')
            
            if parent_event_statuses.exists():
                logger.debug(f"[update_group_hierarchy_progress] Parent group '{group.parent.name}' has {parent_event_statuses.count()} event status(es) - will track leaf contributions")
                for parent_event_status in parent_event_statuses:
                    event = parent_event_status.event
                    logger.debug(f"[update_group_hierarchy_progress] Processing leaf contribution for event '{event.name}' (ID: {event.id})")
                    
                    # Check if event is currently active
                    if not event.is_currently_active():
                        logger.debug(f"[update_group_hierarchy_progress] Event '{event.name}' is not currently active - skipping leaf contribution tracking")
                        continue
                    
                    # Check if parent group has already reached the goal
                    parent_goal_reached = (
                        parent_event_status.goal_reached_at is not None or
                        (event.target_distance_km and event.target_distance_km > 0 and parent_event_status.current_distance_km >= event.target_distance_km)
                    )
                    logger.debug(f"[update_group_hierarchy_progress] Parent goal reached: {parent_goal_reached} (goal_reached_at: {parent_event_status.goal_reached_at}, current_distance: {parent_event_status.current_distance_km}, target: {event.target_distance_km})")
                    
                    # Always track leaf group contributions, even if parent has reached the goal
                    # This ensures we can always identify the best leaf group
                    # But if parent has reached the goal, don't add more kilometers to contributions
                    contribution, created = LeafGroupEventContribution.objects.get_or_create(
                        leaf_group=group,
                        event=event,
                        defaults={'current_event_distance': delta_km if not parent_goal_reached else Decimal('0.00000')}
                    )
                    
                    if created:
                        if not parent_goal_reached:
                            logger.debug(f"[update_group_hierarchy_progress] Created LeafGroupEventContribution for '{group.name}' on event '{event.name}' with {delta_km} km")
                        else:
                            logger.debug(f"[update_group_hierarchy_progress] Created LeafGroupEventContribution for '{group.name}' on event '{event.name}' with 0 km (parent goal already reached)")
                    else:
                        if not parent_goal_reached:
                            old_contribution = contribution.current_event_distance
                            new_contribution = old_contribution + delta_km
                            
                            # Note: Leaf contributions to parent's event are not capped at parent's target_distance_km
                            # because they contribute to the parent's total. The parent's current_distance_km will be capped separately above.
                            
                            LeafGroupEventContribution.objects.filter(pk=contribution.pk).update(
                                current_event_distance=new_contribution
                            )
                            contribution.refresh_from_db()
                            logger.debug(f"[update_group_hierarchy_progress] Updated LeafGroupEventContribution for '{group.name}' on event '{event.name}' - old: {old_contribution}, new: {contribution.current_event_distance}")
                        else:
                            logger.debug(f"[update_group_hierarchy_progress] Parent group '{group.parent.name}' has already reached the goal in event '{event.name}' - not updating LeafGroupEventContribution for '{group.name}'")
                    
                    # Update parent's best_leaf_group if this leaf group has the highest contribution
                    # Find the leaf group with the highest contribution for this parent and event
                    leaf_contributions = LeafGroupEventContribution.objects.filter(
                        leaf_group__parent=group.parent,
                        event=event
                    ).select_related('leaf_group').order_by('-current_event_distance')
                    
                    logger.debug(f"[update_group_hierarchy_progress] Found {leaf_contributions.count()} leaf contributions for parent '{group.parent.name}' in event '{event.name}'")
                    
                    if leaf_contributions.exists():
                        best_contribution = leaf_contributions.first()
                        logger.debug(f"[update_group_hierarchy_progress] Best contribution: {best_contribution.leaf_group.name} with {best_contribution.current_event_distance} km")
                        # Always update parent's best_leaf_group to the current best (even if it hasn't changed)
                        # This ensures best_leaf_group is set even if it was None before
                        parent_update_fields = {'best_leaf_group': best_contribution.leaf_group}
                        
                        # If the best leaf group just reached the goal, record its time
                        # Check if this leaf group is the best AND parent just reached the goal
                        if parent_goal_reached and best_contribution.leaf_group == group and not parent_event_status.best_leaf_group_goal_reached_at:
                            parent_update_fields['best_leaf_group_goal_reached_at'] = timezone.now()
                            logger.debug(f"[update_group_hierarchy_progress] Best leaf group '{group.name}' reached event goal at {parent_update_fields['best_leaf_group_goal_reached_at']}")
                        
                        # Update best_leaf_group (always, to ensure it's set)
                        GroupEventStatus.objects.filter(pk=parent_event_status.pk).update(**parent_update_fields)
                        parent_event_status.refresh_from_db()
                        if parent_event_status.best_leaf_group != best_contribution.leaf_group:
                            logger.debug(f"[update_group_hierarchy_progress] Updated best_leaf_group for '{group.parent.name}' in event '{event.name}' to '{best_contribution.leaf_group.name}'")
                        else:
                            logger.debug(f"[update_group_hierarchy_progress] Best leaf group for '{group.parent.name}' in event '{event.name}' is already '{best_contribution.leaf_group.name}'")
                    else:
                        logger.debug(f"[update_group_hierarchy_progress] No leaf contributions found for parent '{group.parent.name}' in event '{event.name}' - cannot set best_leaf_group")
            else:
                logger.debug(f"[update_group_hierarchy_progress] Parent group '{group.parent.name}' has no event statuses - skipping leaf contribution tracking")
    
    # 2.6. Update Event statuses for active events
    # Get all event statuses for this group
    event_statuses = group.event_statuses.select_related('event').all()
    if not event_statuses.exists():
        logger.debug(f"[update_group_hierarchy_progress] Group '{group.name}' has no event statuses - skipping event updates")
    else:
        logger.info(f"[update_group_hierarchy_progress] Group '{group.name}' has {event_statuses.count()} event status(es) - checking for updates")
    
    for event_status in event_statuses:
        # Refresh event from database to ensure we have the latest is_active status
        event_status.event.refresh_from_db()
        event = event_status.event
        logger.info(f"[update_group_hierarchy_progress] Checking event '{event.name}' (ID: {event.id}) for group '{group.name}': is_active={event.is_active}, is_currently_active()={event.is_currently_active()}")
        
        if event.is_currently_active():
            old_event_distance = event_status.current_distance_km
            
            # Check if group has already reached the goal - if so, don't add more kilometers
            goal_already_reached = (
                event_status.goal_reached_at is not None or
                (event.target_distance_km and event.target_distance_km > 0 and old_event_distance >= event.target_distance_km)
            )
            
            if goal_already_reached:
                logger.debug(f"[update_group_hierarchy_progress] Group '{group.name}' has already reached the goal in event '{event.name}' ({old_event_distance:.5f} km >= {event.target_distance_km:.5f} km) - skipping update")
                # Skip adding kilometers, but continue with leaf group tracking (if applicable)
                new_event_distance = old_event_distance
                goal_reached = False
            else:
                new_event_distance = old_event_distance + delta_km
                
                # Check if group reached the event goal (target_distance_km) for the first time
                goal_reached = False
                if event.target_distance_km and event.target_distance_km > 0:
                    if new_event_distance >= event.target_distance_km and old_event_distance < event.target_distance_km:
                        # Goal is reached for the first time with this update
                        goal_reached = True
                        # Cap at target_distance_km to ensure all groups that reach the goal have the same final distance
                        new_event_distance = event.target_distance_km
                        logger.info(f"[update_group_hierarchy_progress] 🎉 Group '{group.name}' reached event goal in '{event.name}'! Capping at {new_event_distance:.5f} km (target: {event.target_distance_km:.5f} km)")
                    elif new_event_distance > event.target_distance_km:
                        # Goal was already reached, but new distance exceeds it - cap it
                        new_event_distance = event.target_distance_km
                        logger.debug(f"[update_group_hierarchy_progress] Group '{group.name}' already at goal in event '{event.name}', capping excess distance at {new_event_distance:.5f} km")
                
                # Update event distance using F() expression for atomic update
                update_fields = {'current_distance_km': new_event_distance}
                if goal_reached and not event_status.goal_reached_at:
                    # Goal was just reached for the first time - record finish time
                    update_fields['goal_reached_at'] = timezone.now()
                    logger.info(f"[update_group_hierarchy_progress] Group '{group.name}' reached event goal at {update_fields['goal_reached_at']}")
                
                GroupEventStatus.objects.filter(pk=event_status.pk).update(**update_fields)
                event_status.refresh_from_db()
                logger.info(f"[update_group_hierarchy_progress] ✅ Updated GroupEventStatus for '{group.name}' in event '{event.name}' - old: {old_event_distance}, new: {event_status.current_distance_km}")
            
            # Note: Leaf group contribution tracking is now done BEFORE the event_statuses loop (section 2.5)
            # This ensures it works even if the leaf group itself has no event_statuses
            
            # 2.7. IMPORTANT: If this is a TOP group (not a leaf group) that has leaf groups, 
            # update best_leaf_group based on existing contributions (if any)
            # This handles the case where the TOP group collects kilometers directly
            # but we still want to track which leaf group contributed the most
            if not group.is_leaf_group() and event_status:
                # Check if this group has leaf groups
                leaf_groups = group.get_leaf_groups()
                if leaf_groups.exists():
                    # Find the leaf group with the highest contribution for this group and event
                    leaf_contributions = LeafGroupEventContribution.objects.filter(
                        leaf_group__parent=group,
                        event=event
                    ).select_related('leaf_group').order_by('-current_event_distance')
                    
                    if leaf_contributions.exists():
                        best_contribution = leaf_contributions.first()
                        # Update best_leaf_group if it's not set or if it changed
                        if event_status.best_leaf_group != best_contribution.leaf_group:
                            update_fields = {'best_leaf_group': best_contribution.leaf_group}
                            GroupEventStatus.objects.filter(pk=event_status.pk).update(**update_fields)
                            event_status.refresh_from_db()
                            logger.info(f"[update_group_hierarchy_progress] Updated best_leaf_group for '{group.name}' in event '{event.name}' to '{best_contribution.leaf_group.name}'")
        else:
            logger.warning(f"[update_group_hierarchy_progress] ⚠️ Event '{event.name}' is not currently active (is_active={event.is_active}, start_time={event.start_time}, end_time={event.end_time}) - will skip event_status update for group '{group.name}'")

    # 3. RECURSION: Also update parent group
    # IMPORTANT: Propagate to parent even if THIS group reached the goal,
    # because the parent group might not have reached the goal yet
    if group.parent:
        logger.debug(f"[update_group_hierarchy_progress] Propagating to parent group '{group.parent.name}'")
        update_group_hierarchy_progress(group.parent, delta_km)


# --- KIOSK MANAGEMENT ---
# --- KIOSK DEVICE moved to kiosk app ---

# --- KIOSK PLAYLIST moved to kiosk app ---

# --- DEVICE MANAGEMENT & CONFIGURATION ---

# --- DEVICE MANAGEMENT moved to iot app ---
