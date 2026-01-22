# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    admin.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
from django.contrib import admin
from django.contrib.auth import get_user_model
from django import forms
from django.utils.safestring import mark_safe
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from api.models import (
    Cyclist, Group, GroupType, HourlyMetric, TravelTrack, Milestone, GroupTravelStatus, 
    CyclistDeviceCurrentMileage, TravelHistory, Event, GroupEventStatus, EventHistory,
    GroupMilestoneAchievement, MapPopupSettings, LeafGroupTravelContribution
)
from iot.models import (
    Device, DeviceConfiguration, DeviceConfigurationReport, DeviceConfigurationDiff,
    FirmwareImage, DeviceManagementSettings, DeviceHealth, ConfigTemplate,
    DeviceAuditLog, WebhookConfiguration
)
from kiosk.models import KioskDevice, KioskPlaylistEntry
from django.urls import reverse
from django.db import models
from django.db.utils import OperationalError
from django.db import transaction
from zoneinfo import ZoneInfo
from decimal import Decimal
import gpxpy
import json
import time
import logging

logger = logging.getLogger(__name__)

User = get_user_model()

# --- 1. HELPER FUNCTIONS ---

def format_km_de(value):
    """Formats numbers to exactly two decimal places: 1.234,56 km"""
    if value is None: return "0,00 km"
    formatted = f"{float(value):,.2f}"
    return formatted.replace(',', '[TEMP]').replace('.', ',').replace('[TEMP]', '.') + " km"

class GroupTravelStatusInline(admin.TabularInline):
    """Displays all groups traveling on this track"""
    model = GroupTravelStatus
    extra = 1
    verbose_name = _("Teilnehmende Gruppe")
    verbose_name_plural = _("Teilnehmende Gruppen")
    fields = ('group', 'current_travel_distance_display', 'abort_trip_action')
    readonly_fields = ('current_travel_distance_display', 'abort_trip_action')

    def current_travel_distance_display(self, obj):
        """Display current_travel_distance with German format (comma decimal)."""
        if obj and obj.current_travel_distance is not None:
            return format_km_de(obj.current_travel_distance)
        return format_km_de(0)
    current_travel_distance_display.short_description = _("Aktuelle Reise-Distanz (km)")
    
    def abort_trip_action(self, obj):
        """Display abort trip button if group has travel kilometers or is already assigned to a track."""
        from django.urls import reverse
        
        # Check if this is a saved object with kilometers
        if obj and obj.pk:
            if obj.current_travel_distance and obj.current_travel_distance > 0:
                abort_url = reverse('admin:api_grouptravelstatus_abort_trip', args=[obj.pk])
                return mark_safe(
                    f'<a href="{abort_url}" class="button" '
                    f'onclick="return confirm(\'{_("Möchten Sie die Reise für diese Gruppe wirklich abbrechen? Die aktuellen Reisekilometer ({}) gehen verloren.").format(format_km_de(obj.current_travel_distance))}\');">'
                    f'{_("Reise abbrechen")}</a>'
                )
        
        # For new forms, return a placeholder that JavaScript can populate
        # This will be shown when a group with existing travel status is selected
        return mark_safe('<span class="abort-trip-placeholder" style="display: none;"></span>')
    abort_trip_action.short_description = _("Aktionen")
    
    def get_formset(self, request, obj=None, **kwargs):
        """Customize formset to prevent accidental removal of groups with kilometers."""
        from django.forms import BaseInlineFormSet
        from api.models import GroupTravelStatus
        
        formset = super().get_formset(request, obj, **kwargs)
        
        class GroupTravelStatusFormSet(formset):
            def clean(self):
                """Validate that groups with existing kilometers are not accidentally removed."""
                super().clean()
                
                for form in self.forms:
                    # Check if form is marked for deletion
                    if form in self.deleted_forms and form.instance.pk:
                        if form.instance.current_travel_distance and form.instance.current_travel_distance > 0:
                            from django.forms import ValidationError
                            raise ValidationError(
                                _("Die Gruppe '{}' hat bereits {} Reisekilometer. "
                                  "Bitte verwenden Sie die 'Reise abbrechen'-Funktion, um die Gruppe von der Reise zu entfernen.").format(
                                    form.instance.group.name,
                                    format_km_de(form.instance.current_travel_distance)
                                )
                            )
        
        return GroupTravelStatusFormSet
    
    class Media:
        js = ('admin/js/grouptravelstatus_inline.js',)

class LeafGroupTravelContributionInline(admin.TabularInline):
    """
    Displays all leaf groups contributing to parent groups on this track.
    Shows a ranking of leaf groups by their travel contribution.
    """
    model = LeafGroupTravelContribution
    extra = 0
    verbose_name = _("Leaf-Gruppe Beitrag")
    verbose_name_plural = _("Leaf-Gruppen Beiträge (Ranking)")
    fields = ('rank_display', 'leaf_group', 'parent_group_display', 'current_travel_distance_display', 'percentage_display')
    readonly_fields = ('rank_display', 'leaf_group', 'parent_group_display', 'current_travel_distance_display', 'percentage_display')
    can_delete = False  # Prevent deletion of contributions
    can_add = False  # Contributions are created automatically
    
    def get_queryset(self, request):
        """
        Order by contribution distance descending (highest first).
        The inline automatically filters by track (parent object).
        """
        qs = super().get_queryset(request)
        return qs.select_related('leaf_group', 'leaf_group__parent', 'track').order_by('-current_travel_distance', 'leaf_group__name')
    
    def rank_display(self, obj):
        """Display the rank of this leaf group based on contribution."""
        if not obj or not obj.track:
            return "-"
        
        # Get all contributions for this track, ordered by distance descending
        contributions = LeafGroupTravelContribution.objects.filter(
            track=obj.track
        ).order_by('-current_travel_distance', 'leaf_group__name')
        
        # Find the rank (1-based index)
        rank = 1
        for idx, contrib in enumerate(contributions, start=1):
            if contrib.pk == obj.pk:
                rank = idx
                break
        
        # Add medal emoji for top 3
        if rank == 1:
            return mark_safe(f'🥇 {rank}')
        elif rank == 2:
            return mark_safe(f'🥈 {rank}')
        elif rank == 3:
            return mark_safe(f'🥉 {rank}')
        else:
            return str(rank)
    rank_display.short_description = _("Rang")
    
    def parent_group_display(self, obj):
        """Display the parent group of this leaf group."""
        if obj and obj.leaf_group and obj.leaf_group.parent:
            return obj.leaf_group.parent.name
        return "-"
    parent_group_display.short_description = _("Parent-Gruppe")
    parent_group_display.admin_order_field = 'leaf_group__parent__name'
    
    def current_travel_distance_display(self, obj):
        """Display current_travel_distance with German format (comma decimal)."""
        if obj and obj.current_travel_distance is not None:
            # IMPORTANT: Cap at track total_length_km for consistency with avatar display
            distance_km = obj.current_travel_distance
            if obj.track and obj.track.total_length_km and distance_km > obj.track.total_length_km:
                distance_km = obj.track.total_length_km
            return format_km_de(distance_km)
        return format_km_de(0)
    current_travel_distance_display.short_description = _("Beitrag (km)")
    current_travel_distance_display.admin_order_field = 'current_travel_distance'
    
    def percentage_display(self, obj):
        """Display the percentage contribution relative to parent group's total distance."""
        if not obj or not obj.leaf_group or not obj.leaf_group.parent:
            return "-"
        
        try:
            parent_status = obj.leaf_group.parent.travel_status
            if parent_status and parent_status.track_id == obj.track_id:
                parent_distance = parent_status.current_travel_distance or Decimal('0.00000')
                if parent_distance > 0:
                    percentage = (obj.current_travel_distance / parent_distance) * 100
                    return f"{percentage:.1f}%"
                else:
                    return "0,0%"
        except GroupTravelStatus.DoesNotExist:
            pass
        
        return "-"
    percentage_display.short_description = _("Anteil")
    
    def has_add_permission(self, request, obj=None):
        """Contributions are created automatically, no manual addition."""
        return False
    
    def has_delete_permission(self, request, obj=None):
        """Contributions are managed automatically, no manual deletion."""
        return False

class GroupMilestoneAchievementInline(admin.TabularInline):
    """Displays all milestone achievements for this group."""
    model = GroupMilestoneAchievement
    extra = 0
    verbose_name = _("Erreichter Meilenstein")
    verbose_name_plural = _("Erreichte Meilensteine")
    fields = ('milestone', 'track', 'reached_at', 'reached_distance_display', 'reward_text', 'is_redeemed', 'redeemed_at')
    readonly_fields = ('milestone', 'track', 'reached_at', 'reached_distance_display', 'reward_text', 'is_redeemed', 'redeemed_at')
    can_delete = False  # Prevent deletion of historical achievements
    
    def reached_distance_display(self, obj):
        """Display reached_distance with German format (comma decimal)."""
        if obj and obj.reached_distance is not None:
            return format_km_de(obj.reached_distance)
        return format_km_de(0)
    reached_distance_display.short_description = _("Erreichte Distanz (km)")
    
    def get_queryset(self, request):
        """Order achievements by reached_at descending (most recent first)."""
        qs = super().get_queryset(request)
        return qs.select_related('milestone', 'track').order_by('-reached_at')

class MilestoneInline(admin.TabularInline):
    model = Milestone
    extra = 1
    fields = ('name', 'distance_km', 'gps_latitude', 'gps_longitude', 'reward_text', 'description', 'external_link', 'winner_group', 'reached_at')
    readonly_fields = ('reached_at', 'winner_group')
    can_delete = True

    template = 'admin/api/milestone_inline.html'

    def get_extra(self, request, obj=None, **kwargs):
        return 1

    def get_queryset(self, request):
        """Exclude start milestones (distance_km = 0) from the table."""
        qs = super().get_queryset(request)
        return qs.exclude(distance_km=0)
    
    def get_formset(self, request, obj=None, **kwargs):
        """Customize formset to make GPS and distance fields readonly and add milestone data."""
        formset = super().get_formset(request, obj, **kwargs)
        
        # Customize formset to make GPS and distance fields readonly
        class MilestoneFormSet(formset):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                # Make distance_km, gps_latitude, and gps_longitude readonly
                # They can only be set by clicking on the map, not by manual editing
                for form in self.forms:
                    if 'distance_km' in form.fields:
                        form.fields['distance_km'].widget.attrs['readonly'] = True
                        form.fields['distance_km'].widget.attrs['class'] = 'readonly-field'
                    if 'gps_latitude' in form.fields:
                        form.fields['gps_latitude'].widget.attrs['readonly'] = True
                        form.fields['gps_latitude'].widget.attrs['class'] = 'readonly-field'
                    if 'gps_longitude' in form.fields:
                        form.fields['gps_longitude'].widget.attrs['readonly'] = True
                        form.fields['gps_longitude'].widget.attrs['class'] = 'readonly-field'
                    # Limit description field to 500 characters
                    if 'description' in form.fields:
                        form.fields['description'].widget.attrs['maxlength'] = '500'
                        form.fields['description'].widget.attrs['rows'] = '3'
                        form.fields['description'].widget.attrs['style'] = 'max-width: 100%;'
        
        # Add milestone data to the formset (including start point for map display)
        if obj and obj.pk:
            milestones_data = []
            for milestone in obj.milestones.all():
                if milestone.gps_latitude and milestone.gps_longitude:
                    milestones_data.append({
                        'name': milestone.name,
                        'lat': float(milestone.gps_latitude),
                        'lon': float(milestone.gps_longitude),
                        'distance': float(milestone.distance_km),
                        'text': milestone.reward_text or ''
                    })
            MilestoneFormSet.milestones_json = json.dumps(milestones_data)
        else:
            MilestoneFormSet.milestones_json = '[]'
        return MilestoneFormSet

# --- 2. RETRY MIXIN FOR ADMIN OPERATIONS ---

class RetryOnDbLockMixin:
    """
    Mixin for Admin classes to automatically retry database operations on 'database is locked' errors.
    """
    MAX_RETRIES = 10
    BASE_DELAY = 0.05
    MAX_DELAY = 5.0

    def _retry_db_operation(self, operation, *args, **kwargs):
        """
        Retry a database operation with exponential backoff on lock errors.
        
        Args:
            operation: Callable that performs the database operation
            *args, **kwargs: Arguments to pass to the operation
        
        Returns:
            Result of the operation
        """
        last_exception = None
        for attempt in range(self.MAX_RETRIES):
            try:
                return operation(*args, **kwargs)
            except OperationalError as e:
                # Check if it's a database lock error
                error_str = str(e).lower()
                error_type = type(e).__name__
                
                # Check for various lock error patterns
                is_lock_error = (
                    'database is locked' in error_str or 
                    'locked' in error_str
                )
                
                if is_lock_error:
                    last_exception = e
                    if attempt < self.MAX_RETRIES - 1:
                        delay = min(self.BASE_DELAY * (2 ** attempt), self.MAX_DELAY)
                        jitter = self.BASE_DELAY * 0.1 * (attempt + 1)
                        total_delay = delay + jitter
                        
                        logger.warning(
                            f"[RetryOnDbLockMixin] Database locked on attempt {attempt + 1}/{self.MAX_RETRIES} "
                            f"for {getattr(operation, '__name__', 'operation')}. Retrying in {total_delay:.3f}s... "
                            f"Error: {str(e)[:100]}"
                        )
                        time.sleep(total_delay)
                    else:
                        logger.error(
                            f"[RetryOnDbLockMixin] Database locked after {self.MAX_RETRIES} attempts "
                            f"for {getattr(operation, '__name__', 'operation')}. Giving up. "
                            f"Error: {str(e)[:200]}"
                        )
                else:
                    # Not a lock error, re-raise immediately
                    logger.debug(f"[RetryOnDbLockMixin] Non-lock OperationalError, re-raising: {type(e).__name__}: {str(e)[:100]}")
                    raise
            except Exception as e:
                # Check if it's a wrapped database lock error
                error_str = str(e).lower()
                error_type = type(e).__name__
                
                # Check if it's a database lock error in the exception chain
                if 'database is locked' in error_str or 'locked' in error_str:
                    last_exception = e
                    if attempt < self.MAX_RETRIES - 1:
                        delay = min(self.BASE_DELAY * (2 ** attempt), self.MAX_DELAY)
                        jitter = self.BASE_DELAY * 0.1 * (attempt + 1)
                        total_delay = delay + jitter
                        
                        logger.warning(
                            f"[RetryOnDbLockMixin] Database locked (wrapped) on attempt {attempt + 1}/{self.MAX_RETRIES} "
                            f"for {getattr(operation, '__name__', 'operation')}. Retrying in {total_delay:.3f}s... "
                            f"Error: {type(e).__name__}: {str(e)[:100]}"
                        )
                        time.sleep(total_delay)
                    else:
                        logger.error(
                            f"[RetryOnDbLockMixin] Database locked (wrapped) after {self.MAX_RETRIES} attempts "
                            f"for {getattr(operation, '__name__', 'operation')}. Giving up. "
                            f"Error: {type(e).__name__}: {str(e)[:200]}"
                        )
                else:
                    # Not a lock error, re-raise immediately
                    logger.debug(f"[RetryOnDbLockMixin] Non-lock error, re-raising: {type(e).__name__}: {str(e)[:100]}")
                    raise
        
        # If we exhausted all retries, raise the last exception
        if last_exception:
            logger.error(f"[RetryOnDbLockMixin] All retries exhausted, raising exception: {type(last_exception).__name__}: {str(last_exception)[:200]}")
            raise last_exception

    def save_model(self, request, obj, form, change):
        """Override save_model to add retry mechanism."""
        def _save():
            return super(RetryOnDbLockMixin, self).save_model(request, obj, form, change)
        
        try:
            self._retry_db_operation(_save)
        except (OperationalError, Exception) as e:
            error_str = str(e).lower()
            if 'database is locked' in error_str or 'locked' in error_str or 'OperationalError' in type(e).__name__:
                from django.contrib import messages
                messages.error(
                    request,
                    _("Die Datenbank ist derzeit ausgelastet. Bitte versuchen Sie es in ein paar Sekunden erneut.")
                )
                # Re-raise to let Django handle the error properly
                raise

    def save_formset(self, request, form, formset, change):
        """Override save_formset to add retry mechanism."""
        def _save():
            return super(RetryOnDbLockMixin, self).save_formset(request, form, formset, change)
        
        try:
            self._retry_db_operation(_save)
        except (OperationalError, Exception) as e:
            error_str = str(e).lower()
            if 'database is locked' in error_str or 'locked' in error_str or 'OperationalError' in type(e).__name__:
                from django.contrib import messages
                messages.error(
                    request,
                    _("Die Datenbank ist derzeit ausgelastet. Bitte versuchen Sie es in ein paar Sekunden erneut.")
                )
                raise

    def delete_model(self, request, obj):
        """Override delete_model to add retry mechanism."""
        def _delete():
            return super(RetryOnDbLockMixin, self).delete_model(request, obj)
        
        try:
            self._retry_db_operation(_delete)
        except (OperationalError, Exception) as e:
            error_str = str(e).lower()
            if 'database is locked' in error_str or 'locked' in error_str or 'OperationalError' in type(e).__name__:
                from django.contrib import messages
                messages.error(
                    request,
                    _("Die Datenbank ist derzeit ausgelastet. Bitte versuchen Sie es in ein paar Sekunden erneut.")
                )
                raise

# --- 3. MAP WIDGETS ---

class MapInputWidget(forms.TextInput):
    """Widget for GPS single points - map and fields without the annoying admin sidebar"""
    def render(self, name, value, attrs=None, renderer=None):
        attrs.update({'style': 'width: 200px; height: 30px; margin: 5px 0; border: 1px solid #ccc;'})
        input_html = super().render(name, value, attrs, renderer)

        # We use a container that overlays the left admin column
        # 'margin-left: -170px' shifts everything left, 'padding-left: 170px' compensates for content
        wrapper_style = "display: block; width: 100%; clear: both; margin-left: -170px; padding-left: 5px;"

        if name == 'gps_latitude':
            return mark_safe(f'''
                <div style="{wrapper_style}">
                    <div id="leaflet_map" style="height: 400px; width: calc(100% + 150px); max-width: 950px; border: 1px solid #ccc; margin-bottom: 15px; border-radius: 4px; z-index: 1;"></div>
                    <div style="margin-bottom: 10px; display: block;">
                        <label style="display: inline-block; width: 120px; font-weight: bold; color: #444;">Latitude:</label> {input_html}
                    </div>
                </div>
            ''')

        if name == 'gps_longitude':
            return mark_safe(f'''
                <div style="{wrapper_style} margin-top: -5px;">
                    <div style="margin-bottom: 10px; display: block;">
                        <label style="display: inline-block; width: 120px; font-weight: bold; color: #444;">Longitude:</label> {input_html}
                    </div>
                </div>
                <script>
                    (function() {{
                        function initMap() {{
                            var latIn = document.getElementById('id_gps_latitude');
                            var lonIn = document.getElementById('id_gps_longitude');
                            var mapDiv = document.getElementById('leaflet_map');
                            if (!latIn || !lonIn || !mapDiv) return;

                            var sLat = parseFloat(latIn.value) || 51.1657;
                            var sLon = parseFloat(lonIn.value) || 10.4515;

                            var map = L.map('leaflet_map').setView([sLat, sLon], (latIn.value ? 13 : 6));
                            L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png').addTo(map);
                            var marker = L.marker([sLat, sLon], {{draggable: true}}).addTo(map);

                            function updateFields(lat, lon) {{
                                latIn.value = lat.toFixed(6);
                                lonIn.value = lon.toFixed(6);
                            }}

                            map.on('click', function(e) {{
                                marker.setLatLng(e.latlng);
                                updateFields(e.latlng.lat, e.latlng.lng);
                            }});

                            marker.on('dragend', function(e) {{
                                var p = marker.getLatLng();
                                updateFields(p.lat, p.lng);
                            }});

                            // InvalidateSize fixes display errors on load
                            setTimeout(function(){{ map.invalidateSize(); }}, 200);

                            // Remove the original admin labels from the first column
                            var rows = document.querySelectorAll('.field-gps_latitude, .field-gps_longitude');
                            rows.forEach(function(row) {{
                                var originalLabel = row.querySelector('label');
                                if (originalLabel && originalLabel.style.display !== 'none') {{
                                    originalLabel.style.visibility = 'hidden'; // Keep space but invisible
                                    originalLabel.style.width = '0px';
                                }}
                            }});
                        }}
                        if (window.L) {{
                            initMap();
                        }}
                        if (!window.L) {{
                            window.addEventListener('load', initMap);
                        }}
                    }})();
                </script>
            ''')
        return input_html

class ShortNameWidget(forms.TextInput):
    """Widget for short_name field with limited width (max 15 characters)"""
    def __init__(self, attrs=None):
        default_attrs = {'style': 'width: 180px; max-width: 180px;'}
        if attrs:
            default_attrs.update(attrs)
        super().__init__(attrs=default_attrs)

class TrackMapWidget(forms.Textarea):
    """Widget for displaying track map in textarea."""

class LimitedDescriptionWidget(forms.Textarea):
    """Widget for milestone description with character limit (500 chars)."""
    def __init__(self, attrs=None):
        default_attrs = {
            'maxlength': '500',
            'rows': '4',
            'cols': '40',
            'style': 'max-width: 100%;'
        }
        if attrs:
            default_attrs.update(attrs)
        super().__init__(attrs=default_attrs)

class MilestoneAdminForm(forms.ModelForm):
    """Custom form for Milestone admin with limited description field."""
    class Meta:
        model = Milestone
        fields = '__all__'
        widgets = {
            'description': LimitedDescriptionWidget()
        }

class CollapsibleCheckboxSelectMultiple(forms.CheckboxSelectMultiple):
    """Collapsible checkbox widget for ManyToMany fields to save space in inline forms."""
    
    def __init__(self, attrs=None, collapse_by_default=True):
        super().__init__(attrs)
        self.collapse_by_default = collapse_by_default
    
    def render(self, name, value, attrs=None, renderer=None):
        """Render the widget with collapsible functionality."""
        if renderer is None:
            renderer = forms.renderers.get_default_renderer()
        
        # Get the base HTML from parent
        html = super().render(name, value, attrs, renderer)
        
        # Count selected items - value can be a list of IDs or a queryset
        if value is None:
            selected_count = 0
        elif hasattr(value, '__iter__') and not isinstance(value, str):
            selected_count = len(list(value))
        else:
            selected_count = 1 if value else 0
        
        display_text = f"{selected_count} Track(s) ausgewählt" if selected_count > 0 else "Keine Tracks ausgewählt"
        
        # Get widget ID
        widget_id = attrs.get('id', name) if attrs else name
        if not widget_id:
            widget_id = f"id_{name}"
        
        # Generate unique ID for this instance to avoid conflicts
        import uuid
        unique_id = str(uuid.uuid4())[:8]
        widget_id_full = f"{widget_id}_{unique_id}"
        
        collapsed_class = 'collapsed' if self.collapse_by_default else ''
        
        return mark_safe(f'''
        <div class="collapsible-checkbox-container {collapsed_class}" data-widget-id="{widget_id_full}">
            <div class="collapsible-checkbox-header" onclick="toggleCheckboxList_{unique_id}()">
                <span class="collapsible-checkbox-toggle">▼</span>
                <span class="collapsible-checkbox-label">{display_text}</span>
            </div>
            <div class="collapsible-checkbox-content" id="{widget_id_full}_content">
                {html}
            </div>
        </div>
        <script>
        function toggleCheckboxList_{unique_id}() {{
            const container = document.querySelector('[data-widget-id="{widget_id_full}"]');
            if (!container) return;
            const content = document.getElementById('{widget_id_full}_content');
            const toggle = container.querySelector('.collapsible-checkbox-toggle');
            
            if (container.classList.contains('collapsed')) {{
                container.classList.remove('collapsed');
                if (content) content.style.display = 'block';
                if (toggle) toggle.textContent = '▲';
            }} else {{
                container.classList.add('collapsed');
                if (content) content.style.display = 'none';
                if (toggle) toggle.textContent = '▼';
            }}
        }}
        // Update label when checkboxes change
        (function() {{
            const container = document.querySelector('[data-widget-id="{widget_id_full}"]');
            if (container) {{
                const updateLabel = function() {{
                    const checkboxes = container.querySelectorAll('input[type="checkbox"]');
                    const label = container.querySelector('.collapsible-checkbox-label');
                    const checked = container.querySelectorAll('input[type="checkbox"]:checked').length;
                    if (label) {{
                        label.textContent = checked > 0 ? checked + ' Track(s) ausgewählt' : 'Keine Tracks ausgewählt';
                    }}
                }};
                // Update on page load
                setTimeout(updateLabel, 100);
                // Update on checkbox change
                container.addEventListener('change', function(e) {{
                    if (e.target.type === 'checkbox') {{
                        updateLabel();
                    }}
                }});
            }}
        }})();
        </script>
        <style>
        .collapsible-checkbox-container {{
            border: 1px solid #ddd;
            border-radius: 4px;
            margin: 2px 0;
        }}
        .collapsible-checkbox-header {{
            background: #f8f9fa;
            padding: 6px 10px;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 8px;
            user-select: none;
            font-size: 12px;
        }}
        .collapsible-checkbox-header:hover {{
            background: #e9ecef;
        }}
        .collapsible-checkbox-toggle {{
            font-size: 10px;
            color: #666;
            transition: transform 0.2s;
            width: 12px;
            display: inline-block;
        }}
        .collapsible-checkbox-label {{
            font-size: 12px;
            color: #333;
        }}
        .collapsible-checkbox-content {{
            padding: 8px;
            max-height: 150px;
            overflow-y: auto;
        }}
        .collapsible-checkbox-container.collapsed .collapsible-checkbox-content {{
            display: none;
        }}
        .collapsible-checkbox-content ul {{
            list-style: none;
            margin: 0;
            padding: 0;
        }}
        .collapsible-checkbox-content li {{
            margin: 3px 0;
        }}
        .collapsible-checkbox-content label {{
            display: flex;
            align-items: center;
            gap: 6px;
            cursor: pointer;
            font-size: 12px;
        }}
        </style>
        ''')

class TrackMapWidget(forms.Textarea):
    """Widget for TravelTracks (polyline display)"""
    def render(self, name, value, attrs=None, renderer=None):
        attrs.update({'readonly': 'readonly', 'style': 'width: 100%; height: 60px; font-family: monospace; font-size: 10px;'})
        input_html = super().render(name, value, attrs, renderer)
        return mark_safe(f'''
            <div id="track_map" style="height: 500px; width: 100%; border: 1px solid #ccc; margin-bottom: 10px; border-radius: 4px; z-index: 1;"></div>
            {input_html}
            <script>
                // Hide the track map when the MilestoneInline template is active (has milestone-map-admin)
                window.addEventListener('load', function() {{
                    setTimeout(function() {{
                        var milestoneMap = document.getElementById('milestone-map-admin');
                        var trackMapDiv = document.getElementById('track_map');

                        if (milestoneMap && trackMapDiv) {{
                            // MilestoneInline is active, hide the track map
                            trackMapDiv.style.display = 'none';
                        }}
                        if (trackMapDiv && !milestoneMap) {{
                            // No MilestoneInline, show the track map
                            trackMapDiv.style.display = 'block';
                            var map = L.map('track_map').setView([51.1657, 10.4515], 6);
                            L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png').addTo(map);
                            try {{
                                var dataStr = document.getElementById('id_geojson_data').value;
                                if (dataStr) {{
                                    var points = JSON.parse(dataStr);
                                    if (points.length > 0) {{
                                        var polyline = L.polyline(points, {{color: '#007bff', weight: 5}}).addTo(map);
                                        map.fitBounds(polyline.getBounds());
                                    }}
                                }}
                            }} catch(e) {{ console.error(e); }}
                            // InvalidateSize korrigiert Darstellungsfehler
                            setTimeout(function(){{ map.invalidateSize(); }}, 200);
                        }}
                    }}, 100);
                }});
            </script>
        ''')

# --- 3. SAFETY CONFIRMATION ---

CONFIRM_KM_JS = f"""
<script>
document.addEventListener('DOMContentLoaded', function() {{
    const kmFields = document.querySelectorAll('input[name="distance_total"], input[name="cumulative_mileage"]');
    const form = document.querySelector('form');
    if (kmFields.length > 0 && form) {{
        kmFields.forEach(f => {{ f.dataset.orig = f.value; }});
        form.addEventListener('submit', function(e) {{
            let changed = false;
            kmFields.forEach(f => {{
                let cur = parseFloat(f.value) || 0;
                let ori = parseFloat(f.dataset.orig) || 0;
                if (Math.abs(cur - ori) > 0.0001) changed = true;
            }});
            if (changed && !confirm("{_('ACHTUNG: Kilometerstand manuell ändern?')}")) {{
                e.preventDefault();
                document.querySelectorAll('.submit-row input').forEach(b => b.disabled = false);
            }}
        }});
    }}
}});
</script>
"""

# --- 4. BASE ADMIN & FORMS ---

class KMBaseForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in ['distance_total', 'cumulative_mileage']:
            if field in self.fields and self.initial.get(field) is not None:
                # Decimal fields are already precise, no rounding needed
                pass

class BaseAdmin(admin.ModelAdmin):
    form = KMBaseForm
    def render_change_form(self, request, context, *args, **kwargs):
        res = super().render_change_form(request, context, *args, **kwargs)
        res.render()
        res.content = res.content.replace(b'</form>', CONFIRM_KM_JS.encode('utf-8') + b'</form>')
        return res

# --- 5. ADMIN REGISTRATIONS ---

LEAFLET_ASSETS = {
    'css': {'all': ('https://unpkg.com/leaflet@1.9.4/dist/leaflet.css',)},
    'js': (
        'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js',
        'https://cdn.jsdelivr.net/npm/leaflet-geometryutil@0.10.3/src/leaflet.geometryutil.min.js',
    )
}

class DeviceConfigurationInline(admin.StackedInline):
    """Inline configuration for Device."""
    model = DeviceConfiguration
    extra = 0
    max_num = 1
    can_delete = False
    fieldsets = (
        (_("API-Key-Verwaltung"), {
            'fields': ('device_specific_api_key', 'api_key_rotation_enabled', 'api_key_rotation_interval_days', 'api_key_last_rotated', 'generate_api_key_button', 'test_rotation_button'),
            'description': _("Gerätespezifischer API-Key für sichere Authentifizierung. Verwenden Sie 'API-Key generieren' für sofortige Erneuerung oder 'Rotation testen' um die automatische Rotation zu prüfen.")
        }),
        (_("Geräte-Identifikation"), {
            'fields': ('reported_device_name_display', 'default_id_tag'),
            'description': _("Der Gerätename wird vom Gerät gemeldet und ist schreibgeschützt. Der Standard-ID-Tag kann konfiguriert werden.")
        }),
        (_("Kommunikation"), {
            'fields': ('send_interval_seconds', 'server_url')
        }),
        (_("WLAN-Einstellungen"), {
            'fields': ('wifi_ssid', 'wifi_password'),
            'classes': ('collapse',)
        }),
        (_("Config-WLAN-Einstellungen"), {
            'fields': ('ap_password',),
            'classes': ('collapse',),
            'description': _("Passwort für den Config-WLAN-Hotspot (MCC_XXXX). Minimum 8 Zeichen erforderlich (WPA2-Anforderung).")
        }),
        (_("Geräte-Verhalten"), {
            'fields': ('debug_mode', 'test_mode', 'deep_sleep_seconds', 'config_fetch_interval_seconds', 'request_config_comparison')
        }),
        (_("Hardware"), {
            'fields': ('wheel_size',)
        }),
        (_("Firmware"), {
            'fields': ('assigned_firmware', 'last_synced_at')
        }),
    )
    readonly_fields = ('last_synced_at', 'api_key_last_rotated', 'generate_api_key_button', 'test_rotation_button', 'force_rotation_button', 'reported_device_name_display')
    
    def test_rotation_button(self, obj):
        """Display button to test API key rotation."""
        if obj and obj.pk:
            from django.utils.html import format_html
            from django.urls import reverse
            url = reverse('admin:iot_deviceconfiguration_test_rotation', args=[obj.pk])
            return format_html(
                '<a class="button" href="{}" onclick="return confirm(\'Möchten Sie die API-Key-Rotation jetzt testen? Dies prüft, ob die Rotation aktiviert ist und ob das Intervall erreicht wurde.\');">Rotation testen</a>',
                url
            )
        return _("Speichern Sie zuerst die Gerätekonfiguration, um die Rotation zu testen")
    test_rotation_button.short_description = _("Rotation testen")
    
    def force_rotation_button(self, obj):
        """Display button to force API key rotation immediately."""
        if obj and obj.pk:
            from django.utils.html import format_html
            from django.urls import reverse
            url = reverse('admin:iot_deviceconfiguration_force_rotation', args=[obj.pk])
            return format_html(
                '<a class="button" href="{}" onclick="return confirm(\'Möchten Sie die API-Key-Rotation jetzt ausführen? Ein neuer API-Key wird generiert und das Gerät holt ihn beim nächsten Config-Report ab. Der alte Key wird ungültig.\');">Rotation jetzt ausführen</a>',
                url
            )
        return _("Speichern Sie zuerst die Gerätekonfiguration, um die Rotation auszuführen")
    force_rotation_button.short_description = _("Rotation jetzt ausführen")
    
    def reported_device_name_display(self, obj):
        """Display device name as reported by the device (not from database)."""
        if obj:
            reported_name = obj.get_reported_device_name()
            if reported_name:
                return reported_name
            return _("Noch nicht vom Gerät gemeldet")
        return "-"
    reported_device_name_display.short_description = _("Gerätename (vom Gerät gemeldet)")
    
    def generate_api_key_button(self, obj):
        """Display button to generate API key."""
        if obj and obj.pk:
            from django.utils.html import format_html
            from django.urls import reverse
            url = reverse('admin:iot_deviceconfiguration_generate_api_key', args=[obj.pk])
            return format_html(
                '<a class="button" href="{}" onclick="return confirm(\'Are you sure you want to generate a new API key? The old key will be invalidated.\');">Generate New API Key</a>',
                url
            )
        return _("Speichern Sie zuerst die Gerätekonfiguration, um einen API-Key zu generieren")
    generate_api_key_button.short_description = _("API-Key-Aktionen")


class DeviceConfigurationReportInline(admin.TabularInline):
    """Inline reports for Device."""
    model = DeviceConfigurationReport
    extra = 0
    max_num = 10
    readonly_fields = ('created_at', 'has_differences')
    fields = ('created_at', 'has_differences')
    can_delete = True


# --- MCC CORE API & MODELS ADMIN REGISTRATIONS ---
# Order: 1. GroupType, 2. Group, 3. Cyclist, 4. TravelTrack, 5. Milestone, 6. Event, 7. CyclistDeviceCurrentMileage, 8. GroupTravelStatus, 9. TravelHistory, 10. EventHistory, 11. HourlyMetric

@admin.register(GroupType)
class GroupTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'description', 'is_active')
    list_editable = ('is_active',)
    search_fields = ('name', 'description')
    list_filter = ('is_active',)

@admin.register(Group)
class GroupAdmin(RetryOnDbLockMixin, BaseAdmin):
    list_display = ('name', 'short_name', 'group_type', 'distance_total_display', 'parent_display', 'is_visible', 'color_preview', 'logo_preview')
    list_editable = ('is_visible', 'short_name')
    search_fields = ('name', 'short_name')
    readonly_fields = ('logo_preview', 'color_preview')
    change_list_template = 'admin/api/group_change_list.html'
    inlines = [GroupMilestoneAchievementInline]
    
    def get_urls(self):
        urls = super().get_urls()
        from django.urls import path
        from mgmt import admin_views
        custom_urls = [
            path('bulk-create-school/', self.admin_site.admin_view(admin_views.bulk_create_school), name='api_group_bulk_create_school'),
            path('bulk-create-school/preview/', self.admin_site.admin_view(admin_views.bulk_create_school_preview), name='api_group_bulk_create_school_preview'),
        ]
        return custom_urls + urls
    
    def changelist_view(self, request, extra_context=None):
        """Add bulk create button to changelist."""
        extra_context = extra_context or {}
        from django.urls import reverse
        extra_context['bulk_create_url'] = reverse('admin:api_group_bulk_create_school')
        return super().changelist_view(request, extra_context)
    fieldsets = (
        (_('Gruppeninformationen'), {
            'fields': ('group_type', 'name', 'short_name', 'parent', 'is_visible')
        }),
        (_('Darstellung'), {
            'fields': ('logo', 'logo_preview', 'color', 'color_preview'),
            'description': mark_safe(_('Verwenden Sie einen <a href="https://htmlcolorcodes.com/color-picker/" target="_blank">Farbwähler</a> '
                           'oder <a href="https://colorpicker.me/" target="_blank">Color Picker</a> '
                           'um den Hex-Code zu ermitteln.'))
        }),
        (_('Statistiken'), {
            'fields': ('distance_total', 'coins_total')
        }),
        (_('Verwaltung'), {
            'fields': ('managers', 'comments')
        }),
    )

    def get_form(self, request, obj=None, **kwargs):
        """Override to use custom widget for short_name field."""
        form = super().get_form(request, obj, **kwargs)
        if 'short_name' in form.base_fields:
            form.base_fields['short_name'].widget = ShortNameWidget()
        return form

    def distance_total_display(self, obj):
        """Display distance_total with German format (comma decimal)."""
        if obj.distance_total is None:
            return format_km_de(0)
        return format_km_de(obj.distance_total)
    distance_total_display.short_description = _("Gesamtkilometer")
    distance_total_display.admin_order_field = 'distance_total'

    def parent_display(self, obj):
        """Display parent group name only, without group_type."""
        if obj.parent:
            return obj.parent.name
        return _("Keine")
    parent_display.short_description = _("Übergeordnete Gruppe")
    parent_display.admin_order_field = 'parent__name'

    def logo_preview(self, obj):
        """Generates an HTML preview for the group logo"""
        if obj.logo:
            return mark_safe(f'<img src="{obj.logo.url}" style="height:50px; border-radius:5px;"/>')
        return _("Kein Logo")
    logo_preview.short_description = _("Logo Vorschau")
    
    def color_preview(self, obj):
        """Generates a color preview for the group color"""
        if obj and obj.color and obj.color.strip():
            color_value = obj.color.strip()
            # Validate hex color format (basic check)
            if not color_value.startswith('#'):
                color_value = '#' + color_value
            return mark_safe(
                f'<div style="width: 60px; height: 40px; background-color: {color_value}; '
                f'border: 2px solid #333; border-radius: 4px; display: inline-block; vertical-align: middle;"></div> '
                f'<span style="margin-left: 10px; vertical-align: middle; font-weight: bold;">{color_value}</span>'
            )
        color_picker_links = (
            '<a href="https://htmlcolorcodes.com/color-picker/" target="_blank" style="margin-right: 10px;">'
            '🎨 HTML Color Codes</a> | '
            '<a href="https://colorpicker.me/" target="_blank" style="margin-right: 10px;">'
            '🎨 Color Picker</a> | '
            '<a href="https://coolors.co/" target="_blank">🎨 Coolors</a>'
        )
        return mark_safe(f'{_("Keine Farbe definiert")}<br><small style="margin-top: 5px; display: block;">{color_picker_links}</small>')
    color_preview.short_description = _("Farbvorschau")

    class Media:
        css = {
            'all': ('admin/css/group_admin.css',)
        }

class CyclistAdminForm(forms.ModelForm):
    """Custom form for Cyclist admin with single group selection."""
    
    # Replace ManyToMany groups field with single select
    group = forms.ModelChoiceField(
        queryset=Group.objects.filter(is_visible=True).order_by('name'),
        required=False,
        label=_("Gruppe"),
        help_text=_("Wählen Sie eine Gruppe aus. Ein Radler darf nur einer Gruppe zugeordnet werden.")
    )
    
    class Meta:
        model = Cyclist
        exclude = ('groups',)  # Exclude groups field, we use 'group' instead
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Remove the original groups ManyToMany field if it exists
        # This must be done after super().__init__() so the field is created first
        if 'groups' in self.fields:
            del self.fields['groups']
        
        # Set initial value for group field if instance exists and has groups
        # This must be done after removing 'groups' field
        if self.instance and self.instance.pk:
            try:
                existing_groups = self.instance.groups.all()
                if existing_groups.exists():
                    # Use the first group if multiple exist
                    self.fields['group'].initial = existing_groups.first().id
            except Exception:
                # If instance is not yet saved, groups might not be accessible
                pass
        
    def clean(self):
        """Validate cyclist data."""
        cleaned_data = super().clean()
        return cleaned_data
    
    def save(self, commit=True):
        """Override save to handle single group assignment."""
        instance = super().save(commit=commit)
        # Group assignment will be handled in save_related
        return instance


@admin.register(Cyclist)
class CyclistAdmin(RetryOnDbLockMixin, BaseAdmin):
    form = CyclistAdminForm
    list_display = ('user_id', 'id_tag', 'groups_display', 'distance_total_display', 'last_active', 'is_visible', 'is_km_collection_enabled', 'avatar_preview')
    list_editable = ('is_visible', 'is_km_collection_enabled')
    search_fields = ('user_id', 'id_tag')
    readonly_fields = ('avatar_preview',)
    list_filter = ('groups', 'is_visible', 'is_km_collection_enabled', 'last_active')
    
    
    def get_form(self, request, obj=None, **kwargs):
        """Override get_form to ensure form is properly initialized."""
        form = super().get_form(request, obj, **kwargs)
        return form
    

    def groups_display(self, obj):
        """Display groups as comma-separated list."""
        groups = obj.groups.all().order_by('name')
        if groups:
            return ', '.join([group.name for group in groups])
        return _("Keine Gruppen")
    groups_display.short_description = _("Gruppen")
    groups_display.admin_order_field = 'groups__name'

    def distance_total_display(self, obj):
        """Display distance_total with German format (comma decimal)."""
        if obj.distance_total is None:
            return format_km_de(0)
        return format_km_de(obj.distance_total)
    distance_total_display.short_description = _("Gesamtkilometer")
    distance_total_display.admin_order_field = 'distance_total'

    def avatar_preview(self, obj):
        """Generates an HTML preview for the cyclist avatar"""
        if obj.avatar:
            return mark_safe(f'<img src="{obj.avatar.url}" style="height:50px; border-radius:50%;"/>')
        return _("Kein Avatar")
    avatar_preview.short_description = _("Avatar Vorschau")
    
    def save_related(self, request, form, formsets, change):
        """Override save_related to handle single group assignment."""
        # Get the selected group from the form
        selected_group = form.cleaned_data.get('group')
        
        # Clear existing groups and add the selected group
        form.instance.groups.clear()
        if selected_group:
            form.instance.groups.add(selected_group)
        
        # Call parent save_related (though there are no other related objects to save)
        super().save_related(request, form, formsets, change)

@admin.register(CyclistDeviceCurrentMileage)
class CyclistDeviceCurrentMileageAdmin(BaseAdmin):
    list_display = ('cyclist', 'top_group_display', 'device', 'cumulative_mileage_display')
    
    def get_queryset(self, request):
        """Optimize queryset with select_related and prefetch_related to avoid N+1 queries."""
        from django.db.models import Subquery, OuterRef, CharField, Value
        from django.db.models.functions import Coalesce
        
        qs = super().get_queryset(request)
        qs = qs.select_related('cyclist', 'device').prefetch_related('cyclist__groups__parent')
        
        # Annotate with first group name for sorting
        # This allows sorting by the first group's name (as a proxy for top group sorting)
        first_group = Group.objects.filter(
            members=OuterRef('cyclist'),
            is_visible=True
        ).order_by('name').values('name')[:1]
        
        qs = qs.annotate(
            first_group_name=Coalesce(
                Subquery(first_group),
                Value(''),
                output_field=CharField()
            )
        )
        
        return qs

    def cumulative_mileage_display(self, obj):
        """Display cumulative_mileage with German format (comma decimal)."""
        if obj.cumulative_mileage is None:
            return format_km_de(0)
        return format_km_de(obj.cumulative_mileage)
    cumulative_mileage_display.short_description = _("Kumulative Kilometer")
    cumulative_mileage_display.admin_order_field = 'cumulative_mileage'
    
    def top_group_display(self, obj):
        """Display the top parent group of the cyclist."""
        if not obj or not obj.cyclist:
            return "-"
        
        # Get all groups for this cyclist (already prefetched)
        groups = obj.cyclist.groups.filter(is_visible=True)
        if not groups.exists():
            return "-"
        
        # Get top parent names for all groups
        # Use top_parent_name property which handles parent traversal
        top_groups = set()
        for group in groups:
            top_groups.add(group.top_parent_name)
        
        # If all groups have the same top parent, return it
        if len(top_groups) == 1:
            return list(top_groups)[0]
        
        # If multiple top groups, return comma-separated list
        return ", ".join(sorted(top_groups))
    top_group_display.short_description = _("TOP Gruppe")
    top_group_display.admin_order_field = 'first_group_name'

class GroupEventStatusInline(admin.TabularInline):
    """Displays all groups participating in this event"""
    model = GroupEventStatus
    extra = 1
    verbose_name = _("Teilnehmende Gruppe")
    fields = ('group', 'current_distance_km_display')
    readonly_fields = ('current_distance_km_display',)

    def get_formset(self, request, obj=None, **kwargs):
        """Customize formset to filter available groups for selection."""
        formset = super().get_formset(request, obj, **kwargs)
        
        class GroupEventStatusFormSet(formset):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                # Get available groups for selection
                if obj and obj.pk:
                    # Exclude groups that already participate in this event
                    existing_group_ids = obj.group_statuses.values_list('group_id', flat=True)
                    available_groups = Group.objects.exclude(
                        id__in=existing_group_ids
                    ).filter(
                        is_visible=True
                    ).order_by('name')
                    
                    for form in self.forms:
                        # For new entries, customize the group field
                        if not form.instance.pk:
                            if 'group' in form.fields:
                                # Filter the queryset to only show available groups
                                form.fields['group'].queryset = available_groups
                                # Use label_from_instance to show group name and type
                                form.fields['group'].label_from_instance = lambda obj: f"{obj.name} ({obj.group_type})"
                        else:
                            # For existing entries, make group readonly
                            if 'group' in form.fields:
                                form.fields['group'].widget.attrs['readonly'] = True
                                # Make it visually disabled but still submit the value
                                form.fields['group'].widget.attrs['style'] = 'pointer-events: none; background-color: #e9ecef;'
        
        return GroupEventStatusFormSet

    def current_distance_km_display(self, obj):
        """Display current_distance_km with German format (comma decimal)."""
        if obj and obj.current_distance_km is not None:
            return format_km_de(obj.current_distance_km)
        return format_km_de(0)
    current_distance_km_display.short_description = _("Aktuelle Distanz (km)")

@admin.register(TravelTrack)
class TravelTrackAdmin(admin.ModelAdmin):
    list_display = ('name', 'total_length_km_display', 'groups_count', 'is_active', 'is_visible_on_map', 'auto_start', 'start_time', 'end_time')
    list_editable = ('is_active', 'is_visible_on_map', 'auto_start')
    inlines = [MilestoneInline, GroupTravelStatusInline, LeafGroupTravelContributionInline]
    fields = ('name', 'track_file', 'total_length_km', 'is_active', 'is_visible_on_map', 'auto_start', 'start_time', 'end_time', 'geojson_data', 'top_groups_ranking_display')
    readonly_fields = ('total_length_km', 'top_groups_ranking_display')
    formfield_overrides = {models.TextField: {'widget': TrackMapWidget}}
    actions = ['restart_trip', 'save_trip_to_history']
    
    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        """Override to inject groups with travel status data for JavaScript."""
        extra_context = extra_context or {}
        from api.models import GroupTravelStatus
        import json
        
        # Get all groups with existing travel status for JavaScript
        existing_statuses = GroupTravelStatus.objects.select_related('group', 'track').all()
        groups_with_status = {}
        for status in existing_statuses:
            groups_with_status[str(status.group_id)] = {
                'group_name': status.group.name,
                'track_name': status.track.name,
                'current_km': float(status.current_travel_distance) if status.current_travel_distance else 0,
                'status_id': status.pk
            }
        
        extra_context['groups_with_travel_status_json'] = json.dumps(groups_with_status)
        return super().changeform_view(request, object_id, form_url, extra_context)

    def total_length_km_display(self, obj):
        """Display total_length_km with German format (comma decimal)."""
        if obj.total_length_km is None:
            return format_km_de(0)
        return format_km_de(obj.total_length_km)
    total_length_km_display.short_description = _("Gesamtlänge (km)")
    total_length_km_display.admin_order_field = 'total_length_km'
    
    def top_groups_ranking_display(self, obj):
        """Display ranking of top groups (groups defined in this travel track) as a table."""
        if not obj or not obj.pk:
            return _("Speichern Sie zuerst die Reiseroute, um das Ranking der Top-Gruppen anzuzeigen.")
        
        # Get all groups participating in this track
        statuses = list(GroupTravelStatus.objects.filter(
            track=obj
        ).select_related('group').all())
        
        if not statuses:
            return _("Noch keine Gruppen auf dieser Reiseroute.")
        
        # Sort in Python: groups with goal_reached_at first (sorted by time), then by distance
        # IMPORTANT: Groups that reached the goal first should be ranked higher
        statuses.sort(key=lambda s: (
            0 if s.goal_reached_at else 1,  # Groups with goal_reached_at come first (0 < 1)
            s.goal_reached_at if s.goal_reached_at else timezone.now(),  # Earlier time = better rank
            -float(s.current_travel_distance or 0),  # Higher distance = better (negative for descending)
            s.group.name  # Alphabetical as tiebreaker
        ))
        
        # Build HTML table
        html = '<table style="width: 100%; border-collapse: collapse; margin-top: 10px;">'
        html += '<thead><tr style="background-color: #f8f9fa; border-bottom: 2px solid #dee2e6;">'
        html += f'<th style="padding: 8px; text-align: left; border: 1px solid #dee2e6;">{_("Rang")}</th>'
        html += f'<th style="padding: 8px; text-align: left; border: 1px solid #dee2e6;">{_("Gruppe")}</th>'
        html += f'<th style="padding: 8px; text-align: right; border: 1px solid #dee2e6;">{_("Distanz (km)")}</th>'
        html += f'<th style="padding: 8px; text-align: center; border: 1px solid #dee2e6;">{_("Ziel erreicht")}</th>'
        html += f'<th style="padding: 8px; text-align: center; border: 1px solid #dee2e6;">{_("Reisezeit")}</th>'
        html += '</tr></thead><tbody>'
        
        for rank, status in enumerate(statuses, start=1):
            # Medal emoji for top 3
            rank_display = ""
            if rank == 1:
                rank_display = "🥇 1"
            elif rank == 2:
                rank_display = "🥈 2"
            elif rank == 3:
                rank_display = "🥉 3"
            else:
                rank_display = str(rank)
            
            # IMPORTANT: Cap distance at track total_length_km for consistency with avatar display
            distance_km = status.current_travel_distance or Decimal('0.00000')
            if obj.total_length_km and distance_km > obj.total_length_km:
                distance_km = obj.total_length_km
            
            # Check if goal is reached
            goal_reached = "✅" if (obj.total_length_km and distance_km >= obj.total_length_km) else "⏳"
            travel_duration_display = ""
            if obj.total_length_km and distance_km >= obj.total_length_km:
                # Goal is reached - calculate travel duration
                # Use goal_reached_at if available, otherwise use current time as fallback
                end_time = status.goal_reached_at if status.goal_reached_at else timezone.now()
                
                if status.goal_reached_at:
                    goal_reached += f"<br><small style='color: #666;'>{status.goal_reached_at.strftime('%d.%m.%Y %H:%M:%S')}</small>"
                
                # Calculate travel duration from start to goal
                # IMPORTANT: Use the same logic as map/views.py to ensure consistency
                # Only use the assigned entry that comes AFTER the most recent
                # 'restarted' or 'completed' entry to avoid summing travel times across restarts
                # Only consider entries that occurred BEFORE goal_reached_at
                try:
                    from api.models import TravelHistory
                    # First, find the most recent 'restarted' or 'completed' entry
                    # that occurred BEFORE or AT goal_reached_at
                    last_restart_or_complete = TravelHistory.objects.filter(
                        track=obj,
                        group=status.group,
                        action_type__in=['restarted', 'completed'],
                        end_time__lte=end_time  # Only entries before or at goal_reached_at
                    ).order_by('-end_time').first()
                    
                    # Find the assigned entry that comes after the restart/completion
                    if last_restart_or_complete:
                        # Use assigned entry that starts after the restart/completion end time
                        # and before or at goal_reached_at
                        assigned_entry = TravelHistory.objects.filter(
                            track=obj,
                            group=status.group,
                            action_type='assigned',
                            start_time__gt=last_restart_or_complete.end_time,
                            start_time__lte=end_time  # Must be before or at goal_reached_at
                        ).order_by('-start_time').first()
                        
                        if assigned_entry:
                            start_time = assigned_entry.start_time
                        else:
                            # No assigned entry after restart - use restart end time as start
                            # This handles the case where trip was restarted but no new assignment entry was created
                            start_time = last_restart_or_complete.end_time
                    else:
                        # No restart/completion found, use the most recent assigned entry
                        # that occurred before or at goal_reached_at
                        assigned_entry = TravelHistory.objects.filter(
                            track=obj,
                            group=status.group,
                            action_type='assigned',
                            start_time__lte=end_time  # Must be before or at goal_reached_at
                        ).order_by('-start_time').first()
                        
                        if assigned_entry:
                            start_time = assigned_entry.start_time
                        else:
                            # Fallback: use track.start_time if available and before goal_reached_at
                            if obj.start_time and obj.start_time <= end_time:
                                start_time = obj.start_time
                            else:
                                # If track.start_time is after goal_reached_at, use goal_reached_at as start
                                # This should not happen in normal operation, but prevents negative durations
                                start_time = end_time
                    
                    if start_time and start_time <= end_time:
                        travel_duration = end_time - start_time
                        total_seconds = int(travel_duration.total_seconds())
                        if total_seconds > 0:
                            days = total_seconds // 86400
                            hours = (total_seconds % 86400) // 3600
                            minutes = (total_seconds % 3600) // 60
                            seconds = total_seconds % 60
                            
                            # Format: Tage:Stunden:Minuten:Sekunden
                            if days > 0:
                                travel_duration_display = f"{days}:{hours:02d}:{minutes:02d}:{seconds:02d}"
                            else:
                                travel_duration_display = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                        else:
                            travel_duration_display = ""
                    else:
                        # Invalid time range - set to empty
                        travel_duration_display = ""
                except Exception as e:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(f"[top_groups_ranking_display] Error calculating travel duration for {status.group.name}: {e}", exc_info=True)
            
            html += '<tr>'
            html += f'<td style="padding: 8px; border: 1px solid #dee2e6;">{rank_display}</td>'
            html += f'<td style="padding: 8px; border: 1px solid #dee2e6;">{status.group.name}</td>'
            html += f'<td style="padding: 8px; text-align: right; border: 1px solid #dee2e6;">{format_km_de(distance_km)}</td>'
            html += f'<td style="padding: 8px; text-align: center; border: 1px solid #dee2e6;">{goal_reached}</td>'
            html += f'<td style="padding: 8px; text-align: center; border: 1px solid #dee2e6;">{travel_duration_display if travel_duration_display else "-"}</td>'
            html += '</tr>'
        
        html += '</tbody></table>'
        return mark_safe(html)
    top_groups_ranking_display.short_description = _("Top-Gruppen Ranking")

    def groups_count(self, obj):
        """Display the number of groups assigned to this track."""
        count = obj.group_statuses.count()
        return count
    groups_count.short_description = _("Zugeordnete Gruppen")
    groups_count.admin_order_field = 'group_statuses'

    def save_model(self, request, obj, form, change):
        if obj.track_file and (not obj.geojson_data or 'track_file' in form.changed_data):
            try:
                gpx = gpxpy.parse(obj.track_file.open())
                from decimal import Decimal
                obj.total_length_km = Decimal(str(round(gpx.length_3d() / 1000.0, 5)))
                points = [[p.latitude, p.longitude] for t in gpx.tracks for s in t.segments for p in s.points]
                obj.geojson_data = json.dumps(points[::5])
            except Exception as e:
                self.message_user(request, f"GPX Fehler: {e}", level='ERROR')
        super().save_model(request, obj, form, change)

    def get_urls(self):
        """Add custom URLs for restart and save_history actions."""
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path('<path:object_id>/restart/', self.admin_site.admin_view(self.restart_trip_view), name='api_traveltrack_restart'),
            path('<path:object_id>/save_history/', self.admin_site.admin_view(self.save_history_view), name='api_traveltrack_save_history'),
        ]
        return custom_urls + urls

    def restart_trip_view(self, request, object_id):
        """Custom view to restart a single trip from detail page."""
        from django.shortcuts import redirect
        from django.contrib import messages
        obj = self.get_object(request, object_id)
        if obj:
            queryset = TravelTrack.objects.filter(pk=obj.pk)
            self.restart_trip(request, queryset)
        return redirect('admin:api_traveltrack_change', object_id)

    def save_history_view(self, request, object_id):
        """Custom view to save trip history from detail page."""
        from django.shortcuts import redirect
        from django.contrib import messages
        obj = self.get_object(request, object_id)
        if obj:
            queryset = TravelTrack.objects.filter(pk=obj.pk)
            self.save_trip_to_history(request, queryset)
        return redirect('admin:api_traveltrack_change', object_id)

    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        extra_context = extra_context or {}
        if object_id:
            try:
                obj = self.get_object(request, object_id)
                if obj:
                    milestones_data = []
                    for milestone in obj.milestones.all():
                        if milestone.gps_latitude and milestone.gps_longitude:
                            milestones_data.append({
                                'name': milestone.name,
                                'lat': float(milestone.gps_latitude),
                                'lon': float(milestone.gps_longitude),
                                'distance': float(milestone.distance_km),
                                'text': milestone.reward_text or ''
                            })
                    extra_context['milestones_json'] = json.dumps(milestones_data, ensure_ascii=False)
                else:
                    extra_context['milestones_json'] = '[]'
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Error loading milestones: {e}")
                extra_context['milestones_json'] = '[]'
        else:
            extra_context['milestones_json'] = '[]'
        return super().changeform_view(request, object_id, form_url, extra_context)

    def restart_trip(self, request, queryset):
        """Restart selected trips by resetting all travel statuses and milestones."""
        from api.models import TravelHistory
        
        count = 0
        for track in queryset:
            # Save current state to history before restarting
            now = timezone.now()
            for status in track.group_statuses.all():
                if status.current_travel_distance > 0:
                    # Find the most recent 'assigned' entry for this track/group to get the correct start_time
                    # This ensures we link to the correct trip instance when a track is run multiple times
                    assigned_entry = TravelHistory.objects.filter(
                        track=track,
                        group=status.group,
                        action_type='assigned'
                    ).order_by('-start_time').first()
                    
                    # Use the start_time from the assigned entry if found, otherwise use track.start_time or current time
                    if assigned_entry:
                        start_time = assigned_entry.start_time
                    else:
                        start_time = track.start_time or now
                    
                    TravelHistory.objects.create(
                        track=track,
                        group=status.group,
                        start_time=start_time,
                        end_time=now,
                        total_distance_km=status.current_travel_distance,
                        action_type='restarted'
                    )
            # Restart the trip
            track.restart_trip()
            count += 1
        self.message_user(request, f"Successfully restarted {count} trip(s). Previous progress saved to history.")
    restart_trip.short_description = _("Restart trip(s) and save to history")

    def save_trip_to_history(self, request, queryset):
        """Save current trip progress to history without restarting."""
        from api.models import TravelHistory
        
        count = 0
        now = timezone.now()
        for track in queryset:
            for status in track.group_statuses.all():
                if status.current_travel_distance > 0:
                    # Find the most recent 'assigned' entry for this track/group to get the correct start_time
                    # This ensures we link to the correct trip instance when a track is run multiple times
                    assigned_entry = TravelHistory.objects.filter(
                        track=track,
                        group=status.group,
                        action_type='assigned'
                    ).order_by('-start_time').first()
                    
                    # Use the start_time from the assigned entry if found, otherwise use track.start_time or current time
                    if assigned_entry:
                        start_time = assigned_entry.start_time
                    else:
                        start_time = track.start_time or now
                    
                    TravelHistory.objects.create(
                        track=track,
                        group=status.group,
                        start_time=start_time,
                        end_time=now,
                        total_distance_km=status.current_travel_distance,
                        action_type='completed'
                    )
                    count += 1
        self.message_user(request, f"Saved {count} trip progress entries to history.")
    save_trip_to_history.short_description = _("Save trip progress to history")

    class Media:
        css = LEAFLET_ASSETS['css']
        js = LEAFLET_ASSETS['js']

@admin.register(Milestone)
class MilestoneAdmin(admin.ModelAdmin):
    form = MilestoneAdminForm
    list_display = ('name', 'distance_km_display', 'track', 'winner_group', 'reached_at', 'deletion_warning')
    list_filter = ('track', 'winner_group', 'reached_at')
    search_fields = ('name', 'track__name', 'winner_group__name', 'description')
    formfield_overrides = {models.DecimalField: {'widget': MapInputWidget}}
    readonly_fields = ('reached_at',)
    fieldsets = (
        (_('Grundinformationen'), {
            'fields': ('track', 'name', 'distance_km', 'gps_latitude', 'gps_longitude')
        }),
        (_('Beschreibung & Links'), {
            'fields': ('description', 'external_link', 'reward_text'),
            'description': _('Beschreibung (max. 500 Zeichen) und externe Links werden in den Milestone-Details angezeigt. Die Beschreibung wird im Overlay mit maximal 200px Höhe angezeigt.')
        }),
        (_('Status'), {
            'fields': ('winner_group', 'reached_at'),
            'classes': ('collapse',)
        }),
    )

    def distance_km_display(self, obj):
        """Display distance_km with German format (comma decimal)."""
        if obj.distance_km is None:
            return format_km_de(0)
        return format_km_de(obj.distance_km)
    distance_km_display.short_description = _("KM-Marke")
    distance_km_display.admin_order_field = 'distance_km'

    def deletion_warning(self, obj):
        """Display warning if milestone is used in a trip."""
        if obj.pk and obj.track_id:
            from django.utils.safestring import mark_safe
            return mark_safe('<span style="color: #ba2121; font-weight: bold;">⚠️ {}</span>'.format(_("In Reise verwendet")))
        return ""
    deletion_warning.short_description = _("Warnung")
    deletion_warning.admin_order_field = 'track'

    def has_delete_permission(self, request, obj=None):
        """Prevent deletion if milestone is used in a trip."""
        if obj and obj.pk and obj.track_id:
            return False
        return super().has_delete_permission(request, obj)

    class Media:
        css = LEAFLET_ASSETS['css']
        js = LEAFLET_ASSETS['js']

@admin.register(GroupTravelStatus)
class GroupTravelStatusAdmin(admin.ModelAdmin):
    list_display = ('group', 'track', 'current_travel_distance_display', 'abort_trip_action')
    list_filter = ('track',)
    search_fields = ('group__name', 'track__name')
    actions = ['abort_trip_bulk_action']
    readonly_fields = ('leaf_groups_contributions_display',)
    
    fieldsets = (
        (_("Reisestatus"), {
            'fields': ('group', 'track', 'current_travel_distance', 'start_km_offset'),
        }),
        (_("Leaf-Gruppen Beiträge"), {
            'fields': ('leaf_groups_contributions_display',),
            'description': _("Ranking der Leaf-Gruppen basierend auf ihrem Beitrag zur Reise der Parent-Gruppe."),
        }),
    )
    
    def leaf_groups_contributions_display(self, obj):
        """Display leaf groups contributions as a table."""
        if not obj or not obj.pk:
            return _("Speichern Sie zuerst den Reisestatus, um die Leaf-Gruppen Beiträge anzuzeigen.")
        
        parent_group = obj.group
        track = obj.track
        
        # Get all leaf groups of the parent group
        leaf_groups = parent_group.get_leaf_groups()
        if not leaf_groups:
            return _("Diese Gruppe hat keine Leaf-Gruppen.")
        
        # Get contributions for all leaf groups
        contributions = LeafGroupTravelContribution.objects.filter(
            track=track,
            leaf_group__in=leaf_groups
        ).select_related('leaf_group').order_by('-current_travel_distance', 'leaf_group__name')
        
        if not contributions.exists():
            return _("Noch keine Beiträge von Leaf-Gruppen vorhanden.")
        
        # Build HTML table
        html = '<table style="width: 100%; border-collapse: collapse;">'
        html += '<thead><tr style="background-color: #f8f9fa; border-bottom: 2px solid #dee2e6;">'
        html += f'<th style="padding: 8px; text-align: left; border: 1px solid #dee2e6;">{_("Rang")}</th>'
        html += f'<th style="padding: 8px; text-align: left; border: 1px solid #dee2e6;">{_("Leaf-Gruppe")}</th>'
        html += f'<th style="padding: 8px; text-align: right; border: 1px solid #dee2e6;">{_("Beitrag (km)")}</th>'
        html += f'<th style="padding: 8px; text-align: right; border: 1px solid #dee2e6;">{_("Anteil")}</th>'
        html += '</tr></thead><tbody>'
        
        parent_distance = obj.current_travel_distance or Decimal('0.00000')
        # IMPORTANT: Cap parent_distance at track total_length_km for consistency with avatar display
        if track.total_length_km and parent_distance > track.total_length_km:
            parent_distance = track.total_length_km
        
        for rank, contrib in enumerate(contributions, start=1):
            # Medal emoji for top 3
            rank_display = ""
            if rank == 1:
                rank_display = "🥇 1"
            elif rank == 2:
                rank_display = "🥈 2"
            elif rank == 3:
                rank_display = "🥉 3"
            else:
                rank_display = str(rank)
            
            # IMPORTANT: Cap contribution at track total_length_km for consistency with avatar display
            contribution_km = contrib.current_travel_distance
            if track.total_length_km and contribution_km > track.total_length_km:
                contribution_km = track.total_length_km
            
            # Calculate percentage
            percentage = ""
            if parent_distance > 0:
                pct = (contribution_km / parent_distance) * 100
                percentage = f"{pct:.1f}%"
            else:
                percentage = "0,0%"
            
            html += '<tr>'
            html += f'<td style="padding: 8px; border: 1px solid #dee2e6;">{rank_display}</td>'
            html += f'<td style="padding: 8px; border: 1px solid #dee2e6;">{contrib.leaf_group.name}</td>'
            html += f'<td style="padding: 8px; text-align: right; border: 1px solid #dee2e6;">{format_km_de(contribution_km)}</td>'
            html += f'<td style="padding: 8px; text-align: right; border: 1px solid #dee2e6;">{percentage}</td>'
            html += '</tr>'
        
        html += '</tbody></table>'
        return mark_safe(html)
    leaf_groups_contributions_display.short_description = _("Leaf-Gruppen Beiträge (Ranking)")

    def current_travel_distance_display(self, obj):
        """Display current_travel_distance with German format (comma decimal)."""
        if obj.current_travel_distance is None:
            return format_km_de(0)
        return format_km_de(obj.current_travel_distance)
    current_travel_distance_display.short_description = _("Aktuelle Reise-Distanz (km)")
    current_travel_distance_display.admin_order_field = 'current_travel_distance'
    
    def abort_trip_action(self, obj):
        """Display abort trip button if group has travel kilometers."""
        if not obj or not obj.pk:
            return ""
        
        if obj.current_travel_distance and obj.current_travel_distance > 0:
            from django.urls import reverse
            abort_url = reverse('admin:api_grouptravelstatus_abort_trip', args=[obj.pk])
            return mark_safe(
                f'<a href="{abort_url}" class="button" '
                f'onclick="return confirm(\'{_("Möchten Sie die Reise für diese Gruppe wirklich abbrechen? Die aktuellen Reisekilometer ({}) gehen verloren.").format(format_km_de(obj.current_travel_distance))}\');">'
                f'{_("Reise abbrechen")}</a>'
            )
        return ""
    abort_trip_action.short_description = _("Aktionen")
    
    def get_urls(self):
        """Add custom URL for abort trip action."""
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path('<path:object_id>/abort_trip/', self.admin_site.admin_view(self.abort_trip_view), name='api_grouptravelstatus_abort_trip'),
        ]
        return custom_urls + urls
    
    def abort_trip_view(self, request, object_id):
        """Custom view to abort a trip for a group with confirmation."""
        from django.shortcuts import redirect, render
        from django.contrib import messages
        from api.models import TravelHistory
        from django.utils import timezone
        
        try:
            status = GroupTravelStatus.objects.get(pk=object_id)
        except GroupTravelStatus.DoesNotExist:
            messages.error(request, _("Reisestatus nicht gefunden."))
            return redirect('admin:api_grouptravelstatus_changelist')
        
        if request.method == 'POST':
            # Confirmed - abort the trip
            # Note: TravelHistory entry will be created by pre_delete signal,
            # but we create it explicitly here to ensure action_type is 'aborted'
            if status.current_travel_distance and status.current_travel_distance > 0:
                # Find the most recent 'assigned' entry for this track/group to get the correct start_time
                # This ensures we link to the correct trip instance when a track is run multiple times
                assigned_entry = TravelHistory.objects.filter(
                    track=status.track,
                    group=status.group,
                    action_type='assigned'
                ).order_by('-start_time').first()
                
                # Use the start_time from the assigned entry if found, otherwise use track.start_time or current time
                abort_time = timezone.now()
                if assigned_entry:
                    start_time = assigned_entry.start_time
                else:
                    start_time = status.track.start_time or abort_time
                
                # Save to history before aborting
                TravelHistory.objects.create(
                    track=status.track,
                    group=status.group,
                    start_time=start_time,
                    end_time=abort_time,
                    total_distance_km=status.current_travel_distance,
                    action_type='aborted'
                )
            
            # Delete the travel status (removes group from trip)
            # The pre_delete signal will also create a history entry, but we've already created one above
            # To avoid duplicates, we'll skip the signal-created entry
            group_name = status.group.name
            track_name = status.track.name
            status._skip_history_creation = True  # Flag to skip signal
            status.delete()
            
            messages.success(
                request,
                _("Reise für Gruppe '{}' wurde abgebrochen. Die Gruppe kann nun einer neuen Reise zugeordnet werden.").format(group_name)
            )
            return redirect('admin:api_grouptravelstatus_changelist')
        
        # GET - Show confirmation page
        context = {
            'title': _("Reise abbrechen"),
            'status': status,
            'group_name': status.group.name,
            'track_name': status.track.name,
            'current_km': format_km_de(status.current_travel_distance) if status.current_travel_distance else format_km_de(0),
            'opts': self.model._meta,
            'has_view_permission': self.has_view_permission(request, status),
            'has_change_permission': self.has_change_permission(request, status),
            'has_delete_permission': self.has_delete_permission(request, status),
        }
        return render(request, 'admin/api/grouptravelstatus_abort_confirmation.html', context)
    
    def abort_trip_bulk_action(self, request, queryset):
        """Admin action to abort trips for selected groups."""
        from api.models import TravelHistory
        from django.utils import timezone
        from django.contrib import messages
        
        aborted_count = 0
        for status in queryset:
            # Note: TravelHistory entry will be created by pre_delete signal,
            # but we create it explicitly here to ensure action_type is 'aborted'
            if status.current_travel_distance and status.current_travel_distance > 0:
                # Find the most recent 'assigned' entry for this track/group to get the correct start_time
                # This ensures we link to the correct trip instance when a track is run multiple times
                assigned_entry = TravelHistory.objects.filter(
                    track=status.track,
                    group=status.group,
                    action_type='assigned'
                ).order_by('-start_time').first()
                
                # Use the start_time from the assigned entry if found, otherwise use track.start_time or current time
                abort_time = timezone.now()
                if assigned_entry:
                    start_time = assigned_entry.start_time
                else:
                    start_time = status.track.start_time or abort_time
                
                # Save to history before aborting
                TravelHistory.objects.create(
                    track=status.track,
                    group=status.group,
                    start_time=start_time,
                    end_time=abort_time,
                    total_distance_km=status.current_travel_distance,
                    action_type='aborted'
                )
            # Skip signal-created entry to avoid duplicates
            status._skip_history_creation = True
            status.delete()
            aborted_count += 1
        
        messages.success(
            request,
            _("{} Reise(n) wurde(n) abgebrochen. Die Gruppen können nun neuen Reisen zugeordnet werden.").format(aborted_count)
        )
    abort_trip_bulk_action.short_description = _("Ausgewählte Reisen abbrechen")

@admin.register(TravelHistory)
class TravelHistoryAdmin(admin.ModelAdmin):
    list_display = ('track', 'group', 'action_type', 'start_time', 'end_time', 'total_distance_km_display', 'travel_duration_display', 'created_at')
    list_filter = ('track', 'group', 'action_type', 'start_time', 'end_time')
    search_fields = ('track__name', 'group__name')
    readonly_fields = ('track', 'group', 'action_type', 'start_time', 'end_time', 'total_distance_km', 'created_at', 'travel_duration_display')
    date_hierarchy = 'end_time'
    
    def has_add_permission(self, request):
        """Prevent adding new history entries."""
        return False
    
    def has_change_permission(self, request, obj=None):
        """Prevent editing history entries."""
        return False

    def total_distance_km_display(self, obj):
        """Display total_distance_km with German format (comma decimal)."""
        if obj.total_distance_km is None:
            return format_km_de(0)
        return format_km_de(obj.total_distance_km)
    total_distance_km_display.short_description = _("Gesammelte Kilometer")
    total_distance_km_display.admin_order_field = 'total_distance_km'
    
    def travel_duration_display(self, obj):
        """Display travel duration from start_time to end_time."""
        if not obj.start_time or not obj.end_time:
            return "-"
        
        travel_duration = obj.end_time - obj.start_time
        total_seconds = int(travel_duration.total_seconds())
        days = total_seconds // 86400
        hours = (total_seconds % 86400) // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        
        # Format: Tage:Stunden:Minuten:Sekunden
        if days > 0:
            return f"{days}:{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    travel_duration_display.short_description = _("Reisezeit")

@admin.register(GroupMilestoneAchievement)
class GroupMilestoneAchievementAdmin(admin.ModelAdmin):
    list_display = ('leaf_group_display', 'top_group_display', 'milestone_display', 'track', 'reached_at', 'reward_text', 'is_redeemed', 'redeemed_at', 'redeem_reward_action')
    list_filter = ('track', 'group', 'milestone', 'is_redeemed', 'reached_at', 'redeemed_at')
    search_fields = ('group__name', 'milestone__name', 'track__name', 'reward_text')
    readonly_fields = ('group', 'milestone_display_detail', 'track', 'reached_at', 'reached_distance', 'reward_text', 'is_redeemed', 'redeemed_at', 'redeem_reward_action')
    date_hierarchy = 'reached_at'
    
    fieldsets = (
        (_("Erreichung"), {
            'fields': ('group', 'milestone_display_detail', 'track', 'reached_at', 'reached_distance'),
            'description': _("Diese Informationen sind historische Daten und können nicht mehr geändert werden. "
                           "Die 'Gruppe' ist die Leaf-Gruppe (z.B. Klasse), die den Meilenstein erreicht hat. "
                           "Die 'Erreichte Distanz' ist die Reise-Distanz dieser Leaf-Gruppe zum Zeitpunkt des Erreichens.")
        }),
        (_("Belohnung"), {
            'fields': ('reward_text', 'is_redeemed', 'redeemed_at'),
            'description': _("Die Belohnung wurde zum Zeitpunkt des Erreichens des Meilensteins gespeichert und bleibt unverändert, auch wenn die Meilenstein-Belohnung später geändert wird.")
        }),
    )

    def leaf_group_display(self, obj):
        """Display the leaf group (the group that actually reached the milestone)."""
        if obj and obj.group:
            return obj.group.name
        return "-"
    leaf_group_display.short_description = _("Gruppe")
    leaf_group_display.admin_order_field = 'group__name'
    
    def top_group_display(self, obj):
        """Display the top parent group (root group in hierarchy)."""
        if obj and obj.group:
            return obj.group.top_parent_name
        return "-"
    top_group_display.short_description = _("Top-Gruppe")
    top_group_display.admin_order_field = 'group__name'
    
    def milestone_display(self, obj):
        """Display milestone name without distance."""
        if obj and obj.milestone:
            return obj.milestone.name
        return "-"
    milestone_display.short_description = _("Meilenstein")
    milestone_display.admin_order_field = 'milestone__name'
    
    def milestone_display_detail(self, obj):
        """Display milestone name without distance in detail view."""
        if obj and obj.milestone:
            return obj.milestone.name
        return "-"
    milestone_display_detail.short_description = _("Meilenstein")
    
    def group_path_display(self, obj):
        """Display the full group path from top to leaf group."""
        if not obj or not obj.group:
            return "-"
        
        # Build path from leaf to top, then reverse
        path_parts = []
        visited = set()
        current = obj.group
        
        # Collect all groups from leaf to top
        while current and current.id not in visited:
            visited.add(current.id)
            path_parts.append(current.name)
            if current.parent:
                current = current.parent
            else:
                break
        
        # Reverse to show top to leaf
        path_parts.reverse()
        
        return " > ".join(path_parts) if path_parts else obj.group.name
    group_path_display.short_description = _("Gruppen-Pfad")
    
    def reached_distance_display(self, obj):
        """Display reached_distance with German format (comma decimal)."""
        if obj.reached_distance is not None:
            return format_km_de(obj.reached_distance)
        return format_km_de(0)
    reached_distance_display.short_description = _("Erreichte Distanz (km)")
    reached_distance_display.admin_order_field = 'reached_distance'
    
    def redeem_reward_action(self, obj):
        """Display button to redeem reward if not already redeemed."""
        if not obj or not obj.pk:
            return ""
        
        # Only show button if reward exists and is not yet redeemed
        if obj.reward_text and obj.reward_text.strip() and not obj.is_redeemed:
            from django.urls import reverse
            redeem_url = reverse('admin:api_groupmilestoneachievement_redeem_reward', args=[obj.pk])
            return mark_safe(
                f'<a href="{redeem_url}" class="button" '
                f'onclick="return confirm(\'{_("Möchten Sie die Belohnung wirklich einlösen?")}\');" '
                f'style="white-space: nowrap; padding: 4px 8px; font-size: 11px; line-height: 1.2;">'
                f'{_("Einlösen")}</a>'
            )
        elif obj.is_redeemed:
            return mark_safe(f'<span style="color: #28a745; white-space: nowrap;">✓ {_("Eingelöst")}</span>')
        elif not obj.reward_text or not obj.reward_text.strip():
            return mark_safe('<span style="color: #6c757d;">-</span>')
        return ""
    redeem_reward_action.short_description = _("Aktionen")
    
    def get_urls(self):
        """Add custom URL for redeem reward action."""
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path('<path:object_id>/redeem_reward/', self.admin_site.admin_view(self.redeem_reward_view), name='api_groupmilestoneachievement_redeem_reward'),
        ]
        return custom_urls + urls
    
    def redeem_reward_view(self, request, object_id):
        """Custom view to redeem a milestone reward."""
        from django.shortcuts import redirect
        from django.contrib import messages
        from api.models import GroupMilestoneAchievement
        from django.utils import timezone
        from django.db import transaction
        
        try:
            achievement = GroupMilestoneAchievement.objects.get(pk=object_id)
        except GroupMilestoneAchievement.DoesNotExist:
            messages.error(request, _("Meilenstein-Erreichung nicht gefunden."))
            return redirect('admin:api_groupmilestoneachievement_changelist')
        
        if request.method == 'POST':
            # Check if already redeemed
            if achievement.is_redeemed:
                messages.warning(request, _("Die Belohnung wurde bereits eingelöst."))
                return redirect('admin:api_groupmilestoneachievement_change', object_id)
            
            # Check if reward exists
            if not achievement.reward_text or achievement.reward_text.strip() == '':
                messages.warning(request, _("Keine Belohnung für diesen Meilenstein definiert."))
                return redirect('admin:api_groupmilestoneachievement_change', object_id)
            
            # Redeem the reward
            with transaction.atomic():
                achievement.is_redeemed = True
                achievement.redeemed_at = timezone.now()
                achievement.save()
            
            messages.success(request, _("Belohnung erfolgreich eingelöst."))
            logger.info(f"[redeem_reward_view] Reward redeemed for achievement {object_id} (group: {achievement.group.name}, milestone: {achievement.milestone.name})")
            return redirect('admin:api_groupmilestoneachievement_change', object_id)
        
        # GET - Show confirmation page
        from django.shortcuts import render
        context = {
            'title': _("Belohnung einlösen"),
            'achievement': achievement,
            'opts': self.model._meta,
            'has_view_permission': self.has_view_permission(request, achievement),
            'has_change_permission': self.has_change_permission(request, achievement),
        }
        return render(request, 'admin/api/groupmilestoneachievement_redeem_confirmation.html', context)
    
    def get_queryset(self, request):
        """Optimize queryset with select_related and prefetch parent groups."""
        qs = super().get_queryset(request)
        return qs.select_related('group', 'group__parent', 'milestone', 'track')

@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('name', 'event_type', 'total_distance_km_display', 'is_active', 'is_visible_on_map', 'start_time', 'end_time', 'hide_after_date')
    list_editable = ('is_active', 'is_visible_on_map')
    inlines = [GroupEventStatusInline]
    fields = ('name', 'event_type', 'description', 'is_active', 'is_visible_on_map', 'start_time', 'end_time', 'hide_after_date')
    list_filter = ('event_type', 'is_active', 'is_visible_on_map')
    search_fields = ('name', 'description')
    actions = ['save_event_to_history']

    def total_distance_km_display(self, obj):
        """Display total kilometers collected in this event with German format."""
        total = obj.get_total_distance_km()
        if total is None:
            return format_km_de(0)
        return format_km_de(total)
    total_distance_km_display.short_description = _("Gesamtkilometer")

    def save_event_to_history(self, request, queryset):
        """Save event progress to history and reset event statuses."""
        count = 0
        for event in queryset:
            event.save_event_to_history()
            count += 1
        self.message_user(request, _("{} Event(s) wurden in die Historie gespeichert und zurückgesetzt.").format(count))
    save_event_to_history.short_description = _("Event(s) in Historie speichern und zurücksetzen")

    def get_urls(self):
        """Add custom URLs for save_history action."""
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path('<path:object_id>/save_history/', self.admin_site.admin_view(self.save_history_view), name='api_event_save_history'),
        ]
        return custom_urls + urls

    def save_history_view(self, request, object_id):
        """Custom view to save event history from detail page."""
        from django.shortcuts import redirect
        from django.contrib import messages
        obj = self.get_object(request, object_id)
        if obj:
            obj.save_event_to_history()
            self.message_user(request, _("Event wurde in die Historie gespeichert und zurückgesetzt."), messages.SUCCESS)
        return redirect('admin:api_event_change', object_id)

# TravelHistory registration moved to after TravelTrack

@admin.register(EventHistory)
class EventHistoryAdmin(admin.ModelAdmin):
    list_display = ('event', 'group', 'start_time', 'end_time', 'total_distance_km_display', 'created_at')
    list_filter = ('event', 'group', 'start_time', 'end_time')
    search_fields = ('event__name', 'group__name')
    readonly_fields = ('event', 'group', 'start_time', 'end_time', 'total_distance_km', 'created_at')
    date_hierarchy = 'end_time'
    
    def has_add_permission(self, request):
        """Prevent adding new history entries."""
        return False
    
    def has_change_permission(self, request, obj=None):
        """Prevent editing history entries."""
        return False
    
    def has_delete_permission(self, request, obj=None):
        """Prevent deleting history entries."""
        return False

    def total_distance_km_display(self, obj):
        """Display total_distance_km with German format (comma decimal)."""
        if obj.total_distance_km is None:
            return format_km_de(0)
        return format_km_de(obj.total_distance_km)
    total_distance_km_display.short_description = _("Gesammelte Kilometer")
    total_distance_km_display.admin_order_field = 'total_distance_km'

@admin.register(HourlyMetric)
class HourlyMetricAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'cyclist', 'distance_km_display', 'device', 'group_at_time')
    readonly_fields = ('device', 'cyclist', 'timestamp', 'distance_km', 'group_at_time')
    list_filter = ('timestamp', 'device', 'cyclist', 'group_at_time')
    search_fields = ('cyclist__name', 'device__name', 'group_at_time__name')
    date_hierarchy = 'timestamp'
    list_per_page = 50
    
    def distance_km_display(self, obj):
        """Display distance_km with German format (comma decimal)."""
        if obj.distance_km is None:
            return format_km_de(0)
        return format_km_de(obj.distance_km)
    distance_km_display.short_description = _("Kilometer")
    distance_km_display.admin_order_field = 'distance_km'
    
    def has_add_permission(self, request):
        """Prevent adding new history entries."""
        return False
    
    def has_change_permission(self, request, obj=None):
        """Prevent editing history entries."""
        return False
    
    def has_delete_permission(self, request, obj=None):
        """Allow deleting hourly metrics."""
        return True

# --- KIOSK MANAGEMENT ---
class KioskPlaylistEntryInline(admin.TabularInline):
    """Inline admin for playlist entries with drag-and-drop ordering support."""
    model = KioskPlaylistEntry
    extra = 0  # Don't show empty forms by default - user must click "Add another"
    fields = ('order', 'view_type', 'event_filter', 'group_filter', 'track_filter', 'display_duration', 'is_active')
    ordering = ('order', 'id')
    verbose_name = _("Playlist Entry")
    verbose_name_plural = _("Playlist Entries")
    can_delete = True
    min_num = 0  # Allow zero entries
    
    def get_extra(self, request, obj=None, **kwargs):
        """Return 0 extra forms - user must explicitly add entries."""
        return 0
    
    def formfield_for_manytomany(self, db_field, request, **kwargs):
        """Use collapsible checkbox widget for track_filter field."""
        if db_field.name == 'track_filter':
            kwargs['widget'] = CollapsibleCheckboxSelectMultiple(attrs={'class': 'collapsible-checkbox'})
        return super().formfield_for_manytomany(db_field, request, **kwargs)
    
    def get_formset(self, request, obj=None, **kwargs):
        """Customize formset to ensure proper saving and auto-assign order starting from 1."""
        from django.forms.models import BaseInlineFormSet
        
        class KioskPlaylistEntryFormSet(BaseInlineFormSet):
            """Custom formset that ensures forms with view_type are saved and auto-assigns order."""
            
            def clean(self):
                """Validate formset, auto-assign order numbers, and ensure order values are unique."""
                if any(self.errors):
                    return
                
                # Get device_id from forms or instance, avoiding recursion
                device_id = None
                for form in self.forms:
                    if hasattr(form, 'instance') and form.instance and hasattr(form.instance, 'device_id'):
                        device_id = form.instance.device_id
                        break
                    elif hasattr(form, 'cleaned_data') and form.cleaned_data and 'device' in form.cleaned_data:
                        device_obj = form.cleaned_data['device']
                        if device_obj and hasattr(device_obj, 'pk'):
                            device_id = device_obj.pk
                            break
                
                # Fallback: get from parent instance if available
                if not device_id and hasattr(self, 'instance') and self.instance and self.instance.pk:
                    device_id = self.instance.pk
                
                # Get existing orders for this device
                # Use direct model query instead of related manager to avoid recursion
                if device_id:
                    from kiosk.models import KioskPlaylistEntry
                    # Exclude forms that are being deleted or updated in this formset
                    exclude_ids = []
                    for form in self.forms:
                        if hasattr(form, 'instance') and form.instance.pk:
                            # Exclude if being deleted
                            if form.cleaned_data and form.cleaned_data.get('DELETE', False):
                                exclude_ids.append(form.instance.pk)
                            # Exclude if being updated (has cleaned_data and not being deleted)
                            elif form.cleaned_data and not form.cleaned_data.get('DELETE', False):
                                exclude_ids.append(form.instance.pk)
                    
                    if exclude_ids:
                        existing_entries = KioskPlaylistEntry.objects.filter(
                            device_id=device_id
                        ).exclude(id__in=exclude_ids)
                    else:
                        existing_entries = KioskPlaylistEntry.objects.filter(
                            device_id=device_id
                        )
                    existing_orders = set(existing_entries.values_list('order', flat=True))
                else:
                    existing_orders = set()
                
                # Find the maximum order number
                max_order = max(existing_orders) if existing_orders else 0
                next_order = max(1, max_order + 1)
                
                # Get parent device for setting device on new entries
                parent_device = None
                if hasattr(self, 'instance') and self.instance:
                    parent_device = self.instance
                
                # Collect orders from forms and auto-assign for new entries
                orders = []
                for form in self.forms:
                    # Skip empty forms (forms that haven't been filled out)
                    if not form.cleaned_data:
                        continue
                    
                    # Skip forms marked for deletion
                    if form.cleaned_data.get('DELETE', False):
                        continue
                    
                    # Skip forms with errors
                    if form.errors:
                        continue
                    
                    # Ensure device is set for new entries
                    if hasattr(form, 'instance') and form.instance:
                        if not form.instance.device_id and parent_device:
                            form.instance.device = parent_device
                            # Also set in cleaned_data for Django's internal processing
                            if 'device' not in form.cleaned_data:
                                form.cleaned_data['device'] = parent_device
                    
                    # Check if this is a new form (no instance pk)
                    is_new = not hasattr(form, 'instance') or not form.instance.pk
                    
                    order = form.cleaned_data.get('order')
                    
                    # Auto-assign order for new entries
                    if is_new and (not order or order == 0):
                        # Find next available order number
                        while next_order in existing_orders or next_order in orders:
                            next_order += 1
                        order = next_order
                        form.cleaned_data['order'] = order
                        # Also update the form instance if it exists
                        if hasattr(form, 'instance'):
                            form.instance.order = order
                        next_order += 1
                    
                    if order is not None and order > 0:
                        if order in orders:
                            raise forms.ValidationError(
                                _("Die Order-Nummer {} ist bereits vergeben. Jede Order-Nummer darf nur einmal pro Gerät verwendet werden.").format(order)
                            )
                        orders.append(order)
                        existing_orders.add(order)
            
            def save(self, commit=True):
                """Override save to ensure order numbers are set correctly and handle deletions."""
                logger.info(f"KioskPlaylistEntryFormSet.save called with commit={commit}")
                logger.info(f"Total forms: {len(self.forms)}")
                
                # Log form details for debugging
                for i, form in enumerate(self.forms):
                    logger.info(f"Form {i}: has_errors={bool(form.errors)}, has_cleaned_data={bool(form.cleaned_data)}, "
                              f"instance_pk={form.instance.pk if form.instance else None}, "
                              f"is_bound={form.is_bound if hasattr(form, 'is_bound') else 'N/A'}")
                    if form.cleaned_data:
                        logger.info(f"Form {i} cleaned_data keys: {list(form.cleaned_data.keys())}")
                    if hasattr(form, 'data') and form.data:
                        # Log relevant form data
                        form_prefix = form.prefix if hasattr(form, 'prefix') else ''
                        view_type_key = f'{form_prefix}-view_type' if form_prefix else 'view_type'
                        if view_type_key in form.data:
                            logger.info(f"Form {i} raw data view_type: {form.data[view_type_key]}")
                
                # Get device from parent instance (required for new entries)
                parent_device = None
                if hasattr(self, 'instance') and self.instance:
                    parent_device = self.instance
                    logger.info(f"Parent device: {parent_device.name if parent_device else None}, PK: {parent_device.pk if parent_device else None}")
                    # Ensure parent has a PK (should be set by Django admin)
                    if not parent_device.pk and commit:
                        # This shouldn't happen, but if it does, we can't save
                        raise ValueError("Parent device must be saved before saving playlist entries")
                
                # First, manually collect instances from forms that have data
                # Django's super().save() might skip forms it considers "unchanged"
                manual_instances = []
                for i, form in enumerate(self.forms):
                    # Skip deleted forms
                    if form in self.deleted_forms:
                        logger.debug(f"Form {i}: Marked for deletion, skipping")
                        continue
                    
                    # Check if form has errors
                    if form.errors:
                        logger.warning(f"Form {i}: Has errors: {form.errors}, skipping")
                        continue
                    
                    # Get instance from form
                    instance = form.instance
                    
                    # Check if form has data - check both cleaned_data and raw POST data
                    has_data = False
                    view_type = None
                    
                    # First check cleaned_data
                    if form.cleaned_data:
                        view_type = form.cleaned_data.get('view_type')
                        if view_type:
                            has_data = True
                            logger.debug(f"Form {i}: Has cleaned_data with view_type={view_type}")
                    
                    # If no cleaned_data, check if instance has view_type set (might be set from POST)
                    if not has_data and instance:
                        # Check if instance has view_type (might be set directly)
                        if hasattr(instance, 'view_type') and instance.view_type:
                            has_data = True
                            view_type = instance.view_type
                            logger.debug(f"Form {i}: Instance has view_type={view_type}")
                        # Also check if this is an existing instance
                        elif instance.pk:
                            has_data = True
                            logger.debug(f"Form {i}: Existing instance with PK={instance.pk}")
                    
                    # If still no data, check form's initial data or POST data
                    if not has_data:
                        # Try to get from form's initial or bound data
                        if hasattr(form, 'initial') and form.initial.get('view_type'):
                            view_type = form.initial.get('view_type')
                            has_data = True
                            logger.debug(f"Form {i}: Has initial data with view_type={view_type}")
                        elif hasattr(form, 'data'):
                            # Check raw form data
                            form_prefix = form.prefix if hasattr(form, 'prefix') else ''
                            view_type_key = f'{form_prefix}-view_type' if form_prefix else 'view_type'
                            if view_type_key in form.data:
                                view_type = form.data[view_type_key]
                                if view_type:
                                    has_data = True
                                    logger.debug(f"Form {i}: Has raw data with view_type={view_type}")
                    
                    if has_data:
                        # Ensure device is set
                        if not instance.device_id and parent_device:
                            instance.device = parent_device
                            logger.debug(f"Form {i}: Set device to parent device")
                        
                        # Set view_type if we found it but it's not on the instance
                        if view_type and not instance.view_type:
                            instance.view_type = view_type
                            logger.debug(f"Form {i}: Set view_type on instance")
                        
                        # Set other fields from cleaned_data if available
                        if form.cleaned_data:
                            for field_name in ['order', 'display_duration', 'is_active', 'event_filter', 'group_filter']:
                                if field_name in form.cleaned_data and form.cleaned_data[field_name] is not None:
                                    setattr(instance, field_name, form.cleaned_data[field_name])
                        
                        manual_instances.append(instance)
                        logger.info(f"Form {i}: Added instance (PK: {instance.pk}, view_type: {instance.view_type}, device_id: {instance.device_id})")
                    else:
                        logger.debug(f"Form {i}: No data found, skipping")
                
                # Also call parent save to get Django's instances (for compatibility)
                instances = super().save(commit=False)
                logger.info(f"Parent save returned {len(instances)} instances")
                
                # Merge manual instances with Django's instances (avoid duplicates)
                all_instances = []
                seen_pks = set()
                for inst in manual_instances + instances:
                    if inst.pk:
                        if inst.pk not in seen_pks:
                            all_instances.append(inst)
                            seen_pks.add(inst.pk)
                    else:
                        # New instance - check if it's a duplicate by comparing fields
                        is_duplicate = False
                        for existing in all_instances:
                            if not existing.pk and existing.device_id == inst.device_id:
                                is_duplicate = True
                                break
                        if not is_duplicate:
                            all_instances.append(inst)
                
                instances = all_instances
                logger.info(f"Total instances to save (before device check): {len(instances)}")
                
                # Ensure device is set for all instances (required for new entries)
                # Filter out instances without device_id
                valid_instances = []
                for instance in instances:
                    if not instance.device_id and parent_device:
                        instance.device = parent_device
                    # Only include instances with device_id
                    if instance.device_id:
                        valid_instances.append(instance)
                    else:
                        logger.warning(f"Skipping playlist entry: no device_id set. Parent device PK: {parent_device.pk if parent_device else None}")
                
                instances = valid_instances
                logger.info(f"Total instances to save (after device check): {len(instances)}")
                
                if not instances:
                    logger.info("No instances to save - returning early")
                    return []
                
                try:
                    # Handle deletions first - delete marked objects
                    if commit:
                        for form in self.deleted_forms:
                            if form.instance.pk:
                                form.instance.delete()
                    
                    # Get device_id from instances or instance, avoiding recursion
                    device_id = None
                    if instances:
                        # Get device_id from first instance
                        device_id = instances[0].device_id if hasattr(instances[0], 'device_id') else None
                        logger.info(f"Got device_id from first instance: {device_id}")
                    elif parent_device and parent_device.pk:
                        # Fallback: get from parent instance
                        device_id = parent_device.pk
                        logger.info(f"Got device_id from parent device: {device_id}")
                    else:
                        logger.warning("No device_id found!")
                    
                    # Get existing orders for this device (excluding instances being deleted or updated)
                    # Use direct model query instead of related manager to avoid recursion
                    if device_id:
                        # Exclude instances that are being deleted or updated
                        deleted_ids = [form.instance.pk for form in self.deleted_forms if form.instance.pk]
                        updated_ids = [inst.id for inst in instances if inst.pk]
                        exclude_ids = deleted_ids + updated_ids
                        logger.info(f"Excluding IDs: {exclude_ids}")
                        
                        # Query directly via model to avoid recursion through related manager
                        from kiosk.models import KioskPlaylistEntry
                        if exclude_ids:
                            existing_entries = KioskPlaylistEntry.objects.filter(
                                device_id=device_id
                            ).exclude(id__in=exclude_ids)
                        else:
                            existing_entries = KioskPlaylistEntry.objects.filter(
                                device_id=device_id
                            )
                        existing_orders = set(existing_entries.values_list('order', flat=True))
                        logger.info(f"Existing orders: {existing_orders}")
                    else:
                        existing_orders = set()
                        logger.info("No device_id, using empty existing_orders")
                    
                    # Collect all orders that will be used (from existing entries)
                    used_orders = set(existing_orders)
                    
                    # First pass: collect orders from instances that already have them set
                    # and check for duplicates within the instances being saved
                    # Use index as key since instances without PK are not hashable
                    instance_orders = {}
                    for idx, instance in enumerate(instances):
                        # Get order value safely (might be None or 0)
                        current_order = getattr(instance, 'order', None)
                        if current_order and current_order > 0:
                            # Check if this order is already used by another instance in this batch
                            if current_order in instance_orders.values():
                                # Duplicate order found within batch - mark for reassignment
                                instance.order = None
                                logger.info(f"Instance {idx} has duplicate order {current_order}, marking for reassignment")
                            else:
                                instance_orders[idx] = current_order
                                # Check if order conflicts with existing entries
                                if current_order in used_orders:
                                    # Conflict with existing entry - mark for reassignment
                                    instance.order = None
                                    logger.info(f"Instance {idx} order {current_order} conflicts with existing, marking for reassignment")
                                else:
                                    used_orders.add(current_order)
                    
                    # Find the maximum order number
                    max_order = max(used_orders) if used_orders else 0
                    logger.info(f"Max order: {max_order}, used_orders: {used_orders}")
                    
                    # Second pass: auto-assign order numbers for instances that don't have one or had conflicts
                    for instance in instances:
                        current_order = getattr(instance, 'order', None)
                        if not current_order or current_order == 0:
                            # Find next available order number
                            next_order = max(1, max_order + 1)
                            while next_order in used_orders:
                                next_order += 1
                            instance.order = next_order
                            used_orders.add(next_order)
                            max_order = max(max_order, next_order)
                            logger.info(f"Assigned order {next_order} to instance (PK: {instance.pk}, view_type: {instance.view_type})")
                    
                    logger.info(f"Before commit: {len(instances)} instances ready to save")
                    for i, instance in enumerate(instances):
                        logger.debug(f"Instance {i}: PK={instance.pk}, device_id={instance.device_id}, view_type={instance.view_type}, order={instance.order}")
                except Exception as e:
                    logger.error(f"Error in order assignment logic: {e}", exc_info=True)
                    raise
                
                if commit:
                    # Save all instances in a transaction to ensure atomicity
                    try:
                        with transaction.atomic():
                            saved_instances = []
                            for instance in instances:
                                # Only save instances that have a device set and are not empty
                                if not instance.device_id:
                                    logger.warning(f"Skipping playlist entry: no device_id. Instance: {instance}")
                                    continue
                                
                                # Ensure view_type is set (required field)
                                if not instance.view_type:
                                    logger.warning(f"Skipping playlist entry: missing view_type. Device: {instance.device_id}")
                                    continue
                                
                                try:
                                    logger.info(f"Saving playlist entry: PK={instance.pk}, device_id={instance.device_id}, view_type={instance.view_type}, order={instance.order}")
                                    instance.save()
                                    saved_instances.append(instance)
                                    logger.info(f"Successfully saved playlist entry: PK={instance.pk}")
                                except Exception as e:
                                    logger.error(f"Error saving playlist entry: {e}. Instance: {instance}, device_id: {instance.device_id}, view_type: {instance.view_type}", exc_info=True)
                                    raise
                            
                            # Only save M2M if we have saved instances
                            if saved_instances:
                                logger.info(f"Saving M2M relationships for {len(saved_instances)} instances")
                                self.save_m2m()
                            else:
                                logger.warning("No instances were saved - M2M save skipped")
                    except Exception as e:
                        logger.error(f"Error in playlist formset save: {e}", exc_info=True)
                        raise
                
                return instances
        
        kwargs['formset'] = KioskPlaylistEntryFormSet
        return super().get_formset(request, obj, **kwargs)


@admin.register(KioskDevice)
class KioskDeviceAdmin(RetryOnDbLockMixin, admin.ModelAdmin):
    list_display = ('name', 'uid', 'is_active', 'brightness', 'playlist_count', 'playlist_url', 'pending_commands_count', 'updated_at')
    list_editable = ('is_active', 'brightness')
    search_fields = ('name', 'uid')
    fieldsets = (
        (_("Device Information"), {
            'fields': ('name', 'uid', 'is_active')
        }),
        (_("Hardware Control"), {
            'fields': ('brightness', 'command_queue'),
            'description': _("Brightness: 0-100. Command Queue: JSON array of pending commands (e.g., ['RELOAD', 'SET_BRIGHTNESS:50', 'REBOOT'])")
        }),
        (_("Timestamps"), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    readonly_fields = ('created_at', 'updated_at', 'command_queue')
    inlines = [KioskPlaylistEntryInline]
    
    def changelist_view(self, request, extra_context=None):
        """Store request for use in list_display methods."""
        self._request = request
        return super().changelist_view(request, extra_context)
    
    def playlist_count(self, obj):
        """Display number of active playlist entries."""
        return obj.playlist_entries.filter(is_active=True).count()
    playlist_count.short_description = _("Aktive Einträge")
    
    def playlist_url(self, obj):
        """Display the URL to access the kiosk playlist page."""
        if not obj.pk:
            return "-"
        try:
            from django.urls import reverse
            from django.utils.safestring import mark_safe
            
            # Build relative URL
            relative_url = reverse('kiosk:kiosk_playlist_page', args=[obj.uid])
            
            # Get request from stored reference
            request = getattr(self, '_request', None)
            
            # Build absolute URL if we have request info
            if request:
                absolute_url = request.build_absolute_uri(relative_url)
                return mark_safe(f'<a href="{absolute_url}" target="_blank">{absolute_url}</a>')
            else:
                # Fallback: use relative URL
                return mark_safe(f'<a href="{relative_url}" target="_blank">{relative_url}</a>')
        except Exception as e:
            return f"- ({str(e)})"
    playlist_url.short_description = _("Playlist URL")
    
    def pending_commands_count(self, obj):
        """Display number of pending commands."""
        if isinstance(obj.command_queue, list):
            return len(obj.command_queue)
        return 0
    pending_commands_count.short_description = _("Ausstehende Befehle")
    
    def get_urls(self):
        """Add custom URLs for remote actions."""
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path('<path:object_id>/reload/', self.admin_site.admin_view(self.reload_device_view), name='kiosk_kioskdevice_reload'),
            path('<path:object_id>/reboot/', self.admin_site.admin_view(self.reboot_device_view), name='kiosk_kioskdevice_reboot'),
            path('<path:object_id>/set_brightness/<int:brightness>/', self.admin_site.admin_view(self.set_brightness_view), name='kiosk_kioskdevice_set_brightness'),
        ]
        return custom_urls + urls
    
    def reload_device_view(self, request, object_id):
        """Trigger a remote reload on the device."""
        from django.shortcuts import redirect
        from django.contrib import messages
        obj = self.get_object(request, object_id)
        if obj:
            obj.add_command('RELOAD')
            messages.success(request, _("Reload command queued for device '{}'.").format(obj.name))
        return redirect('admin:kiosk_kioskdevice_change', object_id)
    
    def reboot_device_view(self, request, object_id):
        """Trigger a remote reboot on the device."""
        from django.shortcuts import redirect
        from django.contrib import messages
        obj = self.get_object(request, object_id)
        if obj:
            obj.add_command('REBOOT')
            messages.success(request, _("Reboot command queued for device '{}'.").format(obj.name))
        return redirect('admin:kiosk_kioskdevice_change', object_id)
    
    def set_brightness_view(self, request, object_id, brightness):
        """Trigger a remote brightness change on the device."""
        from django.shortcuts import redirect
        from django.contrib import messages
        obj = self.get_object(request, object_id)
        if obj:
            obj.add_command(f'SET_BRIGHTNESS:{brightness}')
            messages.success(request, _("Set brightness command queued for device '{}' to {}%.").format(obj.name, brightness))
        return redirect('admin:kiosk_kioskdevice_change', object_id)
    
    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        """Add action buttons to the change form."""
        extra_context = extra_context or {}
        if object_id:
            obj = self.get_object(request, object_id)
            if obj:
                extra_context['action_buttons'] = [
                    {
                        'label': _("Reload Device"),
                        'url': f'admin:kiosk_kioskdevice_reload',
                        'class': 'default',
                    },
                    {
                        'label': _("Reboot Device"),
                        'url': f'admin:kiosk_kioskdevice_reboot',
                        'class': 'default',
                    },
                    {
                        'label': _("Set Brightness: 50%"),
                        'url': f'admin:kiosk_kioskdevice_set_brightness',
                        'params': {'brightness': 50},
                        'class': 'default',
                    },
                    {
                        'label': _("Set Brightness: 100%"),
                        'url': f'admin:kiosk_kioskdevice_set_brightness',
                        'params': {'brightness': 100},
                        'class': 'default',
                    },
                ]
        return super().changeform_view(request, object_id, form_url, extra_context)


# --- IOT MANAGEMENT ---
@admin.register(Device)
class DeviceAdmin(RetryOnDbLockMixin, BaseAdmin):
    list_display = ('display_name', 'name', 'group', 'distance_total_display', 'config_status', 'is_visible', 'is_km_collection_enabled')
    list_display_links = ('name',)
    list_editable = ('display_name', 'is_visible', 'is_km_collection_enabled')
    fields = ('name', 'display_name', 'group', 'is_visible', 'is_km_collection_enabled', 'distance_total', 'gps_latitude', 'gps_longitude', 'last_active', 'comments')
    formfield_overrides = {models.DecimalField: {'widget': MapInputWidget}}
    inlines = [DeviceConfigurationInline, DeviceConfigurationReportInline]

    def distance_total_display(self, obj):
        """Display distance_total with German format (comma decimal)."""
        if obj.distance_total is None:
            return format_km_de(0)
        return format_km_de(obj.distance_total)
    distance_total_display.short_description = _("Gesamtkilometer")
    distance_total_display.admin_order_field = 'distance_total'

    def config_status(self, obj):
        """Display configuration status with differences indicator."""
        try:
            config = obj.configuration
            unresolved_diffs = obj.configuration_diffs.filter(is_resolved=False).count()
            if unresolved_diffs > 0:
                return mark_safe(f'<span style="color: red;">⚠️ {unresolved_diffs} Unterschiede</span>')
            elif config.last_synced_at:
                return mark_safe(f'<span style="color: green;">✓ Synchronisiert</span>')
            else:
                return mark_safe('<span style="color: orange;">⚠ Nicht synchronisiert</span>')
        except DeviceConfiguration.DoesNotExist:
            return mark_safe('<span style="color: gray;">- Keine Konfiguration</span>')
    config_status.short_description = _("Konfigurationsstatus")

    class Media:
        css = LEAFLET_ASSETS['css']
        js = LEAFLET_ASSETS['js']


# --- DEVICE MANAGEMENT ADMIN ---

class DeviceConfigurationDiffInline(admin.TabularInline):
    """Inline differences for Configuration Report."""
    model = DeviceConfigurationDiff
    extra = 0
    readonly_fields = ('field_name', 'server_value', 'device_value', 'created_at', 'is_resolved', 'resolved_at')
    fields = ('field_name', 'server_value', 'device_value', 'is_resolved', 'resolved_at')
    can_delete = False


@admin.register(DeviceConfigurationReport)
class DeviceConfigurationReportAdmin(admin.ModelAdmin):
    list_display = ('device', 'created_at', 'has_differences', 'diff_count')
    list_filter = ('has_differences', 'created_at', 'device')
    search_fields = ('device__name', 'device__display_name')
    readonly_fields = ('device', 'reported_config', 'has_differences', 'created_at')
    inlines = [DeviceConfigurationDiffInline]
    
    fieldsets = (
        (_("Berichts-Informationen"), {
            'fields': ('device', 'created_at', 'has_differences')
        }),
        (_("Gemeldete Konfiguration"), {
            'fields': ('reported_config',),
            'classes': ('collapse',)
        }),
    )
    
    def diff_count(self, obj):
        """Display number of differences."""
        count = obj.diffs.filter(is_resolved=False).count()
        if count > 0:
            return mark_safe(f'<span style="color: red;">{count} Unterschiede</span>')
        return "0"
    diff_count.short_description = _("Offene Unterschiede")


@admin.register(DeviceConfigurationDiff)
class DeviceConfigurationDiffAdmin(admin.ModelAdmin):
    list_display = ('device', 'field_name', 'server_value_preview', 'device_value_preview', 'is_resolved', 'created_at')
    list_filter = ('is_resolved', 'created_at', 'device')
    search_fields = ('device__name', 'field_name')
    readonly_fields = ('device', 'report', 'field_name', 'server_value', 'device_value', 'created_at')
    list_editable = ('is_resolved',)
    
    fieldsets = (
        (_("Unterschieds-Informationen"), {
            'fields': ('device', 'report', 'field_name', 'created_at', 'is_resolved', 'resolved_at')
        }),
        (_("Werte"), {
            'fields': ('server_value', 'device_value')
        }),
    )
    
    def server_value_preview(self, obj):
        """Display server value with truncation."""
        if obj.server_value:
            value = str(obj.server_value)
            if len(value) > 30:
                return value[:30] + '...'
            return value
        return '-'
    server_value_preview.short_description = _("Server-Wert")
    
    def device_value_preview(self, obj):
        """Display device value with truncation."""
        if obj.device_value:
            value = str(obj.device_value)
            if len(value) > 30:
                return value[:30] + '...'
            return value
        return '-'
    device_value_preview.short_description = _("Geräte-Wert")
    
    def save_model(self, request, obj, form, change):
        """Mark resolved_at when is_resolved is set to True."""
        if change and 'is_resolved' in form.changed_data:
            if obj.is_resolved and not obj.resolved_at:
                obj.resolved_at = timezone.now()
            elif not obj.is_resolved:
                obj.resolved_at = None
        super().save_model(request, obj, form, change)


@admin.register(FirmwareImage)
class FirmwareImageAdmin(admin.ModelAdmin):
    list_display = ('name', 'version', 'is_stable', 'is_active', 'file_size_display', 'assigned_devices_count', 'created_at')
    list_filter = ('is_stable', 'is_active', 'created_at')
    search_fields = ('name', 'version', 'description')
    list_editable = ('is_stable', 'is_active')
    readonly_fields = ('file_size', 'checksum_md5', 'created_at', 'updated_at')
    
    fieldsets = (
        (_("Firmware-Informationen"), {
            'fields': ('name', 'version', 'description', 'is_stable', 'is_active')
        }),
        (_("Firmware-Datei"), {
            'fields': ('firmware_file', 'file_size', 'checksum_md5')
        }),
        (_("Zeitstempel"), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def file_size_display(self, obj):
        """Display file size in human-readable format."""
        if obj.file_size:
            size_kb = obj.file_size / 1024
            if size_kb < 1024:
                return f"{size_kb:.1f} KB"
            else:
                size_mb = size_kb / 1024
                return f"{size_mb:.1f} MB"
        return "-"
    file_size_display.short_description = _("Dateigröße")
    
    def assigned_devices_count(self, obj):
        """Display number of devices assigned to this firmware."""
        count = obj.assigned_devices.count()
        return count
    assigned_devices_count.short_description = _("Zugewiesene Geräte")


@admin.register(MapPopupSettings)
class MapPopupSettingsAdmin(admin.ModelAdmin):
    """Singleton admin for map popup display time settings."""
    list_display = ('weltmeister_popup_duration_seconds', 'milestone_popup_duration_seconds', 'updated_at')
    
    fieldsets = (
        (_("Popup-Dauer"), {
            'fields': ('weltmeister_popup_duration_seconds', 'milestone_popup_duration_seconds'),
            'description': _("Anzeigedauer der Popups in Sekunden (1-300)")
        }),
        (_("Kilometer-Weltmeister Popup Styling"), {
            'fields': ('weltmeister_popup_background_color', 'weltmeister_popup_bg_color_preview', 'weltmeister_popup_background_color_end', 'weltmeister_popup_bg_color_end_preview', 'weltmeister_popup_opacity'),
            'description': mark_safe(_("Hintergrundfarbe und Transparenz des Kilometer-Weltmeister Popups. "
                           "Verwenden Sie einen <a href='https://htmlcolorcodes.com/color-picker/' target='_blank'>Farbwähler</a> "
                           "oder <a href='https://colorpicker.me/' target='_blank'>Color Picker</a> "
                           "um den Hex-Code zu ermitteln."))
        }),
        (_("Meilenstein Popup Styling"), {
            'fields': ('milestone_popup_background_color', 'milestone_popup_bg_color_preview', 'milestone_popup_opacity'),
            'description': mark_safe(_("Hintergrundfarbe und Transparenz des Meilenstein Popups. "
                           "Verwenden Sie einen <a href='https://htmlcolorcodes.com/color-picker/' target='_blank'>Farbwähler</a> "
                           "oder <a href='https://colorpicker.me/' target='_blank'>Color Picker</a> "
                           "um den Hex-Code zu ermitteln."))
        }),
        (_("Zeitstempel"), {
            'fields': ('updated_at',),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ('updated_at', 'weltmeister_popup_bg_color_preview', 'weltmeister_popup_bg_color_end_preview', 'milestone_popup_bg_color_preview')
    
    def weltmeister_popup_bg_color_preview(self, obj):
        """Generates a color preview for the weltmeister popup background color"""
        if obj and obj.weltmeister_popup_background_color and obj.weltmeister_popup_background_color.strip():
            color_value = obj.weltmeister_popup_background_color.strip()
            # Validate hex color format (basic check)
            if not color_value.startswith('#'):
                color_value = '#' + color_value
            return mark_safe(
                f'<div style="width: 60px; height: 40px; background-color: {color_value}; '
                f'border: 2px solid #333; border-radius: 4px; display: inline-block; vertical-align: middle;"></div> '
                f'<span style="margin-left: 10px; vertical-align: middle; font-weight: bold;">{color_value}</span>'
            )
        return mark_safe(_("Keine Farbe definiert"))
    weltmeister_popup_bg_color_preview.short_description = _("Farbvorschau (Start)")
    
    def weltmeister_popup_bg_color_end_preview(self, obj):
        """Generates a color preview for the weltmeister popup background color end (gradient)"""
        if obj and obj.weltmeister_popup_background_color_end and obj.weltmeister_popup_background_color_end.strip():
            color_value = obj.weltmeister_popup_background_color_end.strip()
            # Validate hex color format (basic check)
            if not color_value.startswith('#'):
                color_value = '#' + color_value
            return mark_safe(
                f'<div style="width: 60px; height: 40px; background-color: {color_value}; '
                f'border: 2px solid #333; border-radius: 4px; display: inline-block; vertical-align: middle;"></div> '
                f'<span style="margin-left: 10px; vertical-align: middle; font-weight: bold;">{color_value}</span>'
            )
        return mark_safe(_("Keine Farbe definiert"))
    weltmeister_popup_bg_color_end_preview.short_description = _("Farbvorschau (Ende)")
    
    def milestone_popup_bg_color_preview(self, obj):
        """Generates a color preview for the milestone popup background color"""
        if obj and obj.milestone_popup_background_color and obj.milestone_popup_background_color.strip():
            color_value = obj.milestone_popup_background_color.strip()
            # Validate hex color format (basic check)
            if not color_value.startswith('#'):
                color_value = '#' + color_value
            return mark_safe(
                f'<div style="width: 60px; height: 40px; background-color: {color_value}; '
                f'border: 2px solid #333; border-radius: 4px; display: inline-block; vertical-align: middle;"></div> '
                f'<span style="margin-left: 10px; vertical-align: middle; font-weight: bold;">{color_value}</span>'
            )
        return mark_safe(_("Keine Farbe definiert"))
    milestone_popup_bg_color_preview.short_description = _("Farbvorschau")
    
    def has_add_permission(self, request):
        """Only allow one settings instance."""
        return not MapPopupSettings.objects.exists()
    
    def has_delete_permission(self, request, obj=None):
        """Prevent deletion of settings."""
        return False
    
    def changelist_view(self, request, extra_context=None):
        """Redirect to the single settings object if it exists."""
        settings_obj = MapPopupSettings.get_settings()
        return self.change_view(request, str(settings_obj.pk), extra_context)

@admin.register(DeviceManagementSettings)
class DeviceManagementSettingsAdmin(admin.ModelAdmin):
    """Singleton admin for device management settings."""
    
    def has_add_permission(self, request):
        """Only allow one settings instance."""
        return not DeviceManagementSettings.objects.exists()
    
    def has_delete_permission(self, request, obj=None):
        """Prevent deletion of settings."""
        return False
    
    list_display = ('email_notifications_enabled', 'notification_email', 'last_notification_sent', 'updated_at')
    fieldsets = (
        (_("E-Mail-Benachrichtigungen"), {
            'fields': ('email_notifications_enabled', 'notification_email', 'last_notification_sent'),
            'description': _("Konfigurieren Sie tägliche E-Mail-Benachrichtigungen für Gerätekonfigurationsunterschiede.")
        }),
        (_("Zeitstempel"), {
            'fields': ('updated_at',),
            'classes': ('collapse',)
        }),
    )
    readonly_fields = ('last_notification_sent', 'updated_at')
    
    def changelist_view(self, request, extra_context=None):
        """Redirect to the single settings object if it exists."""
        settings_obj = DeviceManagementSettings.get_settings()
        return self.change_view(request, str(settings_obj.pk), extra_context)


# --- ADDITIONAL DEVICE MANAGEMENT ADMIN ---

@admin.register(DeviceHealth)
class DeviceHealthAdmin(admin.ModelAdmin):
    list_display = ('device', 'status', 'last_heartbeat', 'consecutive_failures', 'is_offline_display', 'updated_at')
    list_filter = ('status', 'updated_at')
    search_fields = ('device__name', 'device__display_name')
    readonly_fields = ('device', 'status', 'last_heartbeat', 'consecutive_failures', 'last_error_message', 'updated_at', 'is_offline_display')
    
    fieldsets = (
        (_("Geräte-Informationen"), {
            'fields': ('device',)
        }),
        (_("Gesundheitsstatus"), {
            'fields': ('status', 'last_heartbeat', 'is_offline_display', 'consecutive_failures', 'last_error_message')
        }),
        (_("Konfiguration"), {
            'fields': ('heartbeat_interval_seconds', 'offline_threshold_seconds')
        }),
        (_("Zeitstempel"), {
            'fields': ('updated_at',),
            'classes': ('collapse',)
        }),
    )
    
    def is_offline_display(self, obj):
        """Display offline status."""
        if obj.is_offline():
            return mark_safe('<span style="color: red;">⚠ Offline</span>')
        return mark_safe('<span style="color: green;">✓ Online</span>')
    is_offline_display.short_description = _("Online-Status")


@admin.register(ConfigTemplate)
class ConfigTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'created_at', 'updated_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name', 'description')
    list_editable = ('is_active',)
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        (_("Template-Informationen"), {
            'fields': ('name', 'description', 'is_active')
        }),
        (_("Template-Konfiguration"), {
            'fields': ('template_config',),
            'description': _("JSON-Objekt mit Konfigurationswerten. Beispiel: {'send_interval_seconds': 60, 'wheel_size': 26}")
        }),
        (_("Zeitstempel"), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(DeviceAuditLog)
class DeviceAuditLogAdmin(admin.ModelAdmin):
    list_display = ('device', 'action', 'user', 'ip_address', 'created_at')
    list_filter = ('action', 'created_at', 'device')
    search_fields = ('device__name', 'user__username', 'ip_address')
    readonly_fields = ('device', 'action', 'user', 'details', 'ip_address', 'created_at')
    
    fieldsets = (
        (_("Protokoll-Informationen"), {
            'fields': ('device', 'action', 'user', 'ip_address', 'created_at')
        }),
        (_("Details"), {
            'fields': ('details',),
            'classes': ('collapse',)
        }),
    )
    
    def has_add_permission(self, request):
        """Prevent manual creation of audit logs."""
        return False


@admin.register(WebhookConfiguration)
class WebhookConfigurationAdmin(admin.ModelAdmin):
    list_display = ('name', 'url', 'is_active', 'events_count', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name', 'url')
    list_editable = ('is_active',)
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        (_("Webhook-Informationen"), {
            'fields': ('name', 'url', 'is_active')
        }),
        (_("Konfiguration"), {
            'fields': ('events', 'secret_key'),
            'description': _("Wählen Sie Ereignisse aus, die diesen Webhook auslösen sollen. Geheimer Schlüssel ist optional für die Authentifizierung.")
        }),
        (_("Zeitstempel"), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def events_count(self, obj):
        """Display number of configured events."""
        if isinstance(obj.events, list):
            return len(obj.events)
        return 0
    events_count.short_description = _("Ereignisse")


# Add custom view for API key generation
@admin.register(DeviceConfiguration)
class DeviceConfigurationAdmin(admin.ModelAdmin):
    """Standalone admin for DeviceConfiguration with API key generation."""
    
    readonly_fields = ('reported_device_name_display', 'api_key_last_rotated', 'generate_api_key_button', 'test_rotation_button', 'force_rotation_button')
    exclude = ('apache_base64_auth_key', 'device_name')  # Remove deprecated Apache Base64 Auth Key field and device_name (use reported name instead)
    
    fieldsets = (
        (_("API-Key-Verwaltung"), {
            'fields': ('device_specific_api_key', 'api_key_rotation_enabled', 'api_key_rotation_interval_days', 'api_key_last_rotated', 'generate_api_key_button', 'test_rotation_button', 'force_rotation_button'),
            'description': _("Gerätespezifischer API-Key für sichere Authentifizierung. Verwenden Sie 'API-Key generieren' für sofortige Erneuerung, 'Rotation jetzt ausführen' um die Rotation manuell zu triggern, oder 'Rotation testen' um die automatische Rotation zu prüfen.")
        }),
        (_("Geräte-Identifikation"), {
            'fields': ('reported_device_name_display', 'default_id_tag'),
            'description': _("Der Gerätename wird vom Gerät gemeldet und ist schreibgeschützt. Der Standard-ID-Tag kann konfiguriert werden.")
        }),
        (_("Kommunikation"), {
            'fields': ('send_interval_seconds', 'server_url')
        }),
        (_("WLAN-Einstellungen"), {
            'fields': ('wifi_ssid', 'wifi_password'),
            'classes': ('collapse',)
        }),
        (_("Config-WLAN-Einstellungen"), {
            'fields': ('ap_password',),
            'classes': ('collapse',),
            'description': _("Passwort für den Config-WLAN-Hotspot. Minimum 8 Zeichen erforderlich (WPA2-Anforderung).")
        }),
        (_("Geräte-Verhalten"), {
            'fields': ('debug_mode', 'test_mode', 'deep_sleep_seconds', 'config_fetch_interval_seconds', 'request_config_comparison')
        }),
        (_("Hardware"), {
            'fields': ('wheel_size',)
        }),
        (_("Firmware"), {
            'fields': ('assigned_firmware', 'last_synced_at')
        }),
    )
    
    def reported_device_name_display(self, obj):
        """Display device name as reported by the device (not from database)."""
        if obj:
            reported_name = obj.get_reported_device_name()
            if reported_name:
                return reported_name
            return _("Noch nicht vom Gerät gemeldet")
        return "-"
    reported_device_name_display.short_description = _("Gerätename (vom Gerät gemeldet)")
    
    def generate_api_key_button(self, obj):
        """Display button to generate API key."""
        if obj and obj.pk:
            from django.utils.html import format_html
            from django.urls import reverse
            url = reverse('admin:iot_deviceconfiguration_generate_api_key', args=[obj.pk])
            return format_html(
                '<a class="button" href="{}" onclick="return confirm(\'Sind Sie sicher, dass Sie einen neuen API-Key generieren möchten? Der alte Key wird ungültig.\');">API-Key generieren</a>',
                url
            )
        return _("Speichern Sie zuerst die Gerätekonfiguration, um einen API-Key zu generieren")
    generate_api_key_button.short_description = _("API-Key-Aktionen")
    
    def test_rotation_button(self, obj):
        """Display button to test API key rotation."""
        if obj and obj.pk:
            from django.utils.html import format_html
            from django.urls import reverse
            url = reverse('admin:iot_deviceconfiguration_test_rotation', args=[obj.pk])
            return format_html(
                '<a class="button" href="{}" onclick="return confirm(\'Möchten Sie die API-Key-Rotation jetzt testen? Dies prüft, ob die Rotation aktiviert ist und ob das Intervall erreicht wurde.\');">Rotation testen</a>',
                url
            )
        return _("Speichern Sie zuerst die Gerätekonfiguration, um die Rotation zu testen")
    test_rotation_button.short_description = _("Rotation testen")
    
    def force_rotation_button(self, obj):
        """Display button to force API key rotation immediately."""
        if obj and obj.pk:
            from django.utils.html import format_html
            from django.urls import reverse
            url = reverse('admin:iot_deviceconfiguration_force_rotation', args=[obj.pk])
            return format_html(
                '<a class="button" href="{}" onclick="return confirm(\'Möchten Sie die API-Key-Rotation jetzt ausführen? Ein neuer API-Key wird generiert und das Gerät holt ihn beim nächsten Config-Report ab. Der alte Key wird ungültig.\');">Rotation jetzt ausführen</a>',
                url
            )
        return _("Speichern Sie zuerst die Gerätekonfiguration, um die Rotation auszuführen")
    force_rotation_button.short_description = _("Rotation jetzt ausführen")
    
    def get_urls(self):
        """Add custom URLs for API key generation and rotation testing."""
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path('<path:object_id>/generate_api_key/', self.admin_site.admin_view(self.generate_api_key_view), name='iot_deviceconfiguration_generate_api_key'),
            path('<path:object_id>/test_rotation/', self.admin_site.admin_view(self.test_rotation_view), name='iot_deviceconfiguration_test_rotation'),
            path('<path:object_id>/force_rotation/', self.admin_site.admin_view(self.force_rotation_view), name='iot_deviceconfiguration_force_rotation'),
        ]
        return custom_urls + urls
    
    def generate_api_key_view(self, request, object_id):
        """View to generate a new API key for a device configuration."""
        from django.shortcuts import redirect
        from django.contrib import messages
        
        try:
            config = DeviceConfiguration.objects.get(pk=object_id)
            old_key = config.device_specific_api_key
            new_key = config.generate_api_key()
            
            # Create audit log
            DeviceAuditLog.objects.create(
                device=config.device,
                action='api_key_generated',
                user=request.user if request.user.is_authenticated else None,
                ip_address=get_client_ip(request) if hasattr(request, 'META') else None,
                details={'old_key_preview': old_key[:8] + '...' if old_key else None}
            )
            
            messages.success(request, f'Neuer API-Key für Gerät {config.device.name} generiert. Neuer Key: {new_key}')
            logger.info(f"[generate_api_key] Generated new API key for device {config.device.name}")
        except DeviceConfiguration.DoesNotExist:
            messages.error(request, 'Gerätekonfiguration nicht gefunden.')
        except Exception as e:
            messages.error(request, f'Fehler beim Generieren des API-Keys: {str(e)}')
            logger.error(f"[generate_api_key] Error: {str(e)}", exc_info=True)
        
        return redirect('admin:iot_device_change', object_id=config.device.pk)
    
    def test_rotation_view(self, request, object_id):
        """View to test API key rotation logic."""
        from django.shortcuts import redirect
        from django.contrib import messages
        from django.utils import timezone
        
        try:
            config = DeviceConfiguration.objects.get(pk=object_id)
            
            # Test rotation logic
            rotation_test_result = {
                'rotation_enabled': config.api_key_rotation_enabled,
                'last_rotated': config.api_key_last_rotated,
                'rotation_interval_days': config.api_key_rotation_interval_days,
            }
            
            if config.api_key_rotation_enabled:
                if config.api_key_last_rotated:
                    days_since_rotation = (timezone.now() - config.api_key_last_rotated).days
                    rotation_test_result['days_since_rotation'] = days_since_rotation
                    rotation_test_result['should_rotate'] = days_since_rotation >= config.api_key_rotation_interval_days
                    
                    if rotation_test_result['should_rotate']:
                        messages.warning(
                            request,
                            f'Rotation ist fällig! Letzte Rotation: {config.api_key_last_rotated.strftime("%Y-%m-%d %H:%M")}, '
                            f'Intervall: {config.api_key_rotation_interval_days} Tage, '
                            f'Vergangene Tage: {days_since_rotation}. '
                            f'Die Rotation wird beim nächsten Config-Report automatisch durchgeführt.'
                        )
                    else:
                        days_until_rotation = config.api_key_rotation_interval_days - days_since_rotation
                        messages.info(
                            request,
                            f'Rotation ist aktiviert. Letzte Rotation: {config.api_key_last_rotated.strftime("%Y-%m-%d %H:%M")}, '
                            f'Intervall: {config.api_key_rotation_interval_days} Tage, '
                            f'Vergangene Tage: {days_since_rotation}, '
                            f'Verbleibende Tage bis zur nächsten Rotation: {days_until_rotation}.'
                        )
                else:
                    messages.warning(
                        request,
                        f'Rotation ist aktiviert, aber noch keine Rotation durchgeführt. '
                        f'Die erste Rotation erfolgt beim nächsten Config-Report. '
                        f'Intervall: {config.api_key_rotation_interval_days} Tage.'
                    )
            else:
                messages.info(
                    request,
                    f'Rotation ist deaktiviert. Letzte Rotation: '
                    f'{config.api_key_last_rotated.strftime("%Y-%m-%d %H:%M") if config.api_key_last_rotated else "Nie"}.'
                )
            
            logger.info(f"[test_rotation] Rotation test for device {config.device.name}: {rotation_test_result}")
        except DeviceConfiguration.DoesNotExist:
            messages.error(request, 'Gerätekonfiguration nicht gefunden.')
        except Exception as e:
            messages.error(request, f'Fehler beim Testen der Rotation: {str(e)}')
            logger.error(f"[test_rotation] Error: {str(e)}", exc_info=True)
        
        # Redirect to DeviceConfiguration change page (standalone admin) or Device change page (inline admin)
        if str(object_id) == str(config.pk):
            return redirect('admin:iot_deviceconfiguration_change', object_id=config.pk)
        else:
            return redirect('admin:iot_device_change', object_id=config.device.pk)
    
    def force_rotation_view(self, request, object_id):
        """View to force API key rotation immediately (regardless of interval)."""
        from django.shortcuts import redirect
        from django.contrib import messages
        
        try:
            config = DeviceConfiguration.objects.get(pk=object_id)
            old_key = config.device_specific_api_key
            new_key = config.generate_api_key()
            
            # Create audit log
            DeviceAuditLog.objects.create(
                device=config.device,
                action='api_key_rotated_manually',
                user=request.user if request.user.is_authenticated else None,
                ip_address=get_client_ip(request) if hasattr(request, 'META') else None,
                details={
                    'old_key_preview': old_key[:8] + '...' if old_key else None,
                    'rotation_triggered_by': 'admin_manual',
                    'rotation_interval_days': config.api_key_rotation_interval_days,
                    'rotation_enabled': config.api_key_rotation_enabled
                }
            )
            
            messages.success(
                request,
                f'API-Key-Rotation für Gerät {config.device.name} erfolgreich ausgeführt. '
                f'Neuer Key: {new_key}. '
                f'Das Gerät wird den neuen Key beim nächsten Config-Report automatisch abholen.'
            )
            logger.info(f"[force_rotation] Manually triggered API key rotation for device {config.device.name}")
        except DeviceConfiguration.DoesNotExist:
            messages.error(request, 'Gerätekonfiguration nicht gefunden.')
        except Exception as e:
            messages.error(request, f'Fehler beim Ausführen der Rotation: {str(e)}')
            logger.error(f"[force_rotation] Error: {str(e)}", exc_info=True)
        
        # Redirect to DeviceConfiguration change page (standalone admin) or Device change page (inline admin)
        # Check if we're in standalone admin by checking if object_id matches config.pk
        if str(object_id) == str(config.pk):
            return redirect('admin:iot_deviceconfiguration_change', object_id=config.pk)
        else:
            return redirect('admin:iot_device_change', object_id=config.device.pk)


def get_client_ip(request):
    """Get client IP address from request."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


# --- ANALYTICS & REPORTING ---
# Register analytics URLs with the admin site
from mgmt.analytics import analytics_dashboard, analytics_data_api, export_data, hierarchy_breakdown
from django.urls import path

# Override admin site's get_urls to include analytics URLs
# Override get_app_list to control app ordering in admin menu
_original_get_app_list = admin.site.get_app_list

def get_app_list_with_custom_ordering(self, request, app_label=None):
    """
    Custom app list ordering: MCC Core API & Models first, then Kiosk, then IOT Management last.
    """
    app_dict = self._build_app_dict(request, app_label)
    app_list = sorted(app_dict.values(), key=lambda x: x['name'].lower())
    
    # Define custom ordering
    app_ordering = {
        'MCC Core API & Models': 1,
        'Kiosk Management': 2,
        'IOT Management': 3,
    }
    
    # Sort apps by custom ordering, then alphabetically for others
    app_list.sort(key=lambda x: (app_ordering.get(x['name'], 999), x['name'].lower()))
    
    return app_list

admin.site.get_app_list = get_app_list_with_custom_ordering.__get__(admin.site, type(admin.site))

# Register analytics URLs with the admin site
_original_get_urls = admin.site.get_urls
def get_urls_with_analytics():
    """Add analytics URLs to admin site."""
    urls = _original_get_urls()
    analytics_urls = [
        path('analytics/', admin.site.admin_view(analytics_dashboard), name='api_analytics_dashboard'),
        path('analytics/data/', admin.site.admin_view(analytics_data_api), name='api_analytics_data_api'),
        path('analytics/export/', admin.site.admin_view(export_data), name='api_analytics_export'),
        path('analytics/hierarchy/', admin.site.admin_view(hierarchy_breakdown), name='api_analytics_hierarchy'),
    ]
    return analytics_urls + urls

admin.site.get_urls = get_urls_with_analytics
