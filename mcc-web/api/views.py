# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    views.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
import json
import logging
import requests
import time
from typing import Dict, Optional
from django.http import JsonResponse, Http404, HttpRequest, FileResponse
from ipaddress import ip_address
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
from django.db.utils import OperationalError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from .models import (
    Cyclist, Group, HourlyMetric, CyclistDeviceCurrentMileage, GroupTravelStatus, 
    Milestone, GroupMilestoneAchievement, LeafGroupTravelContribution, update_group_hierarchy_progress
)
from .helpers import _get_latest_snapshot_date_for_groups, filter_cyclist_metrics_by_snapshot
from iot.models import (
    Device, DeviceConfiguration, DeviceConfigurationReport, DeviceConfigurationDiff,
    FirmwareImage, DeviceManagementSettings, DeviceHealth, DeviceAuditLog
)
from kiosk.models import KioskDevice
from django.shortcuts import get_object_or_404
from django.db.models import Q, Sum
from django.db.models.functions import TruncDate, TruncHour
from decimal import Decimal, ROUND_FLOOR
from datetime import timedelta, datetime
from functools import wraps
from config.logger_utils import get_logger


logger = get_logger(__name__)

# --- Helper Functions ---

def retry_on_db_lock(max_retries=10, base_delay=0.05, max_delay=5.0):
    """
    Decorator to retry database operations on 'database is locked' errors.
    
    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Base delay in seconds for exponential backoff
        max_delay: Maximum delay in seconds between retries
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except OperationalError as e:
                    # Check if it's a database lock error
                    error_str = str(e).lower()
                    if 'database is locked' in error_str or 'locked' in error_str:
                        last_exception = e
                        if attempt < max_retries - 1:
                            # Calculate delay with exponential backoff
                            delay = min(base_delay * (2 ** attempt), max_delay)
                            # Add small random jitter to avoid thundering herd
                            jitter = base_delay * 0.1 * (attempt + 1)
                            total_delay = delay + jitter
                            
                            logger.warning(
                                f"[retry_on_db_lock] Database locked on attempt {attempt + 1}/{max_retries} "
                                f"for {func.__name__}. Retrying in {total_delay:.3f}s..."
                            )
                            time.sleep(total_delay)
                        else:
                            logger.error(
                                f"[retry_on_db_lock] Database locked after {max_retries} attempts "
                                f"for {func.__name__}. Giving up."
                            )
                    else:
                        # Not a lock error, re-raise immediately
                        raise
                except Exception as e:
                    # Other exceptions, re-raise immediately
                    raise
            
            # If we exhausted all retries, raise the last exception
            if last_exception:
                raise last_exception
            return None
        return wrapper
    return decorator
def push_to_minecraft_bridge(
    username,
    coins_total,
    coins_spendable,
    action,
    spendable_action="set",
    spendable_delta=None,
):
    """Queue a Minecraft outbox event for player score updates."""
    from minecraft.services.outbox import queue_player_coins_update

    if not username:
        logger.error(_(" Konfiguration für Minecraft-Bridge ist unvollständig."))
        return False

    try:
        if action not in ["set", "add"]:
            logger.error(_(f" Ungültige Action für Minecraft-Bridge: {action}"))
            return False

        if action == "add":
            logger.warning(_(f" Add-Action für Minecraft wird ignoriert. Führe set aus: {username}"))

        queue_player_coins_update(
            player=username,
            coins_total=int(coins_total),
            coins_spendable=int(coins_spendable),
            reason="db_update",
            spendable_action=spendable_action,
            spendable_delta=spendable_delta,
        )
        logger.info(_(f" Coins für Spieler {username} in Outbox eingereiht."))
        return True
    except Exception as e:
        logger.error(_(f" Fehler beim Einreihen der Coins an die Minecraft-Outbox: {e}"))
        return False

def validate_api_key(api_key):
    """Validates the API key for public endpoints (not IoT device endpoints).
    
    This function is used for public API endpoints (leaderboards, statistics, etc.)
    and does NOT accept IoT Device Shared API Key - only public API key and
    device-specific keys for backward compatibility.
    
    Also supports previous_api_key for grace period during rotation.
    """
    if not api_key:
        logger.warning(f"[validate_api_key] API key validation failed: No API key provided")
        return False, None
    
    # Check global public API key first (for public endpoints)
    if api_key == settings.MCC_APP_API_KEY:
        return True, None
    
    # Check device-specific API keys (current key) - for backward compatibility
    # Note: IoT Device Shared Key is NOT accepted here - it's only for IoT endpoints
    try:
        config = DeviceConfiguration.objects.select_related('device').get(device_specific_api_key=api_key)
        # If device authenticated with new key and previous_key exists, clear it (rotation completed)
        if config.previous_api_key:
            logger.info(f"[validate_api_key] Device {config.device.name} authenticated with new API key - clearing previous key")
            config.previous_api_key = None
            config.previous_api_key_expires_at = None
            config.save(update_fields=['previous_api_key', 'previous_api_key_expires_at'])
        return True, config.device
    except DeviceConfiguration.DoesNotExist:
        pass
    
    # Check previous API key (grace period for rotation - no expiration, until device uses new key)
    try:
        config = DeviceConfiguration.objects.select_related('device').get(previous_api_key=api_key)
        logger.info(f"[validate_api_key] Device {config.device.name} authenticated with previous API key (grace period)")
        return True, config.device
    except DeviceConfiguration.DoesNotExist:
        pass
    
    # Log the invalid API key for admin debugging
    logger.warning(f"[validate_api_key] API key validation failed: Invalid API key received: {api_key}")
    return False, None


def get_client_ip(request: HttpRequest) -> str | None:
    """Get client IP address from request."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def validate_device_api_key(request: HttpRequest, device_id: str = None) -> tuple[bool, Device | None, DeviceConfiguration | None]:
    """
    Validate API key for device-specific endpoints.
    
    Validates in this order:
    1. Device-specific API key (current key)
    2. IoT Device Shared API Key (from DeviceManagementSettings)
    3. Previous API key (grace period for rotation)
    4. Global API key (for testing and backward compatibility)
    
    Returns:
        (is_valid, device, config) tuple
    """
    api_key_header = request.headers.get('X-Api-Key')
    if not api_key_header:
        logger.warning(f"[validate_device_api_key] API key validation failed: No API key provided (device_id: {device_id})")
        return False, None, None
    
    # Check device-specific API key (current key) - highest priority
    try:
        config = DeviceConfiguration.objects.select_related('device').get(device_specific_api_key=api_key_header)
        device = config.device
        
        # If device_id is provided, verify it matches
        if device_id and device.name != device_id:
            logger.warning(f"[validate_device_api_key] Device ID mismatch: API key belongs to {device.name}, but request is for {device_id}")
            return False, None, None
        
        # If device authenticated with new key and previous_key exists, clear it (rotation completed)
        if config.previous_api_key:
            logger.info(f"[validate_device_api_key] Device {device.name} authenticated with new API key - clearing previous key")
            config.previous_api_key = None
            config.previous_api_key_expires_at = None
            config.save(update_fields=['previous_api_key', 'previous_api_key_expires_at'])
        
        return True, device, config
    except DeviceConfiguration.DoesNotExist:
        pass
    
    # Check IoT Device Shared API Key (from DeviceManagementSettings)
    # This key can be used by multiple devices and is only valid for IoT endpoints
    # It is used when device_specific_api_key is empty (not yet assigned to a device)
    try:
        mgmt_settings = DeviceManagementSettings.get_settings()
        if mgmt_settings.iot_device_shared_api_key and api_key_header == mgmt_settings.iot_device_shared_api_key:
            # If device_id is provided, try to get the device and create/update its configuration
            if device_id:
                try:
                    device = Device.objects.get(name=device_id)
                    # Get or create configuration (may not exist yet for new devices)
                    try:
                        config = device.configuration
                    except DeviceConfiguration.DoesNotExist:
                        # Create configuration for new device - device_specific_api_key will be empty
                        # so the device will continue using the Shared Key
                        config = DeviceConfiguration.objects.create(device=device)
                        logger.info(f"[validate_device_api_key] Created DeviceConfiguration for device {device_id} - will use IoT Shared API Key")
                    else:
                        # Configuration exists - check if it has a device-specific key
                        if not config.device_specific_api_key:
                            logger.info(f"[validate_device_api_key] Device {device_id} authenticated with IoT Device Shared API Key (no device-specific key assigned)")
                        else:
                            # Device has its own key, but used Shared Key - log warning
                            logger.warning(f"[validate_device_api_key] Device {device_id} has device_specific_api_key but used Shared Key - this may indicate a configuration issue")
                    return True, device, config
                except Device.DoesNotExist:
                    logger.warning(f"[validate_device_api_key] IoT Device Shared API Key used, but device {device_id} not found")
                    return False, None, None
            else:
                # IoT Shared Key is valid even without device_id (for initial connection)
                logger.info(f"[validate_device_api_key] Authenticated with IoT Device Shared API Key (no device_id provided)")
                return True, None, None
    except Exception as e:
        logger.warning(f"[validate_device_api_key] Error checking IoT Device Shared API Key: {e}")
        pass
    
    # Check previous API key (grace period for rotation - no expiration, until device uses new key)
    try:
        config = DeviceConfiguration.objects.select_related('device').get(
            previous_api_key=api_key_header
        )
        device = config.device
        
        # If device_id is provided, verify it matches
        if device_id and device.name != device_id:
            logger.warning(f"[validate_device_api_key] Device ID mismatch: previous API key belongs to {device.name}, but request is for {device_id}")
            return False, None, None
        
        logger.info(f"[validate_device_api_key] Device {device.name} authenticated with previous API key (grace period - waiting for device to fetch new key)")
        return True, device, config
    except DeviceConfiguration.DoesNotExist:
        pass
    
    # Check global API key (for testing and backward compatibility)
    if api_key_header == settings.MCC_APP_API_KEY:
        # If device_id is provided, try to get the device
        if device_id:
            try:
                device = Device.objects.get(name=device_id)
                try:
                    config = device.configuration
                except DeviceConfiguration.DoesNotExist:
                    config = None
                logger.info(f"[validate_device_api_key] Device {device_id} authenticated with global API key (backward compatibility)")
                return True, device, config
            except Device.DoesNotExist:
                return False, None, None
        logger.info(f"[validate_device_api_key] Authenticated with global API key (backward compatibility)")
        return True, None, None
    
    # Log the invalid API key for admin debugging
    logger.warning(f"[validate_device_api_key] API key validation failed: Invalid API key received: {api_key_header} (device_id: {device_id})")
    return False, None, None

def check_milestone_victory(group, active_leaf_group=None):
    """
    Checks during KM update whether the group has reached a new milestone.
    
    Important: Meilensteine werden der kleinsten Gruppeneinheit (Leaf-Group) zugeordnet,
    zu der die Radler direkt gehören (z.B. Klasse einer Schule), damit sichtbar ist,
    welche spezifische Gruppe den Meilenstein zuerst erreicht hat.
    
    IMPORTANT: Uses current_travel_distance (Reise-Distanz) not distance_total (Gesamtdistanz).
    Meilensteine werden basierend auf der aktuellen Reise-Distanz zugeordnet, nicht auf der
    Gesamtdistanz aller Zeiten.
    
    Race-Condition Protection:
    - Uses `select_for_update()` to lock the milestone during transaction
    - First group to acquire the lock and update the milestone wins (first-come-first-serve)
    - If multiple groups reach the milestone simultaneously, the group with the HIGHEST
      current_travel_distance wins (ensures the group that actually reached furthest in the
      current trip gets the milestone)
    
    Args:
        group: The group to check milestones for (can be leaf or parent group)
        active_leaf_group: Optional leaf group that is currently active (the one that just rode).
                          Used for logging purposes only - milestone assignment is based on
                          highest current_travel_distance, not on which group is currently active.
    """
    # Reload group from database to get fresh travel_status
    group.refresh_from_db()
    
    # Track variable to store the track for milestone checking
    track = None
    status = None
    parent_travel_distance = None  # Store parent's travel distance for milestone checking
    
    try:
        status = group.travel_status
        track = status.track
        parent_travel_distance = status.current_travel_distance
    except GroupTravelStatus.DoesNotExist:
        # If this is a leaf group without travel_status, we need to get the travel distance
        # from its parent group's travel_status (since leaf groups share the parent's trip)
        if group.is_leaf_group():
            # Find parent group with travel_status to get current_travel_distance
            parent = group.parent
            if not parent:
                logger.debug(f"[check_milestone_victory] Leaf group '{group.name}' has no parent. Skipping milestone check.")
                return
            
            try:
                parent_status = parent.travel_status
                track = parent_status.track
                # Get this leaf group's contribution to the trip
                try:
                    contribution = LeafGroupTravelContribution.objects.get(
                        leaf_group=group,
                        track=track
                    )
                    leaf_current_km = contribution.current_travel_distance or Decimal('0.00000')
                    logger.debug(f"[check_milestone_victory] Leaf group '{group.name}' has travel contribution: {leaf_current_km} km on track '{track.name}'")
                except LeafGroupTravelContribution.DoesNotExist:
                    # No contribution yet - use parent's distance as fallback
                    leaf_current_km = parent_status.current_travel_distance or Decimal('0.00000')
                    logger.debug(f"[check_milestone_victory] Leaf group '{group.name}' has no contribution yet, using parent '{parent.name}' travel distance: {leaf_current_km} km")
            except GroupTravelStatus.DoesNotExist:
                logger.debug(f"[check_milestone_victory] Leaf group '{group.name}' parent '{parent.name}' has no travel_status. Skipping milestone check.")
                return
            
            # Find unreached milestones on this track that have now been exceeded
            # IMPORTANT: Check against parent's total travel distance, but assign to leaf group with highest contribution
            parent_travel_distance = parent_status.current_travel_distance or Decimal('0.00000')
            
            # Early exit if no distance traveled - prevents unnecessary debug messages
            if parent_travel_distance <= 0:
                return
            
            new_milestones = Milestone.objects.filter(
                track=track,
                winner_group__isnull=True,
                distance_km__lte=parent_travel_distance  # Check parent's total distance
            ).order_by('distance_km')
            # Store parent_travel_distance for later use in transaction check
            
            # Early exit if no milestones to check - prevents unnecessary debug messages
            if not new_milestones.exists():
                return
            
            logger.debug(f"[check_milestone_victory] Found {new_milestones.count()} unreached milestones for leaf group '{group.name}'")
            
            # Use this leaf group directly
            leaf_group = group
        else:
            logger.debug(f"[check_milestone_victory] Group '{group.name}' has no travel_status and is not a leaf group. Skipping milestone check.")
            return
    else:
        # Group has travel_status - proceed with normal logic
        # Reload status from database to get latest current_travel_distance
        status.refresh_from_db()
        track = status.track  # Set track for later use
        current_travel_km = status.current_travel_distance
        parent_travel_distance = current_travel_km  # For parent groups, this is the travel distance
        
        # Early exit if no distance traveled - prevents unnecessary debug messages
        if not current_travel_km or current_travel_km <= 0:
            return
        
        logger.debug(f"[check_milestone_victory] Checking milestones for group '{group.name}' on track '{track.name}' at {current_travel_km} km")

        # Find unreached milestones on this track that have now been exceeded
        new_milestones = Milestone.objects.filter(
            track=status.track,
            winner_group__isnull=True,
            distance_km__lte=current_travel_km
        ).order_by('distance_km')

        # Early exit if no milestones to check - prevents unnecessary debug messages
        if not new_milestones.exists():
            return

        logger.debug(f"[check_milestone_victory] Found {new_milestones.count()} unreached milestones that may have been reached")

        # IMPORTANT: Find the actual leaf group (smallest unit) that reached the milestone
        # The passed group might be a parent group with travel_status, but we MUST find the specific leaf group
        # that actually reached the milestone based on their distance_total
        leaf_group = None
        leaf_current_km = None
        
        if group.is_leaf_group():
            # Group is already a leaf group, use it directly
            # IMPORTANT: For leaf groups, we need to get the travel contribution from LeafGroupTravelContribution
            # This tracks how much this leaf group contributed to the parent's trip
            parent = group.parent
            if parent:
                try:
                    parent_status = parent.travel_status
                    track = parent_status.track
                    # Get this leaf group's contribution to the trip
                    try:
                        contribution = LeafGroupTravelContribution.objects.get(
                            leaf_group=group,
                            track=track
                        )
                        leaf_current_km = contribution.current_travel_distance or Decimal('0.00000')
                        logger.debug(f"[check_milestone_victory] Leaf group '{group.name}' has travel contribution: {leaf_current_km} km on track '{track.name}'")
                    except LeafGroupTravelContribution.DoesNotExist:
                        # No contribution yet - use parent's distance as fallback
                        leaf_current_km = parent_status.current_travel_distance or Decimal('0.00000')
                        logger.debug(f"[check_milestone_victory] Leaf group '{group.name}' has no contribution yet, using parent '{parent.name}' travel distance: {leaf_current_km} km")
                except GroupTravelStatus.DoesNotExist:
                    logger.debug(f"[check_milestone_victory] Leaf group '{group.name}' parent has no travel_status. Skipping milestone check.")
                    return
            else:
                logger.debug(f"[check_milestone_victory] Leaf group '{group.name}' has no parent. Skipping milestone check.")
                return
            
            leaf_group = group
        else:
            # Group is not a leaf group, find the leaf groups that belong to it
            # We MUST find which specific leaf group reached the milestone based on their distance_total
            # IMPORTANT: If active_leaf_group is provided, prefer it over other leaf groups
            leaf_groups = group.get_leaf_groups()
            if not leaf_groups.exists():
                # No leaf groups - exit silently (no debug message needed)
                return
            
            # Find the leaf group that has reached the milestone distance
            # IMPORTANT: The leaf group with the HIGHEST travel contribution (current_travel_distance from LeafGroupTravelContribution)
            # that reached the milestone should win. This ensures the leaf group that contributed the most
            # kilometers to the parent's trip gets the milestone.
            best_leaf_group = None
            best_distance = Decimal('0.00000')
            
            # Get travel contributions for all leaf groups on this track
            leaf_contributions = LeafGroupTravelContribution.objects.filter(
                leaf_group__in=leaf_groups,
                track=track
            ).select_related('leaf_group').order_by('-current_travel_distance')
            
            # Early exit if no contributions exist - prevents unnecessary debug messages
            if not leaf_contributions.exists():
                return
            
            # Build a map of leaf_group_id -> contribution distance
            contribution_map = {contrib.leaf_group_id: contrib.current_travel_distance for contrib in leaf_contributions}
            
            # Check all leaf groups to find the one with highest contribution that reached the milestone
            for leaf in leaf_groups:
                # Get this leaf group's travel contribution (how much it contributed to the trip)
                leaf_travel_distance = contribution_map.get(leaf.id, Decimal('0.00000'))
                # Only log if there's actual contribution (reduces debug noise)
                if leaf_travel_distance > 0:
                    logger.debug(f"[check_milestone_victory] Checking leaf group '{leaf.name}' with travel contribution: {leaf_travel_distance} km")
                
                # Check if this leaf group has reached any of the milestones
                # IMPORTANT: We check if the PARENT's total travel distance has reached the milestone,
                # but assign it to the leaf group with the highest contribution
                for ms in new_milestones:
                    if current_travel_km >= ms.distance_km:
                        # Parent has reached this milestone - check which leaf group should get credit
                        # The leaf group with the highest contribution wins
                        if leaf_travel_distance > best_distance:
                            best_leaf_group = leaf
                            best_distance = leaf_travel_distance
                            logger.debug(f"[check_milestone_victory] Leaf group '{leaf.name}' ({leaf_travel_distance} km contribution) should get milestone '{ms.name}' ({ms.distance_km} km) - highest contribution so far")
            
            # If no leaf group has contributions yet, fall back to active_leaf_group if provided
            if not best_leaf_group and active_leaf_group and active_leaf_group in leaf_groups:
                best_leaf_group = active_leaf_group
                best_distance = contribution_map.get(active_leaf_group.id, Decimal('0.00000'))
                logger.debug(f"[check_milestone_victory] No contributions found, using active leaf group '{active_leaf_group.name}' as fallback")
            
            if not best_leaf_group:
                # No leaf group reached milestone - exit silently (no warning needed if no milestones exist or no distance traveled)
                return
            
            leaf_group = best_leaf_group
            leaf_current_km = best_distance
            logger.info(f"[check_milestone_victory] Selected leaf group '{leaf_group.name}' with {leaf_current_km} km as milestone winner (highest distance)")
    
    # Validate that leaf group is visible (should be checked, but double-check for safety)
    if not leaf_group.is_visible:
        logger.warning(f"[check_milestone_victory] Leaf group '{leaf_group.name}' is not visible. Skipping milestone assignment.")
        return

    for ms in new_milestones:
        with transaction.atomic():
            # Re-check within the transaction (first-come-first-serve)
            ms_locked = Milestone.objects.select_for_update().get(pk=ms.pk)
            if not ms_locked.winner_group:
                # Double-check that parent group has reached this milestone distance
                # The milestone is assigned to the leaf group with highest contribution,
                # but we check against the parent's total travel distance
                if parent_travel_distance is None:
                    # Fallback: try to get from status
                    parent_travel_distance = status.current_travel_distance if status else Decimal('0.00000')
                
                if parent_travel_distance < ms_locked.distance_km:
                    logger.debug(f"[check_milestone_victory] Parent group has not reached milestone '{ms_locked.name}' yet ({parent_travel_distance} km < {ms_locked.distance_km} km). Skipping.")
                    continue
                
                reached_time = timezone.now()
                # Use leaf_group for milestone assignment (smallest unit)
                ms_locked.winner_group = leaf_group
                ms_locked.reached_at = reached_time
                ms_locked.save()
                
                # IMPORTANT: Get the actual travel contribution of the leaf group for reached_distance
                # This ensures we store the leaf group's contribution, not the parent's total distance
                leaf_contribution_distance = leaf_current_km
                try:
                    leaf_contribution = LeafGroupTravelContribution.objects.get(
                        leaf_group=leaf_group,
                        track=track
                    )
                    leaf_contribution_distance = leaf_contribution.current_travel_distance or Decimal('0.00000')
                    logger.debug(f"[check_milestone_victory] Using leaf group '{leaf_group.name}' contribution: {leaf_contribution_distance} km for reached_distance")
                except LeafGroupTravelContribution.DoesNotExist:
                    # Fallback: use leaf_current_km (should be from contribution already, but if not, use it)
                    logger.debug(f"[check_milestone_victory] No contribution found for leaf group '{leaf_group.name}', using leaf_current_km: {leaf_contribution_distance} km")
                
                # Also save to persistent achievement table using leaf_group
                # Use get_or_create to prevent duplicates (unique_together constraint)
                # IMPORTANT: Use track (parent group's track or found track) to ensure consistency
                # IMPORTANT: Store reward_text at the time of achievement (persistent snapshot)
                # IMPORTANT: Store leaf group's travel contribution distance, not parent's total distance
                achievement, created = GroupMilestoneAchievement.objects.get_or_create(
                    group=leaf_group,  # Use leaf_group (smallest unit) - this is the group that won the milestone
                    milestone=ms_locked,
                    defaults={
                        'track': track,  # Use track (parent group's track or found track - leaf groups don't have their own travel_status)
                        'reached_at': reached_time,
                        'reached_distance': leaf_contribution_distance,  # Use leaf group's travel contribution (current_travel_distance from LeafGroupTravelContribution)
                        'reward_text': ms_locked.reward_text or '',  # Store reward at time of achievement
                        'is_redeemed': False  # Reward not yet redeemed
                    }
                )
                if created:
                    logger.info(f"[check_milestone_victory] ✅ Milestone '{ms_locked.name}' reached by leaf group '{leaf_group.name}' at {ms_locked.distance_km} km! (Persistent achievement saved)")
                else:
                    logger.debug(f"[check_milestone_victory] Milestone '{ms_locked.name}' already has persistent achievement for leaf group '{leaf_group.name}'")
                
                logger.info(f"[check_milestone_victory] ✅ Milestone '{ms_locked.name}' reached by leaf group '{leaf_group.name}' at {ms_locked.distance_km} km!")
            else:
                logger.debug(f"[check_milestone_victory] Milestone '{ms_locked.name}' already reached by '{ms_locked.winner_group.name}'")

# --- API Endpoints ---

@csrf_exempt
def update_data(request):
    """Processes device updates and propagates KM through the group hierarchy."""
    # DEBUG: Log incoming request details
    logger.debug(f"[update_data] Incoming request - Method: {request.method}, Content-Type: {request.content_type}")
    logger.debug(f"[update_data] Request headers: {dict(request.headers)}")
    logger.debug(f"[update_data] Request body (raw): {request.body}")
    logger.debug(f"[update_data] Request body (decoded): {request.body.decode('utf-8', errors='ignore') if request.body else '(empty)'}")
    
    api_key_header = request.headers.get('X-Api-Key')
    logger.debug(f"[update_data] API Key received: {api_key_header[:10] + '...' if api_key_header and len(api_key_header) > 10 else api_key_header}")
    
    # Validate API key (global or device-specific)
    # Note: We validate the key first, but device_id is extracted from JSON body later
    # So we do a basic validation here and full device validation after parsing JSON
    is_valid, device_from_initial_key = validate_api_key(api_key_header)
    if not is_valid:
        logger.warning(f"[update_data] Invalid API key - API key validation failed (API key logged in validate_api_key)")
        return JsonResponse({"error": _("Ungültiger API-Key")}, status=403)

    # Handle JSON POST requests
    try:
        if request.body:
            data = json.loads(request.body)
            logger.debug(f"[update_data] Parsed JSON data: {data}")
        else:
            # Try form data as fallback
            data = request.POST.dict()
            logger.debug(f"[update_data] Using form data: {data}")
            if not data:
                logger.warning(f"[update_data] No data received - Content-Type: {request.content_type}, Method: {request.method}")
                return JsonResponse({"error": _("Keine Daten empfangen"), "content_type": request.content_type, "method": request.method}, status=400)
    except json.JSONDecodeError as e:
        body_preview = request.body.decode('utf-8', errors='ignore')[:200] if request.body else "(empty)"
        logger.error(f"[update_data] JSON decode error: {str(e)}, Body preview: {body_preview}")
        return JsonResponse({
            "error": _("Ungültiges JSON-Format"), 
            "details": str(e), 
            "body_preview": body_preview,
            "content_type": request.content_type
        }, status=400)
    except Exception as e:
        logger.error(f"[update_data] Data processing error: {str(e)}", exc_info=True)
        return JsonResponse({"error": _("Datenfehler"), "details": str(e)}, status=400)
    
    id_tag = data.get('id_tag')
    device_id = data.get('device_id')
    distance_delta = Decimal(str(data.get('distance', 0)))
    
    logger.debug(f"[update_data] Extracted values - id_tag: {id_tag}, device_id: {device_id}, distance: {distance_delta}")
    
    if not id_tag:
        logger.warning(f"[update_data] Missing id_tag in request data")
        return JsonResponse({"error": _("id_tag fehlt")}, status=400)
    if not device_id:
        logger.warning(f"[update_data] Missing device_id in request data")
        return JsonResponse({"error": _("device_id fehlt")}, status=400)
    
    # Validate API key with device_id (now that we have it from JSON body)
    # This ensures device-specific API keys match the device_id in the request
    is_valid, device_from_key, config = validate_device_api_key(request, device_id)
    if not is_valid:
        logger.warning(f"[update_data] Invalid API key for device {device_id} - API key validation failed (API key logged in validate_device_api_key)")
        return JsonResponse({"error": _("Ungültiger API-Key")}, status=403)
    
    try:
        cyclist_obj = Cyclist.objects.get(id_tag__iexact=id_tag)
        logger.debug(f"[update_data] Found cyclist: {cyclist_obj.id_tag} (ID: {cyclist_obj.pk})")
    except Cyclist.DoesNotExist:
        logger.warning(f"[update_data] Cyclist not found: id_tag={id_tag}")
        return JsonResponse({"error": _("Radler nicht gefunden"), "id_tag": id_tag}, status=404)
    
    try:
        device_obj = Device.objects.get(name__iexact=device_id)
        logger.debug(f"[update_data] Found device: {device_obj.name} (ID: {device_obj.pk})")
    except Device.DoesNotExist:
        logger.warning(f"[update_data] Device not found: device_id={device_id}")
        return JsonResponse({"error": _("Gerät nicht gefunden"), "device_id": device_id}, status=404)
    
    # If device was found via API key, verify it matches the device_id from JSON
    if device_from_key and device_from_key.name != device_id:
        logger.warning(f"[update_data] Device ID mismatch: API key belongs to {device_from_key.name}, but request is for {device_id}")
        return JsonResponse({"error": _("API-Key gehört zu einem anderen Gerät")}, status=403)

    # Check if kilometer collection is enabled for cyclist and device
    if not cyclist_obj.is_km_collection_enabled:
        logger.info(f"[update_data] Kilometer collection disabled for cyclist: {cyclist_obj.id_tag} (ID: {cyclist_obj.pk})")
        return JsonResponse({
            "success": False,
            "message": _("Kilometer-Erfassung für diesen Radler ist deaktiviert"),
            "skipped": True
        }, status=200)
    
    if not device_obj.is_km_collection_enabled:
        logger.info(f"[update_data] Kilometer collection disabled for device: {device_obj.name} (ID: {device_obj.pk})")
        return JsonResponse({
            "success": False,
            "message": _("Kilometer-Erfassung für dieses Gerät ist deaktiviert"),
            "skipped": True
        }, status=200)

    # Process the update with retry mechanism for database locks
    try:
        return _process_update_with_retry(cyclist_obj, device_obj, distance_delta, id_tag, device_id)
    except OperationalError as e:
        # If all retries failed, return a 503 Service Unavailable response
        error_str = str(e).lower()
        if 'database is locked' in error_str or 'locked' in error_str:
            logger.error(
                f"[update_data] Database locked after all retries for id_tag: {id_tag}, "
                f"device_id: {device_id}. Request could not be processed."
            )
            return JsonResponse({
                "error": _("Datenbank temporär nicht verfügbar"),
                "message": _("Bitte versuchen Sie es später erneut"),
                "retry_after": 5
            }, status=503)
        else:
            # Other OperationalError, re-raise as 500
            logger.error(f"[update_data] Database error: {e}", exc_info=True)
            raise


@retry_on_db_lock(max_retries=10, base_delay=0.05, max_delay=5.0)
def _process_update_with_retry(cyclist_obj, device_obj, distance_delta, id_tag, device_id):
    """
    Internal function to process the update with automatic retry on database locks.
    This function is wrapped with retry_on_db_lock decorator.
    """
    with transaction.atomic():
        now = timezone.now()
        logger.debug(f"[update_data] Processing update - distance_delta: {distance_delta}, timestamp: {now}")
        
        # Session management
        # Check if there's an existing session for this device with a different cyclist
        # If so, delete it (only one cyclist can be active on a device at a time)
        existing_device_session = CyclistDeviceCurrentMileage.objects.filter(
            device=device_obj
        ).exclude(cyclist=cyclist_obj).first()
        
        if existing_device_session:
            logger.info(f"[update_data] Cyclist switch detected on device {device_obj.name}: "
                       f"Previous cyclist: {existing_device_session.cyclist.id_tag}, "
                       f"New cyclist: {cyclist_obj.id_tag}. Saving old session to HourlyMetric and deleting.")
            
            # Save session to HourlyMetric before deleting
            # IMPORTANT: Each hour should track only the kilometers driven in that hour, not cumulative
            if existing_device_session.cumulative_mileage and existing_device_session.cumulative_mileage > 0:
                # Get the cyclist's primary group at the time of session end
                primary_group = existing_device_session.cyclist.groups.first()
                
                # Round timestamp to the hour to aggregate metrics within the same hour
                hour_timestamp = now.replace(minute=0, second=0, microsecond=0)
                
                # Check if there's already a metric entry for this hour
                from django.db.models import Sum
                existing_metric = HourlyMetric.objects.filter(
                    cyclist=existing_device_session.cyclist,
                    device=existing_device_session.device,
                    timestamp=hour_timestamp
                ).first()
                
                # Calculate distance for this hour only (not cumulative)
                # IMPORTANT: cumulative_mileage is the distance since session start, not total distance
                session_start_hour = existing_device_session.start_time.replace(minute=0, second=0, microsecond=0)
                
                if session_start_hour == hour_timestamp:
                    # Session started in this hour, so cumulative_mileage is the distance for this hour
                    hourly_distance = existing_device_session.cumulative_mileage
                    logger.debug(f"[update_data] Session started in this hour for {existing_device_session.cyclist.id_tag}: "
                               f"cumulative_mileage={existing_device_session.cumulative_mileage}, "
                               f"hourly_distance={hourly_distance}")
                else:
                    # Session started before this hour
                    # Calculate the mileage at the start of this hour from HourlyMetrics
                    mileage_at_hour_start = HourlyMetric.objects.filter(
                        cyclist=existing_device_session.cyclist,
                        device=existing_device_session.device,
                        timestamp__lt=hour_timestamp
                    ).aggregate(total=Sum('distance_km'))['total'] or Decimal('0.00000')
                    
                    # Find the distance at session start from HourlyMetrics
                    mileage_at_session_start = HourlyMetric.objects.filter(
                        cyclist=existing_device_session.cyclist,
                        device=existing_device_session.device,
                        timestamp__lt=session_start_hour
                    ).aggregate(total=Sum('distance_km'))['total'] or Decimal('0.00000')
                    
                    # Total distance now = mileage_at_session_start + cumulative_mileage
                    total_distance_now = mileage_at_session_start + existing_device_session.cumulative_mileage
                    
                    # Distance for this hour = total_distance_now - mileage_at_hour_start
                    hourly_distance = total_distance_now - mileage_at_hour_start
                    
                    logger.debug(f"[update_data] Calculating hourly distance for {existing_device_session.cyclist.id_tag}: "
                               f"session_start={existing_device_session.start_time}, "
                               f"cumulative_mileage={existing_device_session.cumulative_mileage}, "
                               f"mileage_at_session_start={mileage_at_session_start}, "
                               f"mileage_at_hour_start={mileage_at_hour_start}, "
                               f"total_distance_now={total_distance_now}, "
                               f"hourly_distance={hourly_distance}")
                
                # If an existing metric exists, we need to check if we should update it
                if existing_metric:
                    if hourly_distance <= existing_metric.distance_km:
                        logger.debug(f"[update_data] Hourly distance calculation for {existing_device_session.cyclist.id_tag}/{existing_device_session.device.id}: "
                                   f"hourly_distance={hourly_distance}, "
                                   f"existing_metric={existing_metric.distance_km}, "
                                   f"no update needed (hourly_distance <= existing)")
                        # Don't update if the calculated distance is not higher
                        hourly_distance = None  # Mark as skip
                    # hourly_distance is higher, so we'll update the metric below
                
                if hourly_distance and hourly_distance <= 0:
                    logger.warning(f"[update_data] Hourly distance is {hourly_distance} for session {existing_device_session.cyclist.id_tag}, skipping")
                    hourly_distance = None  # Mark as skip
                
                if hourly_distance:
                    # Create/update metric with cyclist AND device combination
                    # This allows reporting both by cyclist and by device
                    if existing_metric:
                        metric = existing_metric
                        created = False
                    else:
                        metric, created = HourlyMetric.objects.get_or_create(
                            cyclist=existing_device_session.cyclist,
                            device=existing_device_session.device,
                            timestamp=hour_timestamp,
                            defaults={
                                'distance_km': hourly_distance,
                                'group_at_time': primary_group
                            }
                        )
                    
                    if not created:
                        # If metric already exists, update it only if the new value is higher
                        # (session continued in the same hour)
                        if hourly_distance > metric.distance_km:
                            old_distance = metric.distance_km
                            metric.distance_km = hourly_distance
                            # Update group if it changed
                            if metric.group_at_time != primary_group:
                                metric.group_at_time = primary_group
                            metric.save()
                            logger.info(f"[update_data] Updated HourlyMetric entry for cyclist {existing_device_session.cyclist.id_tag} "
                                       f"on device {existing_device_session.device.name}: "
                                       f"Hourly distance: {hourly_distance} km (was {old_distance} km)")
                        else:
                            logger.debug(f"[update_data] HourlyMetric already has correct value for {existing_device_session.cyclist.id_tag}")
                    else:
                        logger.info(f"[update_data] Created HourlyMetric entry for ended session: "
                                   f"Cyclist {existing_device_session.cyclist.id_tag}, "
                                   f"Device {existing_device_session.device.name}, "
                                   f"Hourly distance: {hourly_distance} km (cumulative: {existing_device_session.cumulative_mileage} km)")
            
            existing_device_session.delete()
        
        # Get or create session for current cyclist
        session, created = CyclistDeviceCurrentMileage.objects.get_or_create(
            cyclist=cyclist_obj,
            defaults={'device': device_obj, 'cumulative_mileage': distance_delta}
        )
        
        # If session exists but device changed, update the device
        if not created and session.device != device_obj:
            logger.info(f"[update_data] Cyclist {cyclist_obj.id_tag} switched device: "
                       f"From {session.device.name} to {device_obj.name}")
            session.device = device_obj
            session.save()
        
        if created:
            logger.debug(f"[update_data] Created new session for cyclist {cyclist_obj.id_tag} with device {device_obj.name}, cumulative_mileage: {distance_delta}")
        else:
            old_mileage = session.cumulative_mileage
            session.cumulative_mileage += distance_delta
            session.save()
            logger.debug(f"[update_data] Updated session - old_mileage: {old_mileage}, new_mileage: {session.cumulative_mileage}")

        # --- ACTIVATE HIERARCHY LOGIC ---
        # distance_delta is already a Decimal from line 126
        if distance_delta > 0:
            logger.debug(f"[update_data] Propagating {distance_delta} km to {cyclist_obj.groups.count()} group(s)")
            
            # Find the active leaf group (the one the cyclist directly belongs to)
            active_leaf_group = None
            for group in cyclist_obj.groups.all():
                if group.is_leaf_group():
                    active_leaf_group = group
                    break
            
            # The delta is propagated recursively upward for all groups of the cyclist
            # IMPORTANT: Always call update_group_hierarchy_progress, even if the group has reached the travel goal.
            # This ensures that:
            # - distance_total is still updated (for statistics/leaderboard)
            # - Event statuses are still updated (events are independent of travel goals)
            # - Parent groups are still updated (they might not have reached the goal)
            # The function itself will skip travel distance updates if the goal is reached.
            for group in cyclist_obj.groups.all():
                old_group_distance = group.distance_total
                update_group_hierarchy_progress(group, distance_delta)
                group.refresh_from_db()
                logger.debug(f"[update_data] Group '{group.name}' - old_distance: {old_group_distance}, new_distance: {group.distance_total}")
                # Check milestones AFTER updating the group's travel distance
                # Pass active_leaf_group to ensure correct milestone assignment
                check_milestone_victory(group, active_leaf_group=active_leaf_group)

        # Cyclist & Device total KM
        # Use Decimal arithmetic - no rounding needed as DecimalField handles precision
        old_cyclist_distance = cyclist_obj.distance_total
        cyclist_obj.distance_total = cyclist_obj.distance_total + distance_delta
        coins_added = 0
        if distance_delta > 0 and cyclist_obj.mc_username:
            conversion_factor = cyclist_obj.coin_conversion_factor or settings.DEFAULT_COIN_CONVERSION_FACTOR
            try:
                delta_coins = (distance_delta * Decimal(str(conversion_factor))).to_integral_value(rounding=ROUND_FLOOR)
            except Exception:
                delta_coins = Decimal('0')
            coins_added = int(delta_coins) if delta_coins > 0 else 0
            if coins_added > 0:
                cyclist_obj.coins_total += coins_added
                cyclist_obj.coins_spendable += coins_added
        cyclist_obj.last_active = now
        cyclist_obj.save()
        logger.debug(f"[update_data] Cyclist '{cyclist_obj.id_tag}' - old_distance: {old_cyclist_distance}, new_distance: {cyclist_obj.distance_total}")
        if coins_added > 0:
            logger.info(f"[update_data] Coins added for {cyclist_obj.id_tag}: +{coins_added}")
            push_to_minecraft_bridge(
                cyclist_obj.mc_username,
                cyclist_obj.coins_total,
                cyclist_obj.coins_spendable,
                "set",
                spendable_action="add",
                spendable_delta=coins_added,
            )
        
        old_device_distance = device_obj.distance_total
        device_obj.distance_total = device_obj.distance_total + distance_delta
        device_obj.last_active = now
        device_obj.save()
        logger.debug(f"[update_data] Device '{device_obj.name}' - old_distance: {old_device_distance}, new_distance: {device_obj.distance_total}")

    logger.info(f"[update_data] Successfully processed update - id_tag: {id_tag}, device_id: {device_id}, distance: {distance_delta}")
    return JsonResponse({"success": True})

def get_player_coins(request, username):
    """Returns the current coins of a player."""
    api_key_header = request.headers.get('X-Api-Key')
    is_valid, _device = validate_api_key(api_key_header)
    if not is_valid:
        return JsonResponse({"error": _("Ungültiger API-Schlüssel")}, status=403)

    try:
        cyclist_obj = Cyclist.objects.get(Q(user_id__iexact=username) | Q(mc_username__iexact=username))
    except Cyclist.DoesNotExist:
        return JsonResponse({"error": _("Radler nicht gefunden")}, status=404)

    response_data = {
        "mc_username": cyclist_obj.mc_username,
        "coins_total": cyclist_obj.coins_total,
        "coins_spendable": cyclist_obj.coins_spendable,
        "distance_total": cyclist_obj.distance_total,
        "last_active": cyclist_obj.last_active.isoformat() if cyclist_obj.last_active else None
    }
    return JsonResponse(response_data)


def get_cyclist_coins(request, username):
    """Backward-compatible alias for get_player_coins."""
    return get_player_coins(request, username)

@csrf_exempt
def spend_cyclist_coins(request):
    """Allows spending coins."""
    api_key_header = request.headers.get('X-Api-Key')
    is_valid, _device = validate_api_key(api_key_header)
    if not is_valid:
        return JsonResponse({"error": _("Ungültiger API-Schlüssel")}, status=403)

    try:
        data = json.loads(request.body)
        username = data.get('username').lower()
        coins_spent = int(data.get('coins_spent'))
    except (json.JSONDecodeError, ValueError, AttributeError):
        return JsonResponse({"error": _("Ungültige oder fehlende Daten.")}, status=400)
    
    try:
        cyclist_obj = Cyclist.objects.get(mc_username__iexact=username)
    except Cyclist.DoesNotExist:
        return JsonResponse({"error": _("Radler nicht gefunden.")}, status=404)
        
    with transaction.atomic():
        cyclist_obj = Cyclist.objects.select_for_update().get(pk=cyclist_obj.pk)
        if cyclist_obj.coins_spendable < coins_spent:
            return JsonResponse({"error": _("Nicht genug Coins")}, status=400)
        cyclist_obj.coins_spendable -= coins_spent
        cyclist_obj.save()
    
    push_to_minecraft_bridge(
        username,
        cyclist_obj.coins_total,
        cyclist_obj.coins_spendable,
        "set",
        spendable_action="set",
    )
    return JsonResponse({"success": True, "message": _("Coins abgezogen.")})

def get_mapped_minecraft_players(request):
    """Returns the complete player mapping structure."""
    api_key_header = request.headers.get('X-Api-Key')
    is_valid, _device = validate_api_key(api_key_header)
    if not is_valid:
        return JsonResponse({"error": _("Ungültiger API-Schlüssel")}, status=403)

    filtered_cyclists = Cyclist.objects.filter(mc_username__isnull=False).values(
        'id_tag', 'user_id', 'mc_username', 'coins_total', 'coins_spendable', 'distance_total', 'last_active'
    )
    
    response_data = {
        c['id_tag']: {
            'user_id': c['user_id'], 'mc_username': c['mc_username'],
            'coins_total': c['coins_total'], 'coins_spendable': c['coins_spendable'],
            'distance_total': c['distance_total'],
            'last_active': c['last_active'].isoformat() if c['last_active'] else None
        } for c in filtered_cyclists
    }
    return JsonResponse(response_data)


def get_mapped_minecraft_cyclists(request):
    """Backward-compatible alias for get_mapped_minecraft_players."""
    return get_mapped_minecraft_players(request)

@csrf_exempt
def get_user_id(request):
    """Returns the user_id based on the id_tag."""
    api_key_header = request.headers.get('X-Api-Key')
    is_valid, _device = validate_api_key(api_key_header)
    if not is_valid:
        logger.warning(f"[get_user_id] Invalid API key")
        return JsonResponse({"error": _("Ungültiger API-Schlüssel")}, status=403)

    if request.method != 'POST':
        return JsonResponse({"error": _("Methode nicht erlaubt.")}, status=405)

    try:
        data = json.loads(request.body)
        id_tag = data.get('id_tag')
    except json.JSONDecodeError:
        logger.warning(f"[get_user_id] Invalid JSON format")
        return JsonResponse({"error": _("Ungültiges Format.")}, status=400)
    
    if not id_tag:
        logger.warning(f"[get_user_id] Missing id_tag in request")
        return JsonResponse({"error": _("id_tag erforderlich.")}, status=400)

    return_user_id = "NULL"
    try:
        cyclist_obj = Cyclist.objects.get(id_tag__iexact=id_tag)
        if cyclist_obj.user_id: 
            return_user_id = cyclist_obj.user_id
            logger.info(f"[get_user_id] ID tag '{id_tag}' found, assigned to user_id: '{return_user_id}'")
        else:
            logger.info(f"[get_user_id] ID tag '{id_tag}' found but has no user_id assigned")
    except Cyclist.DoesNotExist:
        logger.info(f"[get_user_id] ID tag '{id_tag}' not found in database")
    
    return JsonResponse({"user_id": return_user_id})

# --- NEW: Live Map Logic ---

def get_travel_locations(request):
    """Returns the current positions of groups including logos for the map."""
    active_travels = GroupTravelStatus.objects.select_related('group', 'track').all()
    locations = []
    
    for status in active_travels:
        locations.append({
            'group_name': status.group.name,
            'logo_url': status.group.logo.url if status.group.logo else '/static/map/default_group.png',
            'km_progress': status.current_travel_distance,
            'track_id': status.track.id
        })
    return JsonResponse(locations, safe=False)


# --- KIOSK API ENDPOINTS ---
@csrf_exempt
@retry_on_db_lock(max_retries=10, base_delay=0.05, max_delay=5.0)
def kiosk_get_playlist(request, uid: str):
    """Returns the current playlist for a Kiosk device."""
    import logging
    logger = logging.getLogger(__name__)
    
    # First check if device exists (even if inactive)
    try:
        device = KioskDevice.objects.prefetch_related('playlist_entries__event_filter', 'playlist_entries__group_filter').get(uid=uid)
    except KioskDevice.DoesNotExist:
        logger.warning(f"Device not found: UID={uid}")
        return JsonResponse({
            "error": "Gerät nicht gefunden",
            "error_code": "DEVICE_NOT_FOUND",
            "uid": uid,
            "suggestion": f"Erstellen Sie ein Kiosk-Gerät mit UID '{uid}' im Admin-Panel"
        }, status=404)
    
    # Check if device is active
    if not device.is_active:
        logger.warning(f"Device is inactive: UID={uid}, Name={device.name}")
        return JsonResponse({
            "error": "Gerät ist inaktiv",
            "error_code": "DEVICE_INACTIVE",
            "maintenance_mode": True,
            "suggestion": f"Aktivieren Sie das Gerät '{device.name}' im Admin-Panel"
        }, status=503)
    
    logger.info(f"Found device: {device.name} (UID: {uid})")
    
    # Get all playlist entries (active and inactive for debugging)
    all_entries = device.playlist_entries.all().prefetch_related('track_filter').order_by('order', 'id')
    active_entries = device.playlist_entries.filter(is_active=True).prefetch_related('track_filter').order_by('order', 'id')
    inactive_entries = device.playlist_entries.filter(is_active=False).prefetch_related('track_filter').order_by('order', 'id')
    
    logger.info(f"Device {device.name}: {all_entries.count()} total entries, {active_entries.count()} active, {inactive_entries.count()} inactive")
    
    playlist = []
    for entry in active_entries:
        track_ids = list(entry.track_filter.values_list('id', flat=True)) if entry.track_filter.exists() else None
        playlist.append({
            'id': entry.id,
            'view_type': entry.view_type,
            'event_filter_id': entry.event_filter.id if entry.event_filter else None,
            'event_filter_name': entry.event_filter.name if entry.event_filter else None,
            'group_filter_id': entry.group_filter.id if entry.group_filter else None,
            'group_filter_name': entry.group_filter.name if entry.group_filter else None,
            'track_filter_ids': track_ids,
            'display_duration': entry.display_duration,
            'order': entry.order,
        })
    
    response_data = {
        'device_id': device.id,
        'device_name': device.name,
        'playlist': playlist,
        'updated_at': device.updated_at.isoformat(),
        'total_entries': all_entries.count(),
        'active_entries': active_entries.count(),
        'inactive_entries': inactive_entries.count(),
    }
    
    return JsonResponse(response_data)


@csrf_exempt
@csrf_exempt
@retry_on_db_lock(max_retries=10, base_delay=0.05, max_delay=5.0)
def kiosk_get_commands(request, uid: str):
    """Returns pending commands for a Kiosk device and marks them as processed."""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        device = KioskDevice.objects.get(uid=uid)
    except KioskDevice.DoesNotExist:
        return JsonResponse({
            "error": "Gerät nicht gefunden",
            "error_code": "DEVICE_NOT_FOUND",
            "uid": uid
        }, status=404)
    
    # Get commands from queue
    commands = []
    if isinstance(device.command_queue, list):
        commands = device.command_queue.copy()
        # Clear commands after reading (they will be executed by the client)
        device.clear_commands()
    
    response_data = {
        'device_id': device.id,
        'commands': commands,
        'brightness': device.brightness,
    }
    
    return JsonResponse(response_data)


@csrf_exempt
def get_cyclist_distance(request, identifier):
    """
    Get cyclist distance data (total and optionally for a time period).
    
    Query parameters:
    - start_date (optional): Start date in format YYYY-MM-DD
    - end_date (optional): End date in format YYYY-MM-DD
    
    Returns:
    - distance_total: Total distance (always)
    - distance_period: Distance for the specified period (if dates provided)
    - period_start: Start of period (if dates provided)
    - period_end: End of period (if dates provided)
    """
    api_key_header = request.headers.get('X-Api-Key')
    is_valid, _device = validate_api_key(api_key_header)
    if not is_valid:
        return JsonResponse({"error": _("Ungültiger API-Schlüssel")}, status=403)
    
    # Find cyclist by user_id, id_tag, or mc_username
    try:
        cyclist_obj = Cyclist.objects.get(
            Q(user_id__iexact=identifier) | 
            Q(id_tag__iexact=identifier) | 
            Q(mc_username__iexact=identifier)
        )
    except Cyclist.DoesNotExist:
        return JsonResponse({
            "error": _("Radler nicht gefunden"),
            "identifier": identifier
        }, status=404)
    
    # Build response with total distance
    response_data = {
        "cyclist_id": cyclist_obj.id,
        "user_id": cyclist_obj.user_id,
        "id_tag": cyclist_obj.id_tag,
        "mc_username": cyclist_obj.mc_username,
        "distance_total": float(cyclist_obj.distance_total or 0),
    }
    
    # Parse optional date range
    start_date = request.GET.get('start_date', '').strip()
    end_date = request.GET.get('end_date', '').strip()
    
    if start_date and end_date:
        try:
            start_dt = timezone.make_aware(datetime.strptime(start_date, '%Y-%m-%d'))
            end_dt = timezone.make_aware(datetime.strptime(end_date, '%Y-%m-%d').replace(
                hour=23, minute=59, second=59, microsecond=999999
            ))
            
            # Validate date range
            if start_dt > end_dt:
                return JsonResponse({
                    "error": _("start_date muss vor end_date liegen")
                }, status=400)
            
            # Calculate distance for the period from HourlyMetrics
            period_distance = HourlyMetric.objects.filter(
                cyclist=cyclist_obj,
                timestamp__gte=start_dt,
                timestamp__lte=end_dt
            ).aggregate(
                total=Sum('distance_km')
            )['total'] or Decimal('0.00000')
            
            # Add active sessions that fall within the period
            active_sessions = CyclistDeviceCurrentMileage.objects.filter(
                cyclist=cyclist_obj,
                last_activity__gte=start_dt,
                last_activity__lte=end_dt,
                cumulative_mileage__gt=0
            )
            
            for session in active_sessions:
                # Only count session distance if it overlaps with the period
                if session.start_time and session.start_time <= end_dt:
                    period_distance += session.cumulative_mileage or Decimal('0')
            
            response_data.update({
                "distance_period": float(period_distance),
                "period_start": start_date,
                "period_end": end_date,
            })
        except ValueError as e:
            return JsonResponse({
                "error": _("Ungültiges Datumsformat. Verwenden Sie YYYY-MM-DD"),
                "details": str(e)
            }, status=400)
    elif start_date or end_date:
        # Both dates must be provided if one is given
        return JsonResponse({
            "error": _("start_date und end_date müssen beide angegeben werden")
        }, status=400)
    
    return JsonResponse(response_data)


@csrf_exempt
def get_group_distance(request, identifier):
    """
    Get group distance data (total and optionally for a time period).
    
    Query parameters:
    - start_date (optional): Start date in format YYYY-MM-DD
    - end_date (optional): End date in format YYYY-MM-DD
    - include_children (optional): Include child groups (default: false)
    
    Returns:
    - distance_total: Total distance (always)
    - distance_period: Distance for the specified period (if dates provided)
    - period_start: Start of period (if dates provided)
    - period_end: End of period (if dates provided)
    - children: Child groups data (if include_children=true)
    """
    api_key_header = request.headers.get('X-Api-Key')
    is_valid, _device = validate_api_key(api_key_header)
    if not is_valid:
        return JsonResponse({"error": _("Ungültiger API-Schlüssel")}, status=403)
    
    # Find group by ID or name
    try:
        if identifier.isdigit():
            group_obj = Group.objects.get(id=int(identifier))
        else:
            group_obj = Group.objects.get(name__iexact=identifier)
    except Group.DoesNotExist:
        return JsonResponse({
            "error": _("Gruppe nicht gefunden"),
            "identifier": identifier
        }, status=404)
    except ValueError:
        return JsonResponse({
            "error": _("Ungültige Gruppen-ID"),
            "identifier": identifier
        }, status=400)
    
    # Build response with total distance
    response_data = {
        "group_id": group_obj.id,
        "name": group_obj.name,
        "short_name": group_obj.short_name,
        "group_type": group_obj.group_type.name if group_obj.group_type else None,
        "distance_total": float(group_obj.distance_total or 0),
    }
    
    # Parse optional date range
    start_date = request.GET.get('start_date', '').strip()
    end_date = request.GET.get('end_date', '').strip()
    include_children = request.GET.get('include_children', 'false').strip().lower() == 'true'
    
    if start_date and end_date:
        try:
            start_dt = timezone.make_aware(datetime.strptime(start_date, '%Y-%m-%d'))
            end_dt = timezone.make_aware(datetime.strptime(end_date, '%Y-%m-%d').replace(
                hour=23, minute=59, second=59, microsecond=999999
            ))
            
            # Validate date range
            if start_dt > end_dt:
                return JsonResponse({
                    "error": _("start_date muss vor end_date liegen")
                }, status=400)
            
            # Get group IDs to query (include children if requested)
            if include_children:
                # Get all descendant groups
                from .analytics import _get_descendant_group_ids
                group_ids = _get_descendant_group_ids(group_obj)
                group_ids.append(group_obj.id)
            else:
                group_ids = [group_obj.id]
            
            # Calculate distance for the period from HourlyMetrics
            period_distance = HourlyMetric.objects.filter(
                group_at_time_id__in=group_ids,
                timestamp__gte=start_dt,
                timestamp__lte=end_dt
            ).aggregate(
                total=Sum('distance_km')
            )['total'] or Decimal('0.00000')
            
            # Add active sessions that fall within the period
            active_sessions = CyclistDeviceCurrentMileage.objects.filter(
                cyclist__groups__id__in=group_ids,
                last_activity__gte=start_dt,
                last_activity__lte=end_dt,
                cumulative_mileage__gt=0
            ).distinct()
            
            for session in active_sessions:
                # Only count session distance if it overlaps with the period
                if session.start_time and session.start_time <= end_dt:
                    period_distance += session.cumulative_mileage or Decimal('0')
            
            response_data.update({
                "distance_period": float(period_distance),
                "period_start": start_date,
                "period_end": end_date,
                "include_children": include_children,
            })
        except ValueError as e:
            return JsonResponse({
                "error": _("Ungültiges Datumsformat. Verwenden Sie YYYY-MM-DD"),
                "details": str(e)
            }, status=400)
    elif start_date or end_date:
        # Both dates must be provided if one is given
        return JsonResponse({
            "error": _("start_date und end_date müssen beide angegeben werden")
        }, status=400)
    
    # Include child groups data if requested
    if include_children:
        children = []
        # Get direct children (groups with this group as parent)
        child_groups = Group.objects.filter(parent=group_obj, is_visible=True)
        for child in child_groups:
            children.append({
                "group_id": child.id,
                "name": child.name,
                "short_name": child.short_name,
                "group_type": child.group_type.name if child.group_type else None,
                "distance_total": float(child.distance_total or 0),
            })
        response_data["children"] = children
    
    return JsonResponse(response_data)


@csrf_exempt
def get_leaderboard_cyclists(request):
    """
    Get leaderboard of top cyclists by distance.
    
    Query parameters:
    - sort: 'daily' or 'total' (default: 'total')
    - limit: Number of cyclists to return (default: 10, max: 100)
    - group_id: Filter by group ID (optional)
    """
    api_key_header = request.headers.get('X-Api-Key')
    is_valid, _device = validate_api_key(api_key_header)
    if not is_valid:
        return JsonResponse({"error": _("Ungültiger API-Schlüssel")}, status=403)
    
    sort = request.GET.get('sort', 'total').strip().lower()
    if sort not in ['daily', 'total']:
        sort = 'total'
    
    try:
        limit = int(request.GET.get('limit', 10))
        limit = min(max(limit, 1), 100)  # Between 1 and 100
    except (ValueError, TypeError):
        limit = 10
    
    group_id = request.GET.get('group_id', '').strip()
    
    # Base queryset
    cyclists_qs = Cyclist.objects.filter(is_visible=True)
    
    # Filter by group if specified
    if group_id:
        try:
            group = Group.objects.get(pk=int(group_id))
            from .analytics import _get_descendant_group_ids
            group_ids = _get_descendant_group_ids(group)
            group_ids.append(group.id)
            cyclists_qs = cyclists_qs.filter(groups__id__in=group_ids).distinct()
        except (ValueError, Group.DoesNotExist):
            return JsonResponse({
                "error": _("Gruppe nicht gefunden"),
                "group_id": group_id
            }, status=404)
    
    # Calculate daily distance if needed
    if sort == 'daily':
        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Get daily distance from HourlyMetrics (considering snapshots)
        cyclist_ids = list(cyclists_qs.values_list('id', flat=True))
        
        # Get snapshot dates for cyclists (via their groups)
        cyclist_groups_map: Dict[int, List[int]] = {}
        for cyclist in cyclists_qs:
            cyclist_groups_map[cyclist.id] = list(cyclist.groups.values_list('id', flat=True))
        
        all_group_ids = set()
        for group_ids in cyclist_groups_map.values():
            all_group_ids.update(group_ids)
        
        snapshot_dates = _get_latest_snapshot_date_for_groups(list(all_group_ids))
        
        # For each cyclist, find the latest snapshot date from their groups
        cyclist_snapshot_dates: Dict[int, Optional[timezone.datetime]] = {}
        for cyclist_id, group_ids in cyclist_groups_map.items():
            latest_date = None
            for group_id in group_ids:
                group_date = snapshot_dates.get(group_id)
                if group_date and (latest_date is None or group_date > latest_date):
                    latest_date = group_date
            cyclist_snapshot_dates[cyclist_id] = latest_date
        
        # Calculate daily metrics per cyclist (considering snapshot dates)
        daily_by_cyclist: Dict[int, float] = {}
        for cyclist_id in cyclist_ids:
            snapshot_date = cyclist_snapshot_dates.get(cyclist_id)
            # Use max of today_start and snapshot_date
            effective_start = max(today_start, snapshot_date) if snapshot_date else today_start
            
            daily_metrics = HourlyMetric.objects.filter(
                cyclist_id=cyclist_id,
                timestamp__gte=effective_start,
                group_at_time__isnull=False
            ).aggregate(
                daily_total=Sum('distance_km')
            )
            daily_by_cyclist[cyclist_id] = float(daily_metrics['daily_total'] or 0.0)
        
        # Add active sessions
        active_sessions = CyclistDeviceCurrentMileage.objects.filter(
            cyclist__in=cyclists_qs,
            last_activity__gte=today_start,
            cumulative_mileage__gt=0
        ).select_related('cyclist')
        
        for session in active_sessions:
            cyclist_id = session.cyclist.id
            if cyclist_id not in daily_by_cyclist:
                daily_by_cyclist[cyclist_id] = 0.0
            daily_by_cyclist[cyclist_id] += float(session.cumulative_mileage or 0)
        
        # Get cyclists with their daily totals
        cyclists_list = []
        for cyclist in cyclists_qs.select_related().prefetch_related('groups'):
            daily_km = daily_by_cyclist.get(cyclist.id, 0.0)
            primary_group = cyclist.groups.filter(is_visible=True).first()
            if not primary_group:
                primary_group = cyclist.groups.first()
            
            cyclists_list.append({
                'cyclist_id': cyclist.id,
                'user_id': cyclist.user_id,
                'id_tag': cyclist.id_tag,
                'mc_username': cyclist.mc_username,
                'distance_total': float(cyclist.distance_total or 0),
                'distance_daily': daily_km,
                'group_name': primary_group.name if primary_group else None,
                'group_short_name': primary_group.short_name if primary_group else None,
            })
        
        # Sort by daily distance
        cyclists_list.sort(key=lambda x: (x['distance_daily'], x['distance_total']), reverse=True)
    else:
        # Sort by total distance
        cyclists_list = []
        for cyclist in cyclists_qs.order_by('-distance_total').select_related().prefetch_related('groups')[:limit * 2]:
            primary_group = cyclist.groups.filter(is_visible=True).first()
            if not primary_group:
                primary_group = cyclist.groups.first()
            
            cyclists_list.append({
                'cyclist_id': cyclist.id,
                'user_id': cyclist.user_id,
                'id_tag': cyclist.id_tag,
                'mc_username': cyclist.mc_username,
                'distance_total': float(cyclist.distance_total or 0),
                'group_name': primary_group.name if primary_group else None,
                'group_short_name': primary_group.short_name if primary_group else None,
            })
    
    # Limit results
    cyclists_list = cyclists_list[:limit]
    
    # Add rank
    for i, cyclist_data in enumerate(cyclists_list, 1):
        cyclist_data['rank'] = i
    
    return JsonResponse({
        'sort': sort,
        'limit': limit,
        'cyclists': cyclists_list
    })


@csrf_exempt
def get_leaderboard_groups(request):
    """
    Get leaderboard of top groups by distance.
    
    Query parameters:
    - sort: 'daily', 'total', 'weekly', 'monthly' (default: 'total')
    - limit: Number of groups to return (default: 10, max: 100)
    - parent_group_id: Filter by parent group ID (optional)
    """
    api_key_header = request.headers.get('X-Api-Key')
    is_valid, _device = validate_api_key(api_key_header)
    if not is_valid:
        return JsonResponse({"error": _("Ungültiger API-Schlüssel")}, status=403)
    
    sort = request.GET.get('sort', 'total').strip().lower()
    if sort not in ['daily', 'total', 'weekly', 'monthly']:
        sort = 'total'
    
    try:
        limit = int(request.GET.get('limit', 10))
        limit = min(max(limit, 1), 100)  # Between 1 and 100
    except (ValueError, TypeError):
        limit = 10
    
    parent_group_id = request.GET.get('parent_group_id', '').strip()
    
    now = timezone.now()
    
    # Base queryset
    groups_qs = Group.objects.filter(is_visible=True)
    
    # Filter by parent group if specified
    if parent_group_id:
        try:
            parent_group = Group.objects.get(pk=int(parent_group_id))
            from .analytics import _get_descendant_group_ids
            group_ids = _get_descendant_group_ids(parent_group)
            group_ids.append(parent_group.id)
            groups_qs = groups_qs.filter(id__in=group_ids)
        except (ValueError, Group.DoesNotExist):
            return JsonResponse({
                "error": _("Übergeordnete Gruppe nicht gefunden"),
                "parent_group_id": parent_group_id
            }, status=404)
    
    # Calculate period distances (considering snapshots)
    group_ids = list(groups_qs.values_list('id', flat=True))
    snapshot_dates = _get_latest_snapshot_date_for_groups(group_ids)
    
    period_by_group: Dict[int, float] = {}
    
    if sort == 'daily':
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        for group_id in group_ids:
            snapshot_date = snapshot_dates.get(group_id)
            # Use max of today_start and snapshot_date
            effective_start = max(today_start, snapshot_date) if snapshot_date else today_start
            
            period_metrics = HourlyMetric.objects.filter(
                group_at_time_id=group_id,
                timestamp__gte=effective_start
            ).aggregate(
                period_total=Sum('distance_km')
            )
            period_by_group[group_id] = float(period_metrics['period_total'] or 0.0)
    elif sort == 'weekly':
        days_since_monday = now.weekday()
        week_start = (now - timedelta(days=days_since_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
        for group_id in group_ids:
            snapshot_date = snapshot_dates.get(group_id)
            # Use max of week_start and snapshot_date
            effective_start = max(week_start, snapshot_date) if snapshot_date else week_start
            
            period_metrics = HourlyMetric.objects.filter(
                group_at_time_id=group_id,
                timestamp__gte=effective_start
            ).aggregate(
                period_total=Sum('distance_km')
            )
            period_by_group[group_id] = float(period_metrics['period_total'] or 0.0)
    elif sort == 'monthly':
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        for group_id in group_ids:
            snapshot_date = snapshot_dates.get(group_id)
            # Use max of month_start and snapshot_date
            effective_start = max(month_start, snapshot_date) if snapshot_date else month_start
            
            period_metrics = HourlyMetric.objects.filter(
                group_at_time_id=group_id,
                timestamp__gte=effective_start
            ).aggregate(
                period_total=Sum('distance_km')
            )
            period_by_group[group_id] = float(period_metrics['period_total'] or 0.0)
    else:
        # For 'total' sort, use existing helper function
        pass
    
    # Add active sessions for daily/weekly/monthly
    if sort in ['daily', 'weekly', 'monthly']:
        if sort == 'daily':
            period_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif sort == 'weekly':
            days_since_monday = now.weekday()
            period_start = (now - timedelta(days=days_since_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
        else:  # monthly
            period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        active_sessions = CyclistDeviceCurrentMileage.objects.filter(
            cyclist__groups__in=groups_qs,
            last_activity__gte=period_start,
            cumulative_mileage__gt=0
        ).select_related('cyclist').prefetch_related('cyclist__groups')
        
        for session in active_sessions:
            for group in session.cyclist.groups.filter(id__in=groups_qs.values_list('id', flat=True)):
                if group.id not in period_by_group:
                    period_by_group[group.id] = 0.0
                period_by_group[group.id] += float(session.cumulative_mileage or 0)
    
    # Build groups list
    groups_list = []
    for group in groups_qs.select_related('parent'):
        period_km = period_by_group.get(group.id, 0.0) if sort != 'total' else None
        
        # Get parent group name
        parent_group_name = None
        if group.parent:
            parent_group_name = group.parent.name
        
        groups_list.append({
            'group_id': group.id,
            'name': group.name,
            'short_name': group.short_name,
            'group_type': group.group_type.name if group.group_type else None,
            'distance_total': float(group.distance_total or 0),
            'distance_period': period_km,
            'parent_group_name': parent_group_name,
        })
    
    # Sort
    if sort == 'total':
        groups_list.sort(key=lambda x: x['distance_total'], reverse=True)
    else:
        groups_list.sort(key=lambda x: (x['distance_period'] or 0, x['distance_total']), reverse=True)
    
    # Limit results
    groups_list = groups_list[:limit]
    
    # Add rank
    for i, group in enumerate(groups_list, 1):
        group['rank'] = i
    
    return JsonResponse({
        'sort': sort,
        'limit': limit,
        'groups': groups_list
    })


@csrf_exempt
def get_active_cyclists(request):
    """
    Get list of currently active cyclists (similar to live ticker).
    
    Query parameters:
    - group_id: Filter by group ID (optional)
    - limit: Number of cyclists to return (default: 10, max: 50)
    - active_seconds: Seconds of inactivity threshold (default: 60)
    """
    api_key_header = request.headers.get('X-Api-Key')
    is_valid, _device = validate_api_key(api_key_header)
    if not is_valid:
        return JsonResponse({"error": _("Ungültiger API-Schlüssel")}, status=403)
    
    try:
        limit = int(request.GET.get('limit', 10))
        limit = min(max(limit, 1), 50)  # Between 1 and 50
    except (ValueError, TypeError):
        limit = 10
    
    try:
        active_seconds = int(request.GET.get('active_seconds', 60))
        active_seconds = max(active_seconds, 1)
    except (ValueError, TypeError):
        active_seconds = 60
    
    group_id = request.GET.get('group_id', '').strip()
    
    now = timezone.now()
    active_cutoff = now - timedelta(seconds=active_seconds)
    
    # Base queryset
    cyclists_qs = Cyclist.objects.filter(
        is_visible=True,
        last_active__isnull=False,
        last_active__gte=active_cutoff
    ).select_related('cyclistdevicecurrentmileage').prefetch_related('groups')
    
    # Filter by group if specified
    if group_id:
        try:
            group = Group.objects.get(pk=int(group_id))
            from .analytics import _get_descendant_group_ids
            group_ids = _get_descendant_group_ids(group)
            group_ids.append(group.id)
            cyclists_qs = cyclists_qs.filter(groups__id__in=group_ids).distinct()
        except (ValueError, Group.DoesNotExist):
            return JsonResponse({
                "error": _("Gruppe nicht gefunden"),
                "group_id": group_id
            }, status=404)
    
    # Get active cyclists with session data
    active_cyclists = []
    for cyclist in cyclists_qs.order_by('-last_active')[:limit * 2]:
        session_km = 0.0
        device_name = "Unbekannt"
        
        try:
            mileage_obj = cyclist.cyclistdevicecurrentmileage
            if mileage_obj and mileage_obj.cumulative_mileage is not None:
                session_km = float(mileage_obj.cumulative_mileage)
            if mileage_obj and mileage_obj.device:
                device_name = mileage_obj.device.display_name or mileage_obj.device.name
        except (AttributeError, CyclistDeviceCurrentMileage.DoesNotExist):
            pass
        
        # Get primary group
        primary_group = cyclist.groups.filter(is_visible=True).first()
        if not primary_group:
            primary_group = cyclist.groups.first()
        
        active_cyclists.append({
            'cyclist_id': cyclist.id,
            'user_id': cyclist.user_id,
            'id_tag': cyclist.id_tag,
            'mc_username': cyclist.mc_username,
            'session_km': session_km,
            'distance_total': float(cyclist.distance_total or 0),
            'device_name': device_name,
            'last_active': cyclist.last_active.isoformat() if cyclist.last_active else None,
            'group_name': primary_group.name if primary_group else None,
            'group_short_name': primary_group.short_name if primary_group else None,
        })
    
    # Sort by session_km
    active_cyclists.sort(key=lambda x: x['session_km'], reverse=True)
    active_cyclists = active_cyclists[:limit]
    
    return JsonResponse({
        'active_seconds': active_seconds,
        'limit': limit,
        'cyclists': active_cyclists
    })


@csrf_exempt
def list_cyclists(request):
    """
    Get paginated list of all cyclists.
    
    Query parameters:
    - page: Page number (default: 1)
    - page_size: Items per page (default: 50, max: 100)
    - is_visible: Filter by visibility (default: true)
    - group_id: Filter by group ID (optional)
    """
    api_key_header = request.headers.get('X-Api-Key')
    is_valid, _device = validate_api_key(api_key_header)
    if not is_valid:
        return JsonResponse({"error": _("Ungültiger API-Schlüssel")}, status=403)
    
    try:
        page = int(request.GET.get('page', 1))
        page = max(page, 1)
    except (ValueError, TypeError):
        page = 1
    
    try:
        page_size = int(request.GET.get('page_size', 50))
        page_size = min(max(page_size, 1), 100)  # Between 1 and 100
    except (ValueError, TypeError):
        page_size = 50
    
    is_visible = request.GET.get('is_visible', 'true').strip().lower() == 'true'
    group_id = request.GET.get('group_id', '').strip()
    
    # Base queryset
    cyclists_qs = Cyclist.objects.all()
    
    if is_visible:
        cyclists_qs = cyclists_qs.filter(is_visible=True)
    
    # Filter by group if specified
    if group_id:
        try:
            group = Group.objects.get(pk=int(group_id))
            from .analytics import _get_descendant_group_ids
            group_ids = _get_descendant_group_ids(group)
            group_ids.append(group.id)
            cyclists_qs = cyclists_qs.filter(groups__id__in=group_ids).distinct()
        except (ValueError, Group.DoesNotExist):
            return JsonResponse({
                "error": _("Gruppe nicht gefunden"),
                "group_id": group_id
            }, status=404)
    
    # Pagination
    total_count = cyclists_qs.count()
    total_pages = (total_count + page_size - 1) // page_size
    
    offset = (page - 1) * page_size
    cyclists_list = []
    
    for cyclist in cyclists_qs.order_by('user_id')[offset:offset + page_size]:
        primary_group = cyclist.groups.filter(is_visible=True).first()
        if not primary_group:
            primary_group = cyclist.groups.first()
        
        cyclists_list.append({
            'cyclist_id': cyclist.id,
            'user_id': cyclist.user_id,
            'id_tag': cyclist.id_tag,
            'mc_username': cyclist.mc_username,
            'distance_total': float(cyclist.distance_total or 0),
            'coins_total': cyclist.coins_total,
            'coins_spendable': cyclist.coins_spendable,
            'last_active': cyclist.last_active.isoformat() if cyclist.last_active else None,
            'group_name': primary_group.name if primary_group else None,
            'group_short_name': primary_group.short_name if primary_group else None,
        })
    
    return JsonResponse({
        'page': page,
        'page_size': page_size,
        'total_count': total_count,
        'total_pages': total_pages,
        'cyclists': cyclists_list
    })


@csrf_exempt
def list_groups(request):
    """
    Get paginated list of all groups.
    
    Query parameters:
    - page: Page number (default: 1)
    - page_size: Items per page (default: 50, max: 100)
    - is_visible: Filter by visibility (default: true)
    - parent_id: Filter by parent group ID (optional)
    """
    api_key_header = request.headers.get('X-Api-Key')
    is_valid, _device = validate_api_key(api_key_header)
    if not is_valid:
        return JsonResponse({"error": _("Ungültiger API-Schlüssel")}, status=403)
    
    try:
        page = int(request.GET.get('page', 1))
        page = max(page, 1)
    except (ValueError, TypeError):
        page = 1
    
    try:
        page_size = int(request.GET.get('page_size', 50))
        page_size = min(max(page_size, 1), 100)  # Between 1 and 100
    except (ValueError, TypeError):
        page_size = 50
    
    is_visible = request.GET.get('is_visible', 'true').strip().lower() == 'true'
    parent_id = request.GET.get('parent_id', '').strip()
    
    # Base queryset
    groups_qs = Group.objects.all()
    
    if is_visible:
        groups_qs = groups_qs.filter(is_visible=True)
    
    # Filter by parent if specified
    if parent_id:
        try:
            parent_group = Group.objects.get(pk=int(parent_id))
            groups_qs = groups_qs.filter(parent=parent_group)
        except (ValueError, Group.DoesNotExist):
            return JsonResponse({
                "error": _("Übergeordnete Gruppe nicht gefunden"),
                "parent_id": parent_id
            }, status=404)
    
    # Pagination
    total_count = groups_qs.count()
    total_pages = (total_count + page_size - 1) // page_size
    
    offset = (page - 1) * page_size
    groups_list = []
    
    for group in groups_qs.order_by('name')[offset:offset + page_size]:
        groups_list.append({
            'group_id': group.id,
            'name': group.name,
            'short_name': group.short_name,
            'group_type': group.group_type.name if group.group_type else None,
            'distance_total': float(group.distance_total or 0),
            'coins_total': group.coins_total,
            'parent_group_id': group.parent.id if group.parent else None,
            'parent_group_name': group.parent.name if group.parent else None,
        })
    
    return JsonResponse({
        'page': page,
        'page_size': page_size,
        'total_count': total_count,
        'total_pages': total_pages,
        'groups': groups_list
    })


@csrf_exempt
def get_milestones(request):
    """
    Get milestone status for active travel tracks.
    
    Query parameters:
    - track_id: Filter by track ID (optional)
    """
    api_key_header = request.headers.get('X-Api-Key')
    is_valid, _device = validate_api_key(api_key_header)
    if not is_valid:
        return JsonResponse({"error": _("Ungültiger API-Schlüssel")}, status=403)
    
    track_id = request.GET.get('track_id', '').strip()
    
    from .models import TravelTrack, Milestone
    
    # Get active tracks
    tracks_qs = TravelTrack.objects.filter(is_active=True, is_visible_on_map=True)
    
    if track_id:
        try:
            tracks_qs = tracks_qs.filter(pk=int(track_id))
        except ValueError:
            return JsonResponse({
                "error": _("Ungültige Track-ID"),
                "track_id": track_id
            }, status=400)
    
    milestones_data = []
    for track in tracks_qs:
        if not track.is_currently_active():
            continue
        
        track_milestones = []
        for milestone in track.milestones.filter(
            gps_latitude__isnull=False,
            gps_longitude__isnull=False
        ).exclude(distance_km=0).select_related('winner_group'):
            track_milestones.append({
                'milestone_id': milestone.id,
                'name': milestone.name,
                'distance_km': float(milestone.distance_km),
                'gps_latitude': float(milestone.gps_latitude),
                'gps_longitude': float(milestone.gps_longitude),
                'reward_text': milestone.reward_text or '',
                'description': milestone.description or '',
                'external_link': milestone.external_link or '',
                'is_reached': milestone.winner_group is not None,
                'winner_group_id': milestone.winner_group.id if milestone.winner_group else None,
                'winner_group_name': milestone.winner_group.name if milestone.winner_group else None,
                'reached_at': milestone.reached_at.isoformat() if milestone.reached_at else None,
            })
        
        milestones_data.append({
            'track_id': track.id,
            'track_name': track.name,
            'total_length_km': float(track.total_length_km),
            'milestones': track_milestones
        })
    
    return JsonResponse({
        'milestones': milestones_data
    })


@csrf_exempt
def get_statistics(request):
    """
    Get aggregated statistics (similar to analytics but public API).
    
    Query parameters:
    - start_date: Start date in format YYYY-MM-DD (optional)
    - end_date: End date in format YYYY-MM-DD (optional)
    - group_id: Filter by group ID (optional)
    """
    api_key_header = request.headers.get('X-Api-Key')
    is_valid, _device = validate_api_key(api_key_header)
    if not is_valid:
        return JsonResponse({"error": _("Ungültiger API-Schlüssel")}, status=403)
    
    start_date = request.GET.get('start_date', '').strip()
    end_date = request.GET.get('end_date', '').strip()
    group_id = request.GET.get('group_id', '').strip()
    
    # Parse dates
    if start_date and end_date:
        try:
            start_dt = timezone.make_aware(datetime.strptime(start_date, '%Y-%m-%d'))
            end_dt = timezone.make_aware(datetime.strptime(end_date, '%Y-%m-%d').replace(
                hour=23, minute=59, second=59, microsecond=999999
            ))
            
            if start_dt > end_dt:
                return JsonResponse({
                    "error": _("start_date muss vor end_date liegen")
                }, status=400)
        except ValueError as e:
            return JsonResponse({
                "error": _("Ungültiges Datumsformat. Verwenden Sie YYYY-MM-DD"),
                "details": str(e)
            }, status=400)
    else:
        # Default to last 30 days
        end_dt = timezone.now()
        start_dt = end_dt - timedelta(days=30)
    
    # Build metrics queryset
    metrics_qs = HourlyMetric.objects.filter(
        timestamp__gte=start_dt,
        timestamp__lte=end_dt,
        group_at_time__isnull=False
    )
    
    # Filter by group if specified
    if group_id:
        try:
            group = Group.objects.get(pk=int(group_id))
            from .analytics import _get_descendant_group_ids
            group_ids = _get_descendant_group_ids(group)
            group_ids.append(group.id)
            metrics_qs = metrics_qs.filter(group_at_time_id__in=group_ids)
        except (ValueError, Group.DoesNotExist):
            return JsonResponse({
                "error": _("Gruppe nicht gefunden"),
                "group_id": group_id
            }, status=404)
    
    # Calculate total distance
    total_distance = metrics_qs.aggregate(
        total=Sum('distance_km')
    )['total'] or Decimal('0.00000')
    
    # Add active sessions
    if group_id:
        try:
            group = Group.objects.get(pk=int(group_id))
            from .analytics import _get_descendant_group_ids
            group_ids = _get_descendant_group_ids(group)
            group_ids.append(group.id)
            active_sessions = CyclistDeviceCurrentMileage.objects.filter(
                cyclist__groups__id__in=group_ids,
                last_activity__gte=start_dt,
                last_activity__lte=end_dt,
                cumulative_mileage__gt=0
            ).distinct()
        except (ValueError, Group.DoesNotExist):
            active_sessions = CyclistDeviceCurrentMileage.objects.none()
    else:
        active_sessions = CyclistDeviceCurrentMileage.objects.filter(
            last_activity__gte=start_dt,
            last_activity__lte=end_dt,
            cumulative_mileage__gt=0
        )
    
    for session in active_sessions:
        total_distance += session.cumulative_mileage or Decimal('0')
    
    # Get top groups
    top_groups = Group.objects.filter(is_visible=True)
    if group_id:
        try:
            group = Group.objects.get(pk=int(group_id))
            from .analytics import _get_descendant_group_ids
            group_ids = _get_descendant_group_ids(group)
            group_ids.append(group.id)
            top_groups = top_groups.filter(id__in=group_ids)
        except (ValueError, Group.DoesNotExist):
            pass
    
    top_groups_list = [
        {
            'group_id': g.id,
            'name': g.name,
            'short_name': g.short_name,
            'group_type': g.group_type.name if g.group_type else None,
            'distance_total': float(g.distance_total or 0),
        }
        for g in top_groups.order_by('-distance_total')[:10]
        if g.distance_total and g.distance_total > 0
    ]
    
    # Get top cyclists
    top_cyclists_metrics = metrics_qs.filter(cyclist__isnull=False).values(
        'cyclist_id', 'cyclist__user_id', 'cyclist__id_tag'
    ).annotate(
        total_distance=Sum('distance_km')
    ).order_by('-total_distance')[:10]
    
    top_cyclists_list = []
    for item in top_cyclists_metrics:
        top_cyclists_list.append({
            'cyclist_id': item.get('cyclist_id'),
            'user_id': item.get('cyclist__user_id'),
            'id_tag': item.get('cyclist__id_tag'),
            'distance_period': float(item.get('total_distance') or 0),
        })
    
    return JsonResponse({
        'period_start': start_dt.strftime('%Y-%m-%d'),
        'period_end': end_dt.strftime('%Y-%m-%d'),
        'total_distance': float(total_distance),
        'top_groups': top_groups_list,
        'top_cyclists': top_cyclists_list,
    })


# --- DEVICE MANAGEMENT API ENDPOINTS ---

@csrf_exempt
def device_config_report(request: HttpRequest) -> JsonResponse:
    """
    Endpoint for devices to report their current configuration on boot.
    
    Expected JSON payload:
    {
        "device_id": "device_name",
        "config": {
            "device_name": "...",
            "default_id_tag": "...",
            "send_interval_seconds": 60,
            ...
        }
    }
    """
    try:
        if request.method != 'POST':
            return JsonResponse({"error": _("Methode nicht erlaubt")}, status=405)
        
        data = json.loads(request.body) if request.body else {}
        device_id = data.get('device_id')
        reported_config = data.get('config', {})
        
        if not device_id:
            return JsonResponse({"error": _("device_id ist erforderlich")}, status=400)
        
        # Validate API key (device-specific or global)
        is_valid, device, config = validate_device_api_key(request, device_id)
        if not is_valid:
            logger.warning(f"[device_config_report] Invalid API key for device {device_id}")
            return JsonResponse({"error": _("Ungültiger API-Key")}, status=403)
        
        # If device not found from API key, try to get it by name
        if not device:
            try:
                device = Device.objects.get(name=device_id)
            except Device.DoesNotExist:
                return JsonResponse({"error": _("Gerät nicht gefunden")}, status=404)
        
        # Get or create device configuration
        config, created = DeviceConfiguration.objects.get_or_create(
            device=device,
            defaults={
                'device_name': reported_config.get('device_name', ''),
                'default_id_tag': reported_config.get('default_id_tag', ''),
                'send_interval_seconds': reported_config.get('send_interval_seconds', 60),
                'server_url': reported_config.get('server_url', ''),
                'wifi_ssid': reported_config.get('wifi_ssid', ''),
                'wifi_password': reported_config.get('wifi_password', ''),
                'debug_mode': reported_config.get('debug_mode', False),
                'test_mode': reported_config.get('test_mode', False),
                'deep_sleep_seconds': reported_config.get('deep_sleep_seconds', 0),
                'wheel_size': reported_config.get('wheel_size', 2075.0),  # Default: 26 Zoll = 2075 mm
            }
        )
        
        # Refresh from database to ensure we have the latest request_config_comparison value
        config.refresh_from_db()
        
        logger.info(f"[device_config_report] Device {device_id}: request_config_comparison={config.request_config_comparison}, created={created}")
        
        # Only create report and compare if comparison was requested
        differences = []
        report = None
        
        if config.request_config_comparison:
            # Create configuration report only when comparison is requested
            report = DeviceConfigurationReport.objects.create(
                device=device,
                reported_config=reported_config
            )
            
            # Compare configurations and detect differences
            server_config_dict = config.to_dict()
            
            # Fields that should be excluded from comparison (security or device-only)
            excluded_fields = {'device_api_key', 'wifi_password'}  # device_api_key is not sent for security, wifi_password is never sent
            
            for key, server_value in server_config_dict.items():
                # Skip excluded fields
                if key in excluded_fields:
                    continue
                    
                device_value = reported_config.get(key)
                
                # Special handling for wheel_size: compare with 1mm tolerance
                if key == 'wheel_size':
                    try:
                        server_float = float(server_value) if server_value is not None else 0.0
                        device_float = float(device_value) if device_value is not None else 0.0
                        # Compare with 1mm tolerance
                        if abs(server_float - device_float) > 1.0:
                            diff_info = {
                                'field': key,
                                'server_value': str(server_value) if server_value is not None else '',
                                'device_value': str(device_value) if device_value is not None else ''
                            }
                            differences.append(diff_info)
                            
                            # Create diff record
                            DeviceConfigurationDiff.objects.create(
                                device=device,
                                report=report,
                                field_name=key,
                                server_value=str(server_float),
                                device_value=str(device_float),
                                is_resolved=False
                            )
                        # If within tolerance, no difference
                        continue
                    except (ValueError, TypeError):
                        # If conversion fails, fall through to string comparison
                        pass
                
                # Convert to strings for comparison (default for other fields)
                server_str = str(server_value) if server_value is not None else ''
                device_str = str(device_value) if device_value is not None else ''
                
                if server_str != device_str:
                    diff_info = {
                        'field': key,
                        'server_value': str(server_value) if server_value is not None else '',
                        'device_value': str(device_value) if device_value is not None else ''
                    }
                    differences.append(diff_info)
                    
                    # Create diff record
                    DeviceConfigurationDiff.objects.create(
                        device=device,
                        report=report,
                        field_name=key,
                        server_value=server_str,
                        device_value=device_str,
                        is_resolved=False
                    )
            
            report.has_differences = len(differences) > 0
            report.save()
            
            logger.info(f"[device_config_report] Config comparison completed for device {device_id}. Found {len(differences)} differences. Report ID: {report.id}")
            
            # Reset the flag after comparison
            config.request_config_comparison = False
            # Save immediately with update_fields to ensure the flag is persisted
            config.save(update_fields=['request_config_comparison', 'last_synced_at'])
            logger.info(f"[device_config_report] Flag request_config_comparison reset to False for device {device_id}")
        else:
            logger.info(f"[device_config_report] No comparison requested for device {device_id}. Skipping report creation.")
            # Update last_synced_at (always, even without comparison)
            config.last_synced_at = timezone.now()
            config.save(update_fields=['last_synced_at'])
        
        # Update device last_active and health
        device.last_active = timezone.now()
        device.save()
        
        # Update health status
        health, _ = DeviceHealth.objects.get_or_create(device=device)
        health.update_heartbeat()
        
        # Rotate API key if needed
        if config:
            config.rotate_api_key_if_needed()
        
        # Create audit log entry
        DeviceAuditLog.objects.create(
            device=device,
            action='config_synced',
            ip_address=get_client_ip(request),
            details={'differences_count': len(differences)}
        )
        
        if config.request_config_comparison:
            logger.info(f"[device_config_report] Device {device_id} reported config. Comparison requested. Differences: {len(differences)}")
            return JsonResponse({
                "success": True,
                "has_differences": len(differences) > 0,
                "differences": differences,
                "message": "Konfiguration erfolgreich gemeldet und verglichen"
            })
        else:
            logger.info(f"[device_config_report] Device {device_id} reported config. No comparison requested.")
            return JsonResponse({
                "success": True,
                "has_differences": False,
                "differences": [],
                "message": "Konfiguration erfolgreich gemeldet"
            })
        
    except json.JSONDecodeError as e:
        logger.error(f"[device_config_report] JSON decode error: {str(e)}")
        return JsonResponse({"error": _("Ungültiges JSON-Format")}, status=400)
    except Exception as e:
        logger.error(f"[device_config_report] Error: {str(e)}", exc_info=True)
        return JsonResponse({"error": _("Interner Serverfehler"), "details": str(e)}, status=500)


@csrf_exempt
def device_config_fetch(request: HttpRequest) -> JsonResponse:
    """
    Endpoint for devices to fetch their server-side configuration.
    
    GET /api/device/config/fetch?device_id=device_name
    """
    try:
        device_id = request.GET.get('device_id')
        if not device_id:
            return JsonResponse({"error": _("device_id-Parameter ist erforderlich")}, status=400)
        
        # Validate API key (device-specific or global)
        is_valid, device, config = validate_device_api_key(request, device_id)
        if not is_valid:
            logger.warning(f"[device_config_fetch] Invalid API key for device {device_id}")
            return JsonResponse({"error": _("Ungültiger API-Key")}, status=403)
        
        # If device not found from API key, try to get it by name
        if not device:
            try:
                device = Device.objects.get(name=device_id)
            except Device.DoesNotExist:
                return JsonResponse({"error": _("Gerät nicht gefunden")}, status=404)
        
        # Get device configuration
        try:
            config = device.configuration
        except DeviceConfiguration.DoesNotExist:
            # Return default configuration
            default_config = {
                # Note: device_name is NOT included - it's only configurable via device WebGUI
                # This ensures the device can always send data even if server config is missing
                'default_id_tag': '',
                'send_interval_seconds': 60,
                'server_url': '',
                'wifi_ssid': '',
                'wifi_password': '',
                'ap_password': '',
                'debug_mode': False,
                'test_mode': False,
                'test_distance_km': 0.01,
                'test_interval_seconds': 5,
                'deep_sleep_seconds': 0,
                'wheel_size': 2075.0,  # Default: 26 Zoll = 2075 mm
                'config_fetch_interval_seconds': 3600,
            }
            return JsonResponse({
                "success": True,
                "config": default_config,
                "message": _("Verwende Standard-Konfiguration")
            })
        
        # Update last_synced_at
        config.last_synced_at = timezone.now()
        config.save()
        
        # Update device last_active and health
        device.last_active = timezone.now()
        device.save()
        
        # Update health status
        health, _ = DeviceHealth.objects.get_or_create(device=device)
        health.update_heartbeat()
        
        logger.info(f"[device_config_fetch] Device {device_id} fetched configuration")
        
        return JsonResponse({
            "success": True,
            "config": config.to_dict()
        })
        
    except Exception as e:
        logger.error(f"[device_config_fetch] Error: {str(e)}", exc_info=True)
        return JsonResponse({"error": _("Interner Serverfehler"), "details": str(e)}, status=500)


@csrf_exempt
def device_firmware_download(request: HttpRequest) -> JsonResponse:
    """
    Endpoint for devices to download their assigned firmware.
    
    GET /api/device/firmware/download?device_id=device_name
    """
    try:
        device_id = request.GET.get('device_id')
        if not device_id:
            return JsonResponse({"error": _("device_id-Parameter ist erforderlich")}, status=400)
        
        # Validate API key (device-specific or global)
        is_valid, device, config = validate_device_api_key(request, device_id)
        if not is_valid:
            logger.warning(f"[device_firmware_download] Invalid API key for device {device_id}")
            return JsonResponse({"error": _("Ungültiger API-Key")}, status=403)
        
        # If device not found from API key, try to get it by name
        if not device:
            try:
                device = Device.objects.get(name=device_id)
            except Device.DoesNotExist:
                return JsonResponse({"error": _("Gerät nicht gefunden")}, status=404)
        
        # Get device configuration and assigned firmware
        try:
            config = device.configuration
            firmware = config.assigned_firmware
        except DeviceConfiguration.DoesNotExist:
            return JsonResponse({"error": _("Keine Konfiguration für Gerät gefunden")}, status=404)
        except AttributeError:
            return JsonResponse({"error": _("Keine Firmware für Gerät zugewiesen")}, status=404)
        
        if not firmware or not firmware.is_active:
            return JsonResponse({"error": _("Keine aktive Firmware zugewiesen")}, status=404)
        
        if not firmware.firmware_file:
            return JsonResponse({"error": _("Firmware-Datei nicht gefunden")}, status=404)
        
        # Return firmware metadata
        import os
        
        file_path = firmware.firmware_file.path
        if not os.path.exists(file_path):
            return JsonResponse({"error": _("Firmware-Datei auf dem Server nicht gefunden")}, status=404)
        
        # Get actual file size from filesystem
        actual_file_size = os.path.getsize(file_path)
        stored_file_size = firmware.file_size or 0
        
        # Log file size information
        logger.info(
            f"[device_firmware_download] Device {device_id} downloading firmware {firmware.version} "
            f"(stored_size={stored_file_size}, actual_size={actual_file_size})"
        )
        
        # Validate file size (ESP32 firmware should be at least several KB)
        if actual_file_size < 10000:  # At least 10 KB
            logger.error(
                f"[device_firmware_download] Firmware file too small: {actual_file_size} bytes. "
                f"File path: {file_path}, Stored size: {stored_file_size}"
            )
            return JsonResponse({
                "error": _("Firmware-Datei ist zu klein oder beschädigt"),
                "details": f"Dateigröße: {actual_file_size} Bytes (erwartet: > 10 KB)"
            }, status=500)
        
        # Warn if stored size doesn't match actual size
        if stored_file_size > 0 and abs(stored_file_size - actual_file_size) > 100:
            logger.warning(
                f"[device_firmware_download] File size mismatch: stored={stored_file_size}, actual={actual_file_size}"
            )
        
        # Return file response
        try:
            file_handle = open(file_path, 'rb')
            response = FileResponse(
                file_handle,
                content_type='application/octet-stream'
            )
            response['Content-Disposition'] = f'attachment; filename="{firmware.version}.bin"'
            response['X-Firmware-Version'] = firmware.version
            response['X-Firmware-Checksum'] = firmware.checksum_md5 or ''
            response['X-Firmware-Size'] = str(actual_file_size)
            response['Content-Length'] = str(actual_file_size)
            
            return response
        except Exception as e:
            logger.error(f"[device_firmware_download] Error opening file: {e}", exc_info=True)
            return JsonResponse({"error": _("Fehler beim Öffnen der Firmware-Datei")}, status=500)
        
    except Exception as e:
        logger.error(f"[device_firmware_download] Error: {str(e)}", exc_info=True)
        return JsonResponse({"error": _("Interner Serverfehler"), "details": str(e)}, status=500)


@csrf_exempt
def device_firmware_info(request: HttpRequest) -> JsonResponse:
    """
    Endpoint for devices to check if firmware update is available.
    
    GET /api/device/firmware/info?device_id=device_name&current_version=1.0.0
    """
    try:
        device_id = request.GET.get('device_id')
        current_version = request.GET.get('current_version', '')
        
        if not device_id:
            return JsonResponse({"error": _("device_id-Parameter ist erforderlich")}, status=400)
        
        # Validate API key (device-specific or global)
        is_valid, device, config = validate_device_api_key(request, device_id)
        if not is_valid:
            logger.warning(f"[device_firmware_info] Invalid API key for device {device_id}")
            return JsonResponse({"error": _("Ungültiger API-Key")}, status=403)
        
        # If device not found from API key, try to get it by name
        if not device:
            try:
                device = Device.objects.get(name=device_id)
            except Device.DoesNotExist:
                return JsonResponse({"error": _("Gerät nicht gefunden")}, status=404)
        
        # Get device configuration and assigned firmware
        try:
            config = device.configuration
            firmware = config.assigned_firmware
        except DeviceConfiguration.DoesNotExist:
            return JsonResponse({
                "success": True,
                "update_available": False,
                "message": _("Keine Firmware zugewiesen")
            })
        except AttributeError:
            return JsonResponse({
                "success": True,
                "update_available": False,
                "message": _("Keine Firmware zugewiesen")
            })
        
        if not firmware or not firmware.is_active:
            return JsonResponse({
                "success": True,
                "update_available": False,
                "message": _("Keine aktive Firmware zugewiesen")
            })
        
        # Check if update is needed
        update_available = firmware.version != current_version
        
        response_data = {
            "success": True,
            "update_available": update_available,
            "current_version": current_version,
            "available_version": firmware.version,
            "firmware_name": firmware.name,
            "file_size": firmware.file_size,
            "checksum_md5": firmware.checksum_md5,
            "download_url": f"/api/device/firmware/download?device_id={device_id}"
        }
        
        if update_available:
            response_data["message"] = _("Firmware-Update verfügbar")
        else:
            response_data["message"] = _("Gerät ist auf dem neuesten Stand")
        
        logger.info(f"[device_firmware_info] Device {device_id} checked firmware. Update available: {update_available}")
        
        return JsonResponse(response_data)
        
    except Exception as e:
        logger.error(f"[device_firmware_info] Error: {str(e)}", exc_info=True)
        return JsonResponse({"error": _("Interner Serverfehler"), "details": str(e)}, status=500)


@csrf_exempt
def device_heartbeat(request: HttpRequest) -> JsonResponse:
    """
    Endpoint for devices to send heartbeat signals.
    
    POST /api/device/heartbeat
    Expected JSON: {"device_id": "device_name"}
    """
    try:
        if request.method != 'POST':
            return JsonResponse({"error": _("Methode nicht erlaubt")}, status=405)
        
        data = json.loads(request.body) if request.body else {}
        device_id = data.get('device_id')
        
        if not device_id:
            return JsonResponse({"error": _("device_id ist erforderlich")}, status=400)
        
        # Validate API key (device-specific or global)
        is_valid, device, config = validate_device_api_key(request, device_id)
        if not is_valid:
            logger.warning(f"[device_heartbeat] Invalid API key for device {device_id}")
            return JsonResponse({"error": _("Ungültiger API-Key")}, status=403)
        
        # If device not found from API key, try to get it by name
        if not device:
            try:
                device = Device.objects.get(name=device_id)
            except Device.DoesNotExist:
                return JsonResponse({"error": _("Gerät nicht gefunden")}, status=404)
        
        # Update health status
        health, _ = DeviceHealth.objects.get_or_create(device=device)
        health.update_heartbeat()
        
        # Update device last_active
        device.last_active = timezone.now()
        device.save()
        
        # Create audit log entry
        DeviceAuditLog.objects.create(
            device=device,
            action='heartbeat_received',
            ip_address=get_client_ip(request)
        )
        
        logger.debug(f"[device_heartbeat] Device {device_id} sent heartbeat")
        
        return JsonResponse({
            "success": True,
            "message": "Heartbeat empfangen",
            "status": health.status,
            "last_heartbeat": health.last_heartbeat.isoformat() if health.last_heartbeat else None
        })
        
    except json.JSONDecodeError as e:
        logger.error(f"[device_heartbeat] JSON decode error: {str(e)}")
        return JsonResponse({"error": "Ungültiges JSON-Format"}, status=400)
    except Exception as e:
        logger.error(f"[device_heartbeat] Error: {str(e)}", exc_info=True)
        return JsonResponse({"error": "Interner Serverfehler", "details": str(e)}, status=500)


@csrf_exempt
def redeem_milestone_reward(request: HttpRequest) -> JsonResponse:
    """
    Redeem a milestone reward for a group.
    
    POST parameters:
    - achievement_id: ID of the GroupMilestoneAchievement to redeem
    - group_id: ID of the group (optional, for validation)
    
    Returns:
    - success: True if reward was redeemed, False if already redeemed
    - message: Status message
    """
    api_key_header = request.headers.get('X-Api-Key')
    is_valid, _device = validate_api_key(api_key_header)
    if not is_valid:
        return JsonResponse({"error": _("Ungültiger API-Schlüssel")}, status=403)
    
    if request.method != 'POST':
        return JsonResponse({"error": _("Nur POST-Requests erlaubt")}, status=405)
    
    try:
        data = json.loads(request.body)
        achievement_id = data.get('achievement_id')
        group_id = data.get('group_id')
        
        if not achievement_id:
            return JsonResponse({"error": _("achievement_id ist erforderlich")}, status=400)
        
        try:
            achievement = GroupMilestoneAchievement.objects.select_for_update().get(pk=achievement_id)
        except GroupMilestoneAchievement.DoesNotExist:
            return JsonResponse({"error": _("Meilenstein-Erreichung nicht gefunden")}, status=404)
        
        # Optional: Validate group_id matches
        if group_id:
            try:
                if achievement.group.id != int(group_id):
                    return JsonResponse({"error": _("Gruppe stimmt nicht überein")}, status=400)
            except (ValueError, TypeError):
                return JsonResponse({"error": _("Ungültige group_id")}, status=400)
        
        # Check if already redeemed
        if achievement.is_redeemed:
            return JsonResponse({
                "success": False,
                "message": _("Belohnung wurde bereits eingelöst"),
                "redeemed_at": achievement.redeemed_at.isoformat() if achievement.redeemed_at else None
            }, status=200)
        
        # Check if reward exists
        if not achievement.reward_text or achievement.reward_text.strip() == '':
            return JsonResponse({
                "success": False,
                "message": _("Keine Belohnung für diesen Meilenstein definiert")
            }, status=200)
        
        # Redeem the reward
        with transaction.atomic():
            achievement.is_redeemed = True
            achievement.redeemed_at = timezone.now()
            achievement.save()
        
        logger.info(f"[redeem_milestone_reward] Reward redeemed for achievement {achievement_id} (group: {achievement.group.name}, milestone: {achievement.milestone.name})")
        
        return JsonResponse({
            "success": True,
            "message": _("Belohnung erfolgreich eingelöst"),
            "reward_text": achievement.reward_text,
            "redeemed_at": achievement.redeemed_at.isoformat()
        })
        
    except json.JSONDecodeError:
        return JsonResponse({"error": _("Ungültiges JSON-Format")}, status=400)
    except Exception as e:
        logger.error(f"[redeem_milestone_reward] Error: {str(e)}", exc_info=True)
        return JsonResponse({"error": _("Interner Serverfehler"), "details": str(e)}, status=500)


@csrf_exempt
def get_group_rewards(request: HttpRequest) -> JsonResponse:
    """
    Get all milestone rewards (achievements) for a group.
    
    Query parameters:
    - group_id: ID of the group (required)
    - include_redeemed: Include already redeemed rewards (default: true)
    - track_id: Filter by track ID (optional)
    
    Returns:
    - rewards: List of milestone achievements with reward information
    """
    api_key_header = request.headers.get('X-Api-Key')
    is_valid, _device = validate_api_key(api_key_header)
    if not is_valid:
        return JsonResponse({"error": _("Ungültiger API-Schlüssel")}, status=403)
    
    group_id = request.GET.get('group_id', '').strip()
    if not group_id:
        return JsonResponse({"error": _("group_id ist erforderlich")}, status=400)
    
    try:
        group = Group.objects.get(pk=int(group_id), is_visible=True)
    except (ValueError, Group.DoesNotExist):
        return JsonResponse({"error": _("Gruppe nicht gefunden")}, status=404)
    
    include_redeemed = request.GET.get('include_redeemed', 'true').strip().lower() == 'true'
    track_id = request.GET.get('track_id', '').strip()
    
    # Get all milestone achievements for this group
    achievements_qs = GroupMilestoneAchievement.objects.filter(
        group=group
    ).select_related('milestone', 'track').order_by('-reached_at')
    
    # Filter by redeemed status
    if not include_redeemed:
        achievements_qs = achievements_qs.filter(is_redeemed=False)
    
    # Filter by track if specified
    if track_id:
        try:
            achievements_qs = achievements_qs.filter(track_id=int(track_id))
        except ValueError:
            return JsonResponse({"error": _("Ungültige track_id")}, status=400)
    
    rewards_data = []
    for achievement in achievements_qs:
        rewards_data.append({
            'achievement_id': achievement.id,
            'milestone_id': achievement.milestone.id,
            'milestone_name': achievement.milestone.name,
            'track_id': achievement.track.id,
            'track_name': achievement.track.name,
            'reached_at': achievement.reached_at.isoformat(),
            'reached_distance_km': float(achievement.reached_distance) if achievement.reached_distance else None,
            'reward_text': achievement.reward_text or '',
            'is_redeemed': achievement.is_redeemed,
            'redeemed_at': achievement.redeemed_at.isoformat() if achievement.redeemed_at else None,
        })
    
    return JsonResponse({
        'group_id': group.id,
        'group_name': group.name,
        'rewards': rewards_data,
        'total_count': len(rewards_data)
    })