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
from .helpers import (
    _get_latest_snapshot_date_for_groups,
    filter_cyclist_metrics_by_snapshot,
    get_cyclist_by_identifier,
    build_cyclist_velos_api_fields,
    build_group_velos_api_fields,
    get_cyclist_velos_total,
    get_cyclist_velos_daily,
    get_cyclist_velos_period,
    _calculate_group_velos_periods,
    _calculate_group_velos_from_metrics,
    get_cyclist_session_velos,
)
from api.services.velos_redemption import redeem_cyclist_by_identifier
from api.velos import track_reference_velos
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
from api.services.velos_earn import apply_velos_earn

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
    Check whether a group has reached new milestones based on Velos travel progress.

    Milestones are assigned to the leaf group with the highest Velos contribution.
    Geographic milestone positions remain km-based on the track.
    """
    from api.travel_velos import get_milestone_position_velos

    group.refresh_from_db()

    track = None
    status = None
    parent_travel_velos = 0
    leaf_group = None
    leaf_current_velos = 0
    new_milestones = Milestone.objects.none()

    try:
        status = group.travel_status
        track = status.track
        parent_travel_velos = int(status.current_travel_velos or 0)
    except GroupTravelStatus.DoesNotExist:
        if not group.is_leaf_group():
            logger.debug(
                "[check_milestone_victory] Group '%s' has no travel_status and is not a leaf group.",
                group.name,
            )
            return

        parent = group.parent
        if not parent:
            return

        try:
            parent_status = parent.travel_status
            track = parent_status.track
            parent_travel_velos = int(parent_status.current_travel_velos or 0)
        except GroupTravelStatus.DoesNotExist:
            return

        if parent_travel_velos <= 0:
            return

        new_milestones = Milestone.objects.filter(
            track=track,
            winner_group__isnull=True,
            position_velos__lte=parent_travel_velos,
        ).order_by('position_velos')

        if not new_milestones.exists():
            return

        leaf_group = group
        try:
            contribution = LeafGroupTravelContribution.objects.get(
                leaf_group=group,
                track=track,
            )
            leaf_current_velos = int(contribution.current_travel_velos or 0)
        except LeafGroupTravelContribution.DoesNotExist:
            leaf_current_velos = parent_travel_velos
    else:
        status.refresh_from_db()
        track = status.track
        parent_travel_velos = int(status.current_travel_velos or 0)

        if parent_travel_velos <= 0:
            return

        logger.debug(
            "[check_milestone_victory] Checking milestones for '%s' on '%s' at %s Velos",
            group.name, track.name, parent_travel_velos,
        )

        new_milestones = Milestone.objects.filter(
            track=track,
            winner_group__isnull=True,
            position_velos__lte=parent_travel_velos,
        ).order_by('position_velos')

        if not new_milestones.exists():
            return

        if group.is_leaf_group():
            parent = group.parent
            if not parent:
                return
            leaf_group = group
            try:
                contribution = LeafGroupTravelContribution.objects.get(
                    leaf_group=group,
                    track=track,
                )
                leaf_current_velos = int(contribution.current_travel_velos or 0)
            except LeafGroupTravelContribution.DoesNotExist:
                try:
                    parent_status = parent.travel_status
                    leaf_current_velos = int(parent_status.current_travel_velos or 0)
                except GroupTravelStatus.DoesNotExist:
                    leaf_current_velos = parent_travel_velos
        else:
            leaf_groups = group.get_leaf_groups()
            if not leaf_groups.exists():
                return

            leaf_contributions = LeafGroupTravelContribution.objects.filter(
                leaf_group__in=leaf_groups,
                track=track,
            ).select_related('leaf_group').order_by('-current_travel_velos')

            if not leaf_contributions.exists():
                return

            contribution_map = {
                contrib.leaf_group_id: int(contrib.current_travel_velos or 0)
                for contrib in leaf_contributions
            }

            best_leaf_group = None
            best_velos = 0
            for leaf in leaf_groups:
                leaf_travel_velos = contribution_map.get(leaf.id, 0)
                for ms in new_milestones:
                    if parent_travel_velos >= get_milestone_position_velos(ms):
                        if leaf_travel_velos > best_velos:
                            best_leaf_group = leaf
                            best_velos = leaf_travel_velos

            if not best_leaf_group and active_leaf_group and active_leaf_group in leaf_groups:
                best_leaf_group = active_leaf_group
                best_velos = contribution_map.get(active_leaf_group.id, 0)

            if not best_leaf_group:
                return

            leaf_group = best_leaf_group
            leaf_current_velos = best_velos

    if leaf_group is None or not leaf_group.is_visible:
        if leaf_group:
            logger.warning(
                "[check_milestone_victory] Leaf group '%s' is not visible.",
                leaf_group.name,
            )
        return

    for ms in new_milestones:
        ms_position_velos = get_milestone_position_velos(ms)
        with transaction.atomic():
            ms_locked = Milestone.objects.select_for_update().get(pk=ms.pk)
            if ms_locked.winner_group:
                continue

            if parent_travel_velos < ms_position_velos:
                continue

            reached_time = timezone.now()
            ms_locked.winner_group = leaf_group
            ms_locked.reached_at = reached_time
            ms_locked.save()

            leaf_contribution_distance = Decimal(str(
                LeafGroupTravelContribution.objects.filter(
                    leaf_group=leaf_group,
                    track=track,
                ).values_list('current_travel_distance', flat=True).first() or 0,
            ))
            if leaf_contribution_distance <= 0 and track:
                from api.travel_velos import sync_travel_distance_km_from_velos
                leaf_contribution_distance = sync_travel_distance_km_from_velos(
                    leaf_current_velos, track,
                )

            achievement, created = GroupMilestoneAchievement.objects.get_or_create(
                group=leaf_group,
                milestone=ms_locked,
                defaults={
                    'track': track,
                    'reached_at': reached_time,
                    'reached_distance': leaf_contribution_distance,
                    'reward_text': ms_locked.reward_text or '',
                    'is_redeemed': False,
                },
            )
            if created:
                logger.info(
                    "[check_milestone_victory] Milestone '%s' reached by '%s' at %s Velos",
                    ms_locked.name, leaf_group.name, ms_position_velos,
                )

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
        from api.services.device_display import (
            build_device_display_api_payload,
            get_active_session_for_device,
            handle_boot_reason,
        )
        handle_boot_reason(device_obj, data.get('boot_reason'))
        payload = {
            "success": False,
            "message": _("Kilometer-Erfassung für diesen Radler ist deaktiviert"),
            "skipped": True,
        }
        payload.update(
            build_device_display_api_payload(
                device_obj,
                get_active_session_for_device(device_obj),
            )
        )
        return JsonResponse(payload, status=200)
    
    if not device_obj.is_km_collection_enabled:
        logger.info(f"[update_data] Kilometer collection disabled for device: {device_obj.name} (ID: {device_obj.pk})")
        from api.services.device_display import (
            build_device_display_api_payload,
            get_active_session_for_device,
            handle_boot_reason,
        )
        handle_boot_reason(device_obj, data.get('boot_reason'))
        payload = {
            "success": False,
            "message": _("Kilometer-Erfassung für dieses Gerät ist deaktiviert"),
            "skipped": True,
        }
        payload.update(
            build_device_display_api_payload(
                device_obj,
                get_active_session_for_device(device_obj),
            )
        )
        return JsonResponse(payload, status=200)

    from api.services.device_display import handle_boot_reason
    handle_boot_reason(device_obj, data.get('boot_reason'))

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
                            # group_at_time is write-once (set at creation only)
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

        velos_added = 0
        if distance_delta > 0:
            velos_added = apply_velos_earn(cyclist_obj, device_obj, distance_delta)
            if velos_added > 0:
                logger.info(
                    "[update_data] Velos added for %s: +%s",
                    cyclist_obj.id_tag,
                    velos_added,
                )

        # --- ACTIVATE HIERARCHY LOGIC ---
        if distance_delta > 0:
            logger.debug(f"[update_data] Propagating {distance_delta} km to {cyclist_obj.groups.count()} group(s)")

            active_leaf_group = None
            for group in cyclist_obj.groups.all():
                if group.is_leaf_group():
                    active_leaf_group = group
                    break

            for group in cyclist_obj.groups.all():
                old_group_distance = group.distance_total
                update_group_hierarchy_progress(group, distance_delta, velos_added)
                group.refresh_from_db()
                logger.debug(f"[update_data] Group '{group.name}' - old_distance: {old_group_distance}, new_distance: {group.distance_total}")
                check_milestone_victory(group, active_leaf_group=active_leaf_group)

        # Cyclist & Device total KM
        old_cyclist_distance = cyclist_obj.distance_total
        cyclist_obj.distance_total = cyclist_obj.distance_total + distance_delta
        cyclist_obj.last_active = now
        cyclist_obj.save()
        logger.debug(f"[update_data] Cyclist '{cyclist_obj.id_tag}' - old_distance: {old_cyclist_distance}, new_distance: {cyclist_obj.distance_total}")
        
        old_device_distance = device_obj.distance_total
        device_obj.distance_total = device_obj.distance_total + distance_delta
        device_obj.last_active = now
        device_obj.save()
        logger.debug(f"[update_data] Device '{device_obj.name}' - old_distance: {old_device_distance}, new_distance: {device_obj.distance_total}")

    logger.info(f"[update_data] Successfully processed update - id_tag: {id_tag}, device_id: {device_id}, distance: {distance_delta}")
    from api.services.device_display import build_device_display_api_payload

    response_payload = {"success": True}
    if velos_added:
        response_payload["velos_added"] = velos_added
    try:
        active_session = CyclistDeviceCurrentMileage.objects.select_related('device').get(
            cyclist=cyclist_obj
        )
        response_payload.update(
            build_device_display_api_payload(active_session.device, active_session)
        )
    except CyclistDeviceCurrentMileage.DoesNotExist:
        response_payload.update(build_device_display_api_payload(device_obj))
    return JsonResponse(response_payload)

def get_mapped_minecraft_players(request):
    """Returns the complete player mapping structure."""
    api_key_header = request.headers.get('X-Api-Key')
    is_valid, _device = validate_api_key(api_key_header)
    if not is_valid:
        return JsonResponse({"error": _("Ungültiger API-Schlüssel")}, status=403)

    filtered_cyclists = Cyclist.objects.filter(mc_username__isnull=False).values(
        'id_tag', 'user_id', 'mc_username', 'velos_balance', 'distance_total', 'last_active'
    )
    
    response_data = {
        c['id_tag']: {
            'user_id': c['user_id'], 'mc_username': c['mc_username'],
            'velos_balance': c['velos_balance'],
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
    """Returns the user_id based on the id_tag. Operator tags reset counter to default cyclist."""
    api_key_header = request.headers.get('X-Api-Key')
    is_valid, api_device = validate_api_key(api_key_header)
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

    device_id = (data.get('device_id') or data.get('device_name') or '').strip()
    current_id_tag = (data.get('current_id_tag') or '').strip()

    try:
        cyclist_obj = Cyclist.objects.get(id_tag__iexact=id_tag)
    except Cyclist.DoesNotExist:
        logger.info(f"[get_user_id] ID tag '{id_tag}' not found in database")
        return JsonResponse({"user_id": "NULL"})

    if cyclist_obj.is_operator_tag:
        device_obj = api_device
        if device_id and device_obj is None:
            try:
                device_obj = Device.objects.get(name=device_id)
            except Device.DoesNotExist:
                device_obj = None
        if device_obj is None:
            return JsonResponse(
                {"error": _("device_id erforderlich für Operator-Reset.")},
                status=400,
            )

        default_tag = ''
        try:
            default_tag = (device_obj.configuration.default_id_tag or '').strip()
        except DeviceConfiguration.DoesNotExist:
            default_tag = ''

        default_user_id = 'NULL'
        if default_tag:
            try:
                default_cyclist = Cyclist.objects.get(id_tag__iexact=default_tag)
                if default_cyclist.user_id:
                    default_user_id = default_cyclist.user_id
            except Cyclist.DoesNotExist:
                pass

        from api.services.device_session import end_device_session_for_device

        active = (
            CyclistDeviceCurrentMileage.objects.filter(device=device_obj)
            .select_related('cyclist')
            .first()
        )
        needs_reset = False
        if active and not active.cyclist.is_operator_tag:
            if default_tag and active.cyclist.id_tag.lower() != default_tag.lower():
                needs_reset = True
            elif not default_tag:
                needs_reset = True
        if (
            current_id_tag
            and default_tag
            and current_id_tag.lower() != default_tag.lower()
        ):
            needs_reset = True

        action = 'reset_to_default' if needs_reset else 'noop'
        if needs_reset:
            end_device_session_for_device(device_obj, reason='operator_reset')
            from api.services.device_display import unlock_device_display
            unlock_device_display(device_obj, reason='operator_reset')
            logger.info(
                "[get_user_id] Operator reset on device %s (default_tag=%s)",
                device_obj.name,
                default_tag,
            )

        return JsonResponse({
            'user_id': 'OPERATOR',
            'is_operator_tag': True,
            'action': action,
            'default_id_tag': default_tag,
            'default_user_id': default_user_id,
        })

    return_user_id = "NULL"
    if cyclist_obj.user_id:
        return_user_id = cyclist_obj.user_id
        logger.info(f"[get_user_id] ID tag '{id_tag}' found, assigned to user_id: '{return_user_id}'")
    else:
        logger.info(f"[get_user_id] ID tag '{id_tag}' found but has no user_id assigned")

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
def get_cyclist_velos(request, identifier):
    """
    Get cyclist Velos data (balance, totals, session, optional period).

    Query parameters:
    - start_date / end_date (optional, YYYY-MM-DD): velos_period for the range
    """
    api_key_header = request.headers.get('X-Api-Key')
    is_valid, _device = validate_api_key(api_key_header)
    if not is_valid:
        return JsonResponse({"error": _("Ungültiger API-Schlüssel")}, status=403)

    cyclist_obj = get_cyclist_by_identifier(identifier)
    if not cyclist_obj:
        return JsonResponse({
            "error": _("Radler nicht gefunden"),
            "identifier": identifier,
        }, status=404)

    response_data = {
        "cyclist_id": cyclist_obj.id,
        "user_id": cyclist_obj.user_id,
        "id_tag": cyclist_obj.id_tag,
        "mc_username": cyclist_obj.mc_username,
        "distance_total": float(cyclist_obj.distance_total or 0),
        **build_cyclist_velos_api_fields(
            cyclist_obj,
            include_session=True,
            include_daily=True,
        ),
    }

    start_date = request.GET.get('start_date', '').strip()
    end_date = request.GET.get('end_date', '').strip()

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
            response_data.update(build_cyclist_velos_api_fields(
                cyclist_obj,
                period_start=start_dt,
                period_end=end_dt,
            ))
            response_data.update({
                "period_start": start_date,
                "period_end": end_date,
            })
        except ValueError as e:
            return JsonResponse({
                "error": _("Ungültiges Datumsformat. Verwenden Sie YYYY-MM-DD"),
                "details": str(e),
            }, status=400)
    elif start_date or end_date:
        return JsonResponse({
            "error": _("start_date und end_date müssen beide angegeben werden")
        }, status=400)

    return JsonResponse(response_data)


@csrf_exempt
def redeem_cyclist_velos_api(request):
    """
    Redeem 100% of a cyclist's velos_balance (FEZitty / Wuhlis workflow).

    POST JSON: identifier (user_id or id_tag), optional note, external_currency
    """
    api_key_header = request.headers.get('X-Api-Key')
    is_valid, _device = validate_api_key(api_key_header)
    if not is_valid:
        return JsonResponse({"error": _("Ungültiger API-Schlüssel")}, status=403)

    if request.method != 'POST':
        return JsonResponse({"error": _("Methode nicht erlaubt.")}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": _("Ungültiges JSON-Format")}, status=400)

    identifier = (data.get('identifier') or data.get('user_id') or data.get('id_tag') or '').strip()
    if not identifier:
        return JsonResponse({"error": _("identifier ist erforderlich")}, status=400)

    result = redeem_cyclist_by_identifier(
        identifier,
        note=data.get('note', '') or '',
        external_currency=data.get('external_currency', '') or '',
    )

    if not result.success:
        return JsonResponse({"success": False, "error": result.message}, status=400)

    cyclist = result.redemption.cyclist if result.redemption else None
    payload = {
        "success": True,
        "message": result.message,
        "velos_redeemed": result.velos_redeemed,
    }
    if cyclist:
        payload.update({
            "cyclist_id": cyclist.id,
            "user_id": cyclist.user_id,
            "velos_balance": cyclist.velos_balance,
        })
    return JsonResponse(payload)


@csrf_exempt
def get_group_velos(request, identifier):
    """
    Get group Velos ledger data (total and spendable).

    Query parameters:
    - include_cyclists: Include member cyclists with velos_total (default: false)
    """
    api_key_header = request.headers.get('X-Api-Key')
    is_valid, _device = validate_api_key(api_key_header)
    if not is_valid:
        return JsonResponse({"error": _("Ungültiger API-Schlüssel")}, status=403)

    try:
        if identifier.isdigit():
            group_obj = Group.objects.get(id=int(identifier), is_visible=True)
        else:
            group_obj = Group.objects.get(name__iexact=identifier, is_visible=True)
    except Group.DoesNotExist:
        return JsonResponse({
            "error": _("Gruppe nicht gefunden"),
            "identifier": identifier,
        }, status=404)

    include_cyclists = request.GET.get('include_cyclists', 'false').strip().lower() == 'true'

    response_data = {
        "group_id": group_obj.id,
        "name": group_obj.name,
        "short_name": group_obj.short_name,
        "mc_username": group_obj.mc_username,
        **build_group_velos_api_fields(group_obj),
    }

    if include_cyclists:
        members = []
        for cyclist in group_obj.members.filter(is_visible=True).order_by('user_id'):
            members.append({
                "cyclist_id": cyclist.id,
                "user_id": cyclist.user_id,
                "velos_balance": int(cyclist.velos_balance or 0),
                "velos_total": get_cyclist_velos_total(cyclist),
            })
        response_data["cyclists"] = members
        response_data["sum_cyclist_velos_total"] = sum(m["velos_total"] for m in members)

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
    
    # Find cyclist by user_id or id_tag
    cyclist_obj = get_cyclist_by_identifier(identifier)
    if not cyclist_obj:
        return JsonResponse({
            "error": _("Radler nicht gefunden"),
            "identifier": identifier
        }, status=404)
    
    # Build response with total distance and Velos (km fields kept for transition)
    response_data = {
        "cyclist_id": cyclist_obj.id,
        "user_id": cyclist_obj.user_id,
        "id_tag": cyclist_obj.id_tag,
        "mc_username": cyclist_obj.mc_username,
        "distance_total": float(cyclist_obj.distance_total or 0),
        **build_cyclist_velos_api_fields(cyclist_obj, include_session=True),
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
            
            response_data.update(build_cyclist_velos_api_fields(
                cyclist_obj,
                period_start=start_dt,
                period_end=end_dt,
            ))
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
    
    # Build response with total distance and Velos ledger
    response_data = {
        "group_id": group_obj.id,
        "name": group_obj.name,
        "short_name": group_obj.short_name,
        "group_type": group_obj.group_type.name if group_obj.group_type else None,
        "distance_total": float(group_obj.distance_total or 0),
        **build_group_velos_api_fields(group_obj),
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
                from mgmt.analytics import _get_descendant_group_ids
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
            
            period_velos = HourlyMetric.objects.filter(
                group_at_time_id__in=group_ids,
                timestamp__gte=start_dt,
                timestamp__lte=end_dt,
            ).aggregate(
                total=Sum('velos')
            )['total'] or 0
            
            # Add active sessions that fall within the period
            active_sessions = CyclistDeviceCurrentMileage.objects.filter(
                cyclist__groups__id__in=group_ids,
                last_activity__gte=start_dt,
                last_activity__lte=end_dt,
                cumulative_mileage__gt=0
            ).select_related('cyclist', 'device__configuration').distinct()
            
            for session in active_sessions:
                # Only count session distance if it overlaps with the period
                if session.start_time and session.start_time <= end_dt:
                    period_distance += session.cumulative_mileage or Decimal('0')
                    period_velos += get_cyclist_session_velos(session.cyclist)
            
            response_data.update({
                "distance_period": float(period_distance),
                "velos_period": int(period_velos),
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
                **build_group_velos_api_fields(child),
            })
        response_data["children"] = children

    include_cyclists = request.GET.get('include_cyclists', 'false').strip().lower() == 'true'
    if include_cyclists:
        cyclists_payload = []
        for cyclist in group_obj.members.filter(is_visible=True).order_by('user_id'):
            cyclists_payload.append({
                "cyclist_id": cyclist.id,
                "user_id": cyclist.user_id,
                "velos_balance": int(cyclist.velos_balance or 0),
                "velos_total": get_cyclist_velos_total(cyclist),
            })
        response_data["cyclists"] = cyclists_payload
    
    return JsonResponse(response_data)


@csrf_exempt
def get_leaderboard_cyclists(request):
    """
    Get leaderboard of top cyclists by Velos (distance fields kept for transition).
    
    Query parameters:
    - sort: 'daily' or 'total' (default: 'total') — sorts by velos_daily / velos_total
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
            from mgmt.analytics import _get_descendant_group_ids
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
        daily_velos_by_cyclist: Dict[int, int] = {}
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
            cyclist_obj = cyclists_qs.filter(id=cyclist_id).first()
            if cyclist_obj:
                daily_velos_by_cyclist[cyclist_id] = get_cyclist_velos_daily(cyclist_obj, now)
            else:
                daily_velos_by_cyclist[cyclist_id] = 0
        
        # Add active sessions
        active_sessions = CyclistDeviceCurrentMileage.objects.filter(
            cyclist__in=cyclists_qs,
            last_activity__gte=today_start,
            cumulative_mileage__gt=0
        ).select_related('cyclist', 'device__configuration')
        
        for session in active_sessions:
            cyclist_id = session.cyclist.id
            if cyclist_id not in daily_by_cyclist:
                daily_by_cyclist[cyclist_id] = 0.0
            if cyclist_id not in daily_velos_by_cyclist:
                daily_velos_by_cyclist[cyclist_id] = 0
            daily_by_cyclist[cyclist_id] += float(session.cumulative_mileage or 0)
            daily_velos_by_cyclist[cyclist_id] += get_cyclist_session_velos(session.cyclist)
        
        # Get cyclists with their daily totals
        cyclists_list = []
        for cyclist in cyclists_qs.select_related().prefetch_related('groups'):
            daily_km = daily_by_cyclist.get(cyclist.id, 0.0)
            daily_velos = daily_velos_by_cyclist.get(cyclist.id, 0)
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
                'velos_total': get_cyclist_velos_total(cyclist),
                'velos_daily': daily_velos,
                'velos_balance': int(cyclist.velos_balance or 0),
                'group_name': primary_group.name if primary_group else None,
                'group_short_name': primary_group.short_name if primary_group else None,
            })
        
        # Sort by daily Velos (distance_daily kept for reference)
        cyclists_list.sort(key=lambda x: (x['velos_daily'], x['velos_total']), reverse=True)
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
                'velos_total': get_cyclist_velos_total(cyclist),
                'velos_balance': int(cyclist.velos_balance or 0),
                'group_name': primary_group.name if primary_group else None,
                'group_short_name': primary_group.short_name if primary_group else None,
            })
        
        cyclists_list.sort(key=lambda x: (x['velos_total'], x['distance_total']), reverse=True)
    
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
    Get leaderboard of top groups by Velos from HourlyMetric.

    velos_total reflects metric totals (period-aware via snapshots).
    velos_spendable remains the group ledger field (Minecraft).
    
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
            from mgmt.analytics import _get_descendant_group_ids
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
    velos_period_by_group: Dict[int, int] = {}
    
    groups_for_velos = list(groups_qs)
    velos_periods = _calculate_group_velos_periods(groups_for_velos, now=now, use_cache=False)
    
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
            velos_period_by_group[group_id] = velos_periods.get(group_id, {}).get('daily', 0)
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
            velos_period_by_group[group_id] = velos_periods.get(group_id, {}).get('weekly', 0)
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
            velos_period_by_group[group_id] = velos_periods.get(group_id, {}).get('monthly', 0)
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
    
    # Build groups list (velos_total = HourlyMetric period total; velos_spendable = ledger)
    groups_list = []
    for group in groups_qs.select_related('parent'):
        period_km = period_by_group.get(group.id, 0.0) if sort != 'total' else None
        period_velos = velos_period_by_group.get(group.id, 0) if sort != 'total' else None
        metric_velos_total = int(velos_periods.get(group.id, {}).get('total', 0))

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
            'velos_total': metric_velos_total,
            'velos_spendable': int(group.velos_spendable or 0),
            'velos_period': period_velos,
            'parent_group_name': parent_group_name,
        })
    
    # Sort by Velos (distance fields kept for reference)
    if sort == 'total':
        groups_list.sort(key=lambda x: (x['velos_total'], x['distance_total']), reverse=True)
    else:
        groups_list.sort(key=lambda x: (x['velos_period'] or 0, x['velos_total']), reverse=True)
    
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
    ).select_related(
        'cyclistdevicecurrentmileage__device__configuration'
    ).prefetch_related('groups')
    
    # Filter by group if specified
    if group_id:
        try:
            group = Group.objects.get(pk=int(group_id))
            from mgmt.analytics import _get_descendant_group_ids
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
        session_velos = 0
        device_name = "Unbekannt"
        
        try:
            mileage_obj = cyclist.cyclistdevicecurrentmileage
            if mileage_obj and mileage_obj.cumulative_mileage is not None:
                session_km = float(mileage_obj.cumulative_mileage)
            if mileage_obj and mileage_obj.device:
                device_name = mileage_obj.device.display_name or mileage_obj.device.name
            session_velos = get_cyclist_session_velos(cyclist)
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
            'session_velos': session_velos,
            'velos_total': get_cyclist_velos_total(cyclist),
            'velos_balance': int(cyclist.velos_balance or 0),
            'distance_total': float(cyclist.distance_total or 0),
            'device_name': device_name,
            'last_active': cyclist.last_active.isoformat() if cyclist.last_active else None,
            'group_name': primary_group.name if primary_group else None,
            'group_short_name': primary_group.short_name if primary_group else None,
        })
    
    # Sort by session Velos
    active_cyclists.sort(key=lambda x: x['session_velos'], reverse=True)
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
            from mgmt.analytics import _get_descendant_group_ids
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
            'velos_balance': cyclist.velos_balance,
            'velos_total': get_cyclist_velos_total(cyclist),
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

    velos_total is summed from HourlyMetric; velos_spendable is the ledger field.
    
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
    page_groups = list(groups_qs.order_by('name')[offset:offset + page_size])
    velos_by_group = _calculate_group_velos_from_metrics(page_groups, use_cache=False)

    groups_list = []
    for group in page_groups:
        groups_list.append({
            'group_id': group.id,
            'name': group.name,
            'short_name': group.short_name,
            'group_type': group.group_type.name if group.group_type else None,
            'distance_total': float(group.distance_total or 0),
            'velos_total': velos_by_group.get(group.id, 0),
            'velos_spendable': int(group.velos_spendable or 0),
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

    top_groups[].velos_total is the Velos sum from HourlyMetric within the period.
    
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
            from mgmt.analytics import _get_descendant_group_ids
            group_ids = _get_descendant_group_ids(group)
            group_ids.append(group.id)
            metrics_qs = metrics_qs.filter(group_at_time_id__in=group_ids)
        except (ValueError, Group.DoesNotExist):
            return JsonResponse({
                "error": _("Gruppe nicht gefunden"),
                "group_id": group_id
            }, status=404)
    
    # Calculate total distance and Velos
    total_distance = metrics_qs.aggregate(
        total=Sum('distance_km')
    )['total'] or Decimal('0.00000')
    total_velos = int(metrics_qs.aggregate(total=Sum('velos'))['total'] or 0)
    
    # Add active sessions
    if group_id:
        try:
            group = Group.objects.get(pk=int(group_id))
            from mgmt.analytics import _get_descendant_group_ids
            group_ids = _get_descendant_group_ids(group)
            group_ids.append(group.id)
            active_sessions = CyclistDeviceCurrentMileage.objects.filter(
                cyclist__groups__id__in=group_ids,
                last_activity__gte=start_dt,
                last_activity__lte=end_dt,
                cumulative_mileage__gt=0
            ).select_related('cyclist', 'device__configuration').distinct()
        except (ValueError, Group.DoesNotExist):
            active_sessions = CyclistDeviceCurrentMileage.objects.none()
    else:
        active_sessions = CyclistDeviceCurrentMileage.objects.filter(
            last_activity__gte=start_dt,
            last_activity__lte=end_dt,
            cumulative_mileage__gt=0
        ).select_related('cyclist', 'device__configuration')
    
    for session in active_sessions:
        total_distance += session.cumulative_mileage or Decimal('0')
        total_velos += get_cyclist_session_velos(session.cyclist)
    
    # Top groups by Velos in the requested period (HourlyMetric)
    top_groups_agg = list(
        metrics_qs.values('group_at_time_id')
        .annotate(period_velos=Sum('velos'))
        .filter(period_velos__gt=0)
        .order_by('-period_velos')[:10]
    )
    top_group_ids = [row['group_at_time_id'] for row in top_groups_agg]
    period_velos_by_group = {
        row['group_at_time_id']: int(row['period_velos'] or 0)
        for row in top_groups_agg
    }
    groups_by_id = {
        g.id: g
        for g in Group.objects.filter(id__in=top_group_ids, is_visible=True).select_related('group_type')
    }

    top_groups_list = []
    for group_id in top_group_ids:
        group = groups_by_id.get(group_id)
        if group is None:
            continue
        top_groups_list.append({
            'group_id': group.id,
            'name': group.name,
            'short_name': group.short_name,
            'group_type': group.group_type.name if group.group_type else None,
            'distance_total': float(group.distance_total or 0),
            'velos_total': period_velos_by_group[group_id],
        })
    
    # Get top cyclists by Velos in period
    top_cyclists_metrics = metrics_qs.filter(cyclist__isnull=False).values(
        'cyclist_id', 'cyclist__user_id', 'cyclist__id_tag'
    ).annotate(
        total_distance=Sum('distance_km'),
        total_velos=Sum('velos'),
    ).order_by('-total_velos')[:10]
    
    top_cyclists_list = []
    for item in top_cyclists_metrics:
        top_cyclists_list.append({
            'cyclist_id': item.get('cyclist_id'),
            'user_id': item.get('cyclist__user_id'),
            'id_tag': item.get('cyclist__id_tag'),
            'distance_period': float(item.get('total_distance') or 0),
            'velos_period': int(item.get('total_velos') or 0),
        })
    
    return JsonResponse({
        'period_start': start_dt.strftime('%Y-%m-%d'),
        'period_end': end_dt.strftime('%Y-%m-%d'),
        'total_distance': float(total_distance),
        'total_velos': total_velos,
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
        boot_reason = data.get('boot_reason')
        
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

        from api.services.device_display import (
            build_device_display_api_payload,
            get_active_session_for_device,
            handle_boot_reason,
        )
        handle_boot_reason(device, boot_reason)
        
        # Create audit log entry
        DeviceAuditLog.objects.create(
            device=device,
            action='heartbeat_received',
            ip_address=get_client_ip(request)
        )
        
        logger.debug(f"[device_heartbeat] Device {device_id} sent heartbeat")
        
        response_data = {
            "success": True,
            "message": "Heartbeat empfangen",
            "status": health.status,
            "last_heartbeat": health.last_heartbeat.isoformat() if health.last_heartbeat else None,
        }
        response_data.update(
            build_device_display_api_payload(
                device,
                get_active_session_for_device(device),
            )
        )
        return JsonResponse(response_data)
        
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
            'reached_velos': track_reference_velos(achievement.reached_distance)
            if achievement.reached_distance else None,
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