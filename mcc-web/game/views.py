# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    views.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
import json
import logging
import os
import io
try:
    import qrcode
    # Test if PIL/Pillow is available (required for image generation)
    try:
        from PIL import Image
        QRCODE_AVAILABLE = True
    except ImportError:
        QRCODE_AVAILABLE = False
        logging.getLogger(__name__).warning("qrcode installed but PIL/Pillow not available")
except ImportError as e:
    QRCODE_AVAILABLE = False
    logging.getLogger(__name__).warning(f"qrcode package not available: {e}")
from django.http import JsonResponse, FileResponse, Http404, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.urls import reverse
from api.models import Cyclist, Group
from iot.models import Device
from django.db.models import Q
from django.db.models.functions import Coalesce


def format_css_number(value, decimals=1):
    """
    Format a number for use in CSS values, always using dot as decimal separator.
    
    This utility function ensures that numeric values used in CSS (like width, height, etc.)
    are always formatted with a dot (.) as decimal separator, regardless of the current
    locale setting. This prevents issues where German locale would use commas (,) which
    CSS doesn't accept.
    
    Args:
        value: Numeric value to format
        decimals: Number of decimal places (default: 1)
    
    Returns:
        String representation of the number with dot as decimal separator
    
    Example:
        format_css_number(90.5, 1)  # Returns "90.5" (never "90,5")
        format_css_number(90.5, 2)  # Returns "90.50" (never "90,50")
    """
    if value is None:
        return "0"
    
    try:
        num = float(value)
        # Format with specified decimals, always using dot
        formatted = f"{num:.{decimals}f}"
        # Ensure dot is used (replace comma if locale added one)
        return formatted.replace(',', '.')
    except (ValueError, TypeError):
        return "0" 
from django.utils.translation import gettext_lazy as _
from .models import GameRoom

logger = logging.getLogger(__name__)


# --- Helper Functions for GameRoom ---

# --- Helper Functions for Master System ---

def is_master(request, room):
    """Checks if the current session is the master of the room."""
    if not room or not room.master_session_key:
        return False
    return request.session.session_key == room.master_session_key

def can_delete_assignment(request, room, cyclist_user_id):
    """Checks if an assignment can be deleted by the current user."""
    if not room:
        return True  # No room = normal mode, allow deletion
    if is_master(request, room):
        return True  # Master can delete all
    # Normal participants can only delete their own assignments
    device_assignments = request.session.get('device_assignments', {})
    return cyclist_user_id in device_assignments.values()

def can_modify_target_km(request, room):
    """Checks if target kilometers can be modified by the current user."""
    if not room:
        return True  # No room = normal mode, allow modification
    return is_master(request, room)


def sync_session_from_room(request):
    """Loads game state from GameRoom into session if room_code exists."""
    room_code = request.session.get('room_code')
    if room_code:
        try:
            # Try to get room (both active and inactive)
            room = GameRoom.objects.get(room_code=room_code)
            
            # Check if room is inactive (ended)
            if not room.is_active:
                # Room has been ended - clear session and return None
                logger.info(f"🏁 Raum {room_code} wurde beendet, bereinige Session")
                if 'room_code' in request.session:
                    del request.session['room_code']
                if 'is_master' in request.session:
                    del request.session['is_master']
                if 'device_assignments' in request.session:
                    del request.session['device_assignments']
                if 'assignment_owners' in request.session:
                    del request.session['assignment_owners']
                if 'start_distances' in request.session:
                    del request.session['start_distances']
                if 'stop_distances' in request.session:
                    del request.session['stop_distances']
                if 'announced_winners' in request.session:
                    del request.session['announced_winners']
                if 'current_target_km' in request.session:
                    del request.session['current_target_km']
                request.session.modified = True
                return None
            
            # Room is active - sync data from room to session
            request.session['device_assignments'] = room.device_assignments or {}
            request.session['start_distances'] = room.start_distances or {}
            request.session['stop_distances'] = room.stop_distances or {}
            request.session['is_game_stopped'] = room.is_game_stopped
            request.session['announced_winners'] = room.announced_winners or []
            request.session['current_target_km'] = room.current_target_km
            # Update master flag - CRITICAL: This must be updated every time we sync
            is_master_flag = is_master(request, room)
            request.session['is_master'] = is_master_flag
            logger.info(f"🔄 sync_session_from_room: room_code={room_code}, session_key={request.session.session_key}, is_master={is_master_flag}, master_session_key={room.master_session_key}")
            
            # Update active sessions list
            if request.session.session_key:
                active_sessions = room.active_sessions or []
                if request.session.session_key not in active_sessions:
                    active_sessions.append(request.session.session_key)
                    room.active_sessions = active_sessions
                    room.save()
            
            request.session.modified = True
            return room
        except GameRoom.DoesNotExist:
            # Room doesn't exist, clear room_code from session
            logger.info(f"🏁 Raum {room_code} existiert nicht mehr, bereinige Session")
            if 'room_code' in request.session:
                del request.session['room_code']
            if 'is_master' in request.session:
                del request.session['is_master']
            if 'device_assignments' in request.session:
                del request.session['device_assignments']
            if 'assignment_owners' in request.session:
                del request.session['assignment_owners']
            request.session.modified = True
    return None


def sync_room_from_session(request):
    """Saves current session state to GameRoom if room_code exists."""
    room_code = request.session.get('room_code')
    if room_code:
        try:
            room = GameRoom.objects.get(room_code=room_code)
            # Don't sync to inactive rooms
            if not room.is_active:
                logger.warning(f"⚠️ Versuch, zu beendetem Raum zu syncen: {room_code}")
                return None
            # Sync data from session to room
            room.device_assignments = request.session.get('device_assignments', {})
            room.start_distances = request.session.get('start_distances', {})
            room.stop_distances = request.session.get('stop_distances', {})
            room.is_game_stopped = request.session.get('is_game_stopped', False)
            room.announced_winners = request.session.get('announced_winners', [])
            room.current_target_km = request.session.get('current_target_km', 0.0)
            
            # Update active sessions list
            if request.session.session_key:
                active_sessions = room.active_sessions or []
                if request.session.session_key not in active_sessions:
                    active_sessions.append(request.session.session_key)
                room.active_sessions = active_sessions
            
            room.save()  # This also updates last_activity
            return room
        except GameRoom.DoesNotExist:
            # Room doesn't exist, clear room_code from session
            if 'room_code' in request.session:
                del request.session['room_code']
                request.session.modified = True
    return None


# --- HTML View ---
def game_page(request):
    """Serves the main page of the kilometer challenge (replaces mcc_game.py:/)."""
    # Sync from room if in a shared room
    sync_session_from_room(request)
    
    room_code = request.session.get('room_code')
    room_url = None
    if room_code:
        base_url = request.build_absolute_uri('/')[:-1]
        room_url = f"{base_url}{reverse('game:room_page', args=[room_code])}"
    
    # Get current target_km from session (synced from room if in a room)
    current_target_km = request.session.get('current_target_km', 0.0)
    if current_target_km is None:
        current_target_km = 0.0
    else:
        current_target_km = float(current_target_km)
    
    # Get master flag (only relevant if in a room, otherwise False)
    # CRITICAL: If in a room, sync first to ensure is_master is up-to-date
    if room_code:
        # sync_session_from_room was already called above, so is_master should be current
        is_master_flag = request.session.get('is_master', False)
        logger.info(f"🔍 game_page: room_code={room_code}, session_key={request.session.session_key}, is_master={is_master_flag}")
    else:
        is_master_flag = False
    
    # Get all top-level parent groups (schools) for filtering
    top_groups = Group.objects.filter(
        parent__isnull=True,
        is_visible=True
    ).order_by('name')
    
    context = {
        # Path correction: Only send the relative path, {% static %} in template handles the rest
        'logo_left': settings.MCC_LOGO_LEFT,
        'logo_right': settings.MCC_LOGO_RIGHT,
        'winner_photo': settings.MCC_WINNER_PHOTO,
        'cyclists': Cyclist.objects.filter(is_visible=True).values('user_id', 'id_tag').order_by('user_id'),
        'devices': Device.objects.filter(is_visible=True).values('name', 'display_name').order_by('display_name', 'name'),
        'top_groups': top_groups,
        'room_code': room_code,
        'room_url': room_url,
        'current_target_km': current_target_km,  # For initializing input field and checkboxes
        'is_master': is_master_flag,  # Master flag for template (only relevant if in a room)
    }
    return render(request, 'game/mcc_game.html', context)

# --- NEW HTMX Views ---

@csrf_exempt
def end_session(request):
    """Ends the current user session by deleting all session data."""
    
    # CRITICAL: If in a room, only master can end the session
    room_code = request.session.get('room_code')
    if room_code:
        try:
            room = GameRoom.objects.get(room_code=room_code, is_active=True)
            if not is_master(request, room):
                logger.warning(f"❌ Nicht-Master versucht Session zu beenden: {room_code}, Session: {request.session.session_key}")
                return JsonResponse({"error": _("Nur der Spielleiter kann die Session beenden")}, status=403)
        except GameRoom.DoesNotExist:
            # Room doesn't exist, allow action (user will be redirected)
            pass
    
    # Log the action
    if request.session.get('device_assignments'):
        logger.info(_(f"🛑 Session für Gast-Spiel wurde beendet. Zuweisungen: {request.session.get('device_assignments')}"))
    else:
        logger.info(_("🛑 Session wurde zurückgesetzt."))
        
    # CRITICAL STEP: Deletes the session on the server and invalidates the cookie in the browser
    request.session.flush() 
    
    # Send an empty, successful JSON response.
    return JsonResponse({"status": "session_ended"})

@csrf_exempt
def handle_assignment_form(request):
    """Adds assignments, removes them, or clears all (HTMX POST)."""
    # Sync from room if in a shared room
    sync_session_from_room(request)
    
    active_assignments = request.session.get('device_assignments', {})
    room_code = request.session.get('room_code')
    
    # Get room for master checks
    room = None
    if room_code:
        try:
            room = GameRoom.objects.get(room_code=room_code)
            # Check if room is inactive (ended)
            if not room.is_active:
                # Room was ended - clear session
                if 'room_code' in request.session:
                    del request.session['room_code']
                if 'is_master' in request.session:
                    del request.session['is_master']
                request.session.modified = True
                logger.warning(f"🏁 Versuch, Zuweisung in beendetem Raum zu ändern: {room_code}")
                return JsonResponse({"error": _("Dieser Raum wurde beendet.")}, status=410)  # 410 Gone
        except GameRoom.DoesNotExist:
            # Room doesn't exist - clear session
            if 'room_code' in request.session:
                del request.session['room_code']
            if 'is_master' in request.session:
                del request.session['is_master']
            request.session.modified = True
            pass
    
    logger.info(f"🔍 handle_assignment_form: method={request.method}, room_code={room_code}, current_assignments={active_assignments}")
    
    if request.method == 'POST':
        action = request.POST.get('action') 
        logger.info(f"🔍 Action: {action}, POST data: {dict(request.POST)}")
        
        if action == 'add':
            cyclist = request.POST.get('cyclist')
            device = request.POST.get('device')
            
            if cyclist and device and device not in active_assignments and cyclist not in active_assignments.values():
                active_assignments[device] = cyclist
                request.session['device_assignments'] = active_assignments
                # Track assignment owner for deletion rights
                if 'assignment_owners' not in request.session:
                    request.session['assignment_owners'] = {}
                request.session['assignment_owners'][device] = request.session.session_key
                request.session.modified = True  # CRITICAL: Ensure session is saved immediately
                
                # CRITICAL: Force immediate save to database so Admin GUI can see it
                request.session.save()
                
                # Update GameSession tracking
                from .signals import update_game_session
                update_game_session(request.session.session_key)
                
                logger.info(f"💾 Session saved immediately after assignment: session_key={request.session.session_key}, "
                           f"device_assignments={active_assignments}")
                
                # Update session_to_cyclist mapping in room
                if room and request.session.session_key:
                    session_to_cyclist = room.session_to_cyclist or {}
                    # Store the cyclist assigned by this session (for master transfer)
                    # If session already has a cyclist, update it (in case user reassigns)
                    session_to_cyclist[request.session.session_key] = cyclist
                    room.session_to_cyclist = session_to_cyclist
                    room.save()
                    logger.info(f"✅ Updated session_to_cyclist: {session_to_cyclist}")
                
                logger.info(_(f"✅ Zuweisung hinzugefügt: {cyclist} -> {device}, neue Assignments: {active_assignments}"))
            else:
                logger.warning(_(f"❌ Zuweisung konnte nicht hinzugefügt werden: cyclist={cyclist}, device={device}, active_assignments={active_assignments}"))
        
        elif action == 'remove':
            cyclist_to_remove = request.POST.get('cyclist')
            
            if cyclist_to_remove:
                # Check if user can delete this assignment
                if not can_delete_assignment(request, room, cyclist_to_remove):
                    logger.warning(_(f"❌ Keine Berechtigung zum Löschen der Zuweisung: {cyclist_to_remove}"))
                    return JsonResponse({"error": _("Keine Berechtigung zum Löschen dieser Zuweisung.")}, status=403)
                
                device_key = next((d for d, p in active_assignments.items() if p == cyclist_to_remove), None)
                if device_key:
                    del active_assignments[device_key]
                    # Remove from assignment owners
                    if 'assignment_owners' in request.session and device_key in request.session['assignment_owners']:
                        del request.session['assignment_owners'][device_key]
                    request.session['device_assignments'] = active_assignments
                    request.session.modified = True  # CRITICAL: Ensure session is saved
                    # CRITICAL: Force immediate save to database
                    request.session.save()
                    
                    # Update GameSession tracking
                    from .signals import update_game_session
                    update_game_session(request.session.session_key)
                    
                    logger.info(_(f"✅ Zuweisung entfernt: {cyclist_to_remove}, neue Assignments: {active_assignments}"))
        
        elif action == 'clear':
            # Only master can clear all assignments
            if room and not is_master(request, room):
                logger.warning(_("❌ Nur der Master kann alle Zuweisungen löschen"))
                return JsonResponse({"error": _("Nur der Spielleiter kann alle Zuweisungen löschen.")}, status=403)
            
            request.session['device_assignments'] = {}
            request.session['start_distances'] = {}
            request.session['is_game_stopped'] = False
            if 'announced_winners' in request.session:
                del request.session['announced_winners']
            if 'assignment_owners' in request.session:
                del request.session['assignment_owners']
            request.session.modified = True  # CRITICAL: Ensure session is saved
            logger.info(_("✅ Alle Zuweisungen gelöscht."))
    
    # Sync to room if in a shared room
    if room_code:
        logger.info(f"🔄 Syncing to room {room_code}...")
        sync_room_from_session(request)
        logger.info(f"✅ Sync completed. Room assignments: {request.session.get('device_assignments', {})}")
    else:
        logger.info("ℹ️ Kein Raum aktiv, keine Sync nötig.")

    logger.info(f"🔍 Rendering results table with assignments: {request.session.get('device_assignments', {})}")
    return render_results_table(request) 


def render_target_km_display(request):
    """Renders the target kilometer display fragment for non-master users (for HTMX triggers)."""
    # Sync from room if in a shared room
    room_code = request.session.get('room_code')
    if room_code:
        logger.info(f"🔄 Syncing from room {room_code} for target_km display...")
        sync_session_from_room(request)
        # If room was ended, room_code might have been cleared by sync_session_from_room
        room_code = request.session.get('room_code')  # Re-read in case it was cleared
    
    # Get current target_km from session (synced from room if in a room)
    current_target_km = request.session.get('current_target_km', 0.0)
    if current_target_km is None:
        current_target_km = 0.0
    else:
        current_target_km = float(current_target_km)
    
    context = {
        'current_target_km': current_target_km,
    }
    return render(request, 'game/target_km_fragment.html', context)


def render_results_table(request):
    """Renders the updated results table fragment (for HTMX triggers)."""
    # Sync from room if in a shared room
    room_code = request.session.get('room_code')
    room = None
    if room_code:
        logger.info(f"🔄 Syncing from room {room_code}...")
        room = sync_session_from_room(request)
        # If room was ended, room_code might have been cleared by sync_session_from_room
        room_code = request.session.get('room_code')  # Re-read in case it was cleared
    
    device_assignments = request.session.get('device_assignments', {})
    start_distances = request.session.get('start_distances', {})
    stop_distances = request.session.get('stop_distances', {})
    is_game_stopped = request.session.get('is_game_stopped', False)
    
    logger.info(f"🔍 render_results_table: device_assignments={device_assignments}, room_code={room_code}")
    logger.info(f"🔍 Game state: start_distances={start_distances}, stop_distances={stop_distances}, is_game_stopped={is_game_stopped}")
    
    # Update interval is now fixed
    update_interval = 10 
    
    game_is_active = bool(start_distances)
    logger.info(f"🔍 game_is_active={game_is_active} (based on start_distances)")
    
    if not device_assignments:
        # Get target_km from session even if no assignments
        target_km = request.session.get('current_target_km', 0.0)
        if target_km is None:
            target_km = 0.0
        else:
            target_km = float(target_km)
        logger.info("ℹ️ Keine Zuweisungen, rendere leere Tabelle, target_km=" + str(target_km))
        context = {
            'game_results': [],
            'game_is_active': False,
            'update_interval': update_interval,
            'is_game_stopped': False,
            'target_km': target_km,
            'room_code': room_code,
        }
        return render(request, 'game/results_table_fragment.html', context)

    device_names = device_assignments.keys()
    devices = Device.objects.filter(name__in=device_names).values('name', 'display_name')
    # Create a mapping from device name to display name
    device_display_map = {d['name']: (d['display_name'] if d['display_name'] else d['name']) for d in devices}
    user_ids = device_assignments.values()
    
    logger.info(f"🔍 Device names: {list(device_names)}, User IDs: {list(user_ids)}")
    
    # CRITICAL: Get cyclist data including distance_total (not device distance)
    cyclists = Cyclist.objects.filter(user_id__in=user_ids).values('user_id', 'distance_total', 'coin_conversion_factor')
    cyclist_data = {c['user_id']: c for c in cyclists}
    cyclist_factors = {c['user_id']: c['coin_conversion_factor'] for c in cyclists}
    
    logger.info(f"🔍 Found cyclists: {list(cyclist_data.keys())}, cyclist_data: {cyclist_data}")

    game_results = []
    
    # Get room for master checks
    is_master_flag = False
    if room:
        is_master_flag = is_master(request, room)
    
    # Get assignment owners for deletion rights
    assignment_owners = request.session.get('assignment_owners', {})
    current_session_key = request.session.session_key
    
    # Iterate through device assignments to maintain device-cyclist mapping
    for device_name in device_names:
        user_id = device_assignments.get(device_name)
        
        if not user_id:
            logger.warning(f"⚠️ Kein user_id für device {device_name}")
            continue
        
        if user_id not in cyclist_data:
            logger.warning(f"⚠️ Cyclist {user_id} nicht in Datenbank gefunden! Verfügbare Cyclists: {list(cyclist_data.keys())}")
            continue  # Skip if cyclist not found
        
        cyclist = cyclist_data[user_id]
        
        # CRITICAL: Use cyclist distance_total, not device distance_total
        # Convert Decimal to float for consistent calculations
        current_distance_total = float(cyclist['distance_total'])
        
        if game_is_active and not is_game_stopped:
            # Game is running - calculate distance gained since game start
            start_distance = start_distances.get(user_id, current_distance_total)
            distance_gained = max(0, current_distance_total - start_distance)
            logger.info(f"🔍 Distance calculation (running): user_id={user_id}, current_distance_total={current_distance_total}, start_distance={start_distance}, distance_gained={distance_gained}")
        elif game_is_active and is_game_stopped:
            # Game was stopped - use frozen distance at stop time
            start_distance = start_distances.get(user_id, current_distance_total)
            stop_distance = stop_distances.get(user_id, current_distance_total)
            # Use the distance at stop time, not current distance
            distance_gained = max(0, stop_distance - start_distance)
            logger.info(f"🔍 Distance calculation (stopped): user_id={user_id}, stop_distance={stop_distance}, start_distance={start_distance}, distance_gained={distance_gained}")
        else:
            # Before game start, always show 0 km
            distance_gained = 0
            logger.info(f"🔍 Distance calculation (not started): user_id={user_id}, current_distance_total={current_distance_total}, game_is_active={game_is_active}, is_game_stopped={is_game_stopped}, start_distances={start_distances}, distance_gained={distance_gained}")
            
        # Default value 100 from settings is used if not found
        coin_factor = cyclist_factors.get(user_id, settings.DEFAULT_COIN_CONVERSION_FACTOR) 
        coins_gained = distance_gained * coin_factor
        
        # Check if current user can delete this assignment
        can_delete = False
        is_own_assignment = False
        if not room:
            can_delete = True  # No room = normal mode
            is_own_assignment = True  # In normal mode, all are own assignments
        elif is_master_flag:
            can_delete = True  # Master can delete all
            # Check if this is own assignment
            assignment_owner = assignment_owners.get(device_name)
            is_own_assignment = (assignment_owner == current_session_key)
        else:
            # Check if this assignment belongs to current session
            assignment_owner = assignment_owners.get(device_name)
            can_delete = (assignment_owner == current_session_key)
            is_own_assignment = (assignment_owner == current_session_key)
        
        # Check if this cyclist is the master
        is_master_cyclist = False
        if room and room.master_session_key:
            session_to_cyclist = room.session_to_cyclist or {}
            master_cyclist = session_to_cyclist.get(room.master_session_key)
            is_master_cyclist = (master_cyclist == user_id)
        
        # Use display_name for device if available, otherwise fall back to name
        device_display_name = device_display_map.get(device_name, device_name)
        
        game_results.append({
            "cyclist_name": user_id,
            "device_name": device_display_name,  # Use display_name instead of name
            "distance_km": round(distance_gained, 2),
            "coins": round(coins_gained, 0),
            "progress_percent": 0.0,  # Will be calculated after target_km is known
            "can_delete": can_delete,  # Flag for template
            "is_own_assignment": is_own_assignment,  # Flag for marking own assignments
            "is_master_cyclist": is_master_cyclist,  # Flag for marking master row
        })
    
    # Get target_km from GET parameter (can be empty string, 0, or a number)
    # If no GET parameter, use value from session/room
    target_km_str = request.GET.get('target_km', '')
    if target_km_str:
        # GET parameter provided - check if user can modify
        if room and not is_master_flag:
            logger.warning(f"❌ Nur Master kann Zielkilometer ändern")
            return JsonResponse({"error": _("Nur der Spielleiter kann die Zielkilometer ändern.")}, status=403)
        
        # GET parameter provided - use it
        target_km = float(target_km_str) if target_km_str else 0.0
        logger.info(f"🔍 Target KM from GET parameter: {target_km}")
    else:
        # No GET parameter - use value from session (which was synced from room if in a room)
        target_km = request.session.get('current_target_km', 0.0)
        if target_km is None:
            target_km = 0.0
        else:
            target_km = float(target_km)
        logger.info(f"🔍 Target KM from session/room: {target_km}, room_code={room_code}")
    
    # Sort game results by distance_km (descending - highest first)
    game_results.sort(key=lambda x: x['distance_km'], reverse=True)
    
    # Calculate progress percentage for each result if target is set
    if target_km > 0:
        for result in game_results:
            progress = (result['distance_km'] / target_km) * 100
            result['progress_percent'] = float(min(100.0, round(progress, 1)))
            # Format progress_percent as string with dot (for CSS compatibility)
            # CRITICAL: Always use format_css_number() for CSS values to avoid locale issues
            result['progress_percent_str'] = format_css_number(result['progress_percent'], decimals=1)
            # Debug logging - show calculated progress_percent
            logger.info(f"📊 Progress calculation: cyclist={result['cyclist_name']}, device={result['device_name']}, distance_km={result['distance_km']}, target_km={target_km}, progress={progress}, progress_percent={result['progress_percent']}, progress_percent_str={result['progress_percent_str']}")
    else:
        for result in game_results:
            result['progress_percent'] = 0.0
            result['progress_percent_str'] = "0.0"
            logger.info(f"📊 Progress calculation: cyclist={result['cyclist_name']}, device={result['device_name']}, target_km=0, progress_percent=0.0")
    
    # Get previous target_km from session to detect changes
    previous_target_km = request.session.get('current_target_km', None)
    
    # Convert to float for comparison (handle None case)
    if previous_target_km is not None:
        previous_target_km = float(previous_target_km)
    else:
        previous_target_km = 0.0
    
    # If target_km changed (either from GET parameter or from room sync), update session
    # Use a small epsilon for float comparison to handle floating point precision issues
    if abs(target_km - previous_target_km) > 0.01:
        logger.info(f"🔍 Target KM changed: {previous_target_km} -> {target_km}, resetting announced_winners")
        if 'announced_winners' in request.session:
            del request.session['announced_winners']
        request.session['current_target_km'] = target_km
        request.session.modified = True
        request.session.save()
        
        # Update GameSession tracking
        from .signals import update_game_session
        update_game_session(request.session.session_key)
        
        # CRITICAL: If target_km came from GET parameter, sync it to room immediately
        if target_km_str and room_code:
            logger.info(f"🔄 Syncing target_km {target_km} to room {room_code}")
            sync_room_from_session(request)
    
    # Find all winners who have reached the target (game continues, no auto-stop)
    winner_names = []
    if target_km > 0 and not is_game_stopped:
        for result in game_results:
            if result['distance_km'] >= target_km:
                winner_names.append(result['cyclist_name'])
    
    # Track which winners have already been announced (to avoid duplicate popups)
    announced_winners = request.session.get('announced_winners', [])
    new_winners = [w for w in winner_names if w not in announced_winners]
    
    # Add new winners to the announced list
    if new_winners:
        announced_winners.extend(new_winners)
        request.session['announced_winners'] = announced_winners
        request.session.modified = True
    
    logger.info(f"🔍 Rendering table with {len(game_results)} results: {[r['cyclist_name'] for r in game_results]}")
    
    # Sync to room if in a shared room (only if we have changes, but not if we already synced target_km above)
    if room_code and not (target_km_str and abs(target_km - previous_target_km) > 0.01):
        sync_room_from_session(request)
    
    # Get master cyclist name for template (if in a room with a master)
    master_cyclist_name = None
    if room and room.master_session_key:
        session_to_cyclist = room.session_to_cyclist or {}
        master_cyclist_name = session_to_cyclist.get(room.master_session_key)
    
    context = {
        'game_results': game_results,
        'winner_names': winner_names,  # List of all winners who reached target
        'new_winners': new_winners,  # Winners who just reached target (for popup)
        'game_is_active': game_is_active, 
        'update_interval': update_interval, 
        'is_game_stopped': is_game_stopped,
        'target_km': target_km,  # Target kilometers for progress bar
        'room_code': room_code,  # Room code for automatic updates
        'is_master': is_master_flag,  # Master flag for template
        'master_cyclist_name': master_cyclist_name,  # Master cyclist name for template
        'current_session_key': current_session_key,  # Current session key for template
    }
    logger.info(f"✅ Returning context with {len(game_results)} game_results, is_master={is_master_flag}, master_cyclist_name={master_cyclist_name}, current_session_key={current_session_key}")
    return render(request, 'game/results_table_fragment.html', context)


@csrf_exempt
def start_game(request):
    """Starts the game and saves the initial distances (reads assignments from session)."""
    # Sync from room if in a shared room
    sync_session_from_room(request)
    
    # CRITICAL: Check if user is in a room and if so, only master can start/stop game
    room_code = request.session.get('room_code')
    if room_code:
        try:
            room = GameRoom.objects.get(room_code=room_code, is_active=True)
            if not is_master(request, room):
                logger.warning(f"❌ Nicht-Master versucht Spiel zu starten/stoppen: {room_code}, Session: {request.session.session_key}")
                return JsonResponse({"error": _("Nur der Spielleiter kann das Spiel starten oder stoppen")}, status=403)
        except GameRoom.DoesNotExist:
            # Room doesn't exist, allow action (user will be redirected)
            pass
    
    logger.info(f"🔍 start_game called: method={request.method}, path={request.path}, POST data={dict(request.POST)}")
    if request.method == 'POST':
        action = request.POST.get('action')
        logger.info(f"🔍 Action parameter: {action}")
        if action == 'stop':
            # CRITICAL: Save the distances at stop time to freeze the game results
            device_assignments = request.session.get('device_assignments', {})
            if device_assignments:
                user_ids = device_assignments.values()
                cyclists = Cyclist.objects.filter(user_id__in=user_ids).values('user_id', 'distance_total')
                # Store stop distances by cyclist user_id
                stop_distances = {cyclist['user_id']: float(cyclist['distance_total']) for cyclist in cyclists}
                request.session['stop_distances'] = stop_distances
            
            request.session['is_game_stopped'] = True
            request.session.modified = True  # CRITICAL: Ensure session is saved
            # Sync to room if in a shared room
            sync_room_from_session(request)
            logger.info(_("Spiel via Stopp-Button gestoppt."))
            return JsonResponse({"status": "game_stopped"})

        device_assignments = request.session.get('device_assignments', {})
        logger.info(_(f"🔍 Start-Game Request: device_assignments={device_assignments}, session_key={request.session.session_key}"))
        if not device_assignments:
             logger.warning(_("❌ Start fehlgeschlagen: Keine Zuweisungen in der Session gefunden."))
             return JsonResponse({"error": _("Keine Zuweisungen aktiv.")}, status=400) 

        # CRITICAL: Use cyclist distances, not device distances
        # Get all cyclists assigned to devices
        user_ids = device_assignments.values()
        cyclists = Cyclist.objects.filter(user_id__in=user_ids).values('user_id', 'distance_total')
        
        # Store start distances by cyclist user_id (not device name)
        # CRITICAL: Convert Decimal to float for JSON serialization in session
        start_distances = {cyclist['user_id']: float(cyclist['distance_total']) for cyclist in cyclists}
        
        request.session['start_distances'] = start_distances
        request.session['is_game_stopped'] = False
        # CRITICAL: Clear stop_distances when restarting the game
        if 'stop_distances' in request.session:
            del request.session['stop_distances']
        # CRITICAL: Clear announced winners when starting a new game
        if 'announced_winners' in request.session:
            del request.session['announced_winners']
        # CRITICAL: Clear current_target_km when starting a new game
        if 'current_target_km' in request.session:
            del request.session['current_target_km']
        # CRITICAL: Also clear winner_names to ensure fresh start
        request.session.modified = True  # CRITICAL: Ensure session is saved
        # Sync to room if in a shared room
        sync_room_from_session(request)
        logger.info(_("✅ Spiel gestartet. Startdistanzen (Radler): {start_distances}, announced_winners und current_target_km zurückgesetzt.").format(start_distances=start_distances))
        
        logger.info(_(f"✅ Spiel gestartet. Startdistanzen (Radler): {start_distances}"))
        return JsonResponse({"status": "game_started"})
        
    return JsonResponse({"error": _("Methode nicht erlaubt")}, status=405)


def get_game_players(request):
    cyclists = Cyclist.objects.all().values('user_id', 'id_tag')
    cyclist_list = [{"user_id": c["user_id"], "mapping_key": c["id_tag"]} for c in cyclists]
    return JsonResponse(cyclist_list, safe=False)

def get_game_devices(request):
    devices = Device.objects.all().values('name')
    device_list = [{"name": d["name"]} for d in devices]
    return JsonResponse(device_list, safe=False)

def get_game_data(request):
    # Unchanged
    pass

def serve_goal_sound(request):
    sound_path = settings.MCC_GAME_SOUND
    
    if not os.path.exists(sound_path):
        logger.error(f"❌ Sounddatei nicht gefunden: {sound_path}")
        raise Http404("Sound file not found")
        
    return FileResponse(open(sound_path, 'rb'), content_type='audio/mpeg')

def get_game_images(request):
    return JsonResponse({
        "logo_left": settings.STATIC_URL + settings.MCC_LOGO_LEFT,
        "logo_right": settings.STATIC_URL + settings.MCC_LOGO_RIGHT,
        "winner_photo": settings.STATIC_URL + settings.MCC_WINNER_PHOTO
    })


# --- GameRoom Views ---

def create_room(request):
    """Creates a new game room and redirects to it."""
    # Ensure session has a key
    if not request.session.session_key:
        request.session.create()
    
    room = GameRoom.objects.create()
    room.master_session_key = request.session.session_key  # Set creator as master
    room.save()
    request.session['room_code'] = room.room_code
    request.session['is_master'] = True  # Flag for template
    request.session.modified = True
    request.session.save()
    
    # Update GameSession tracking
    from .signals import update_game_session
    update_game_session(request.session.session_key)
    
    logger.info(_(f"🏠 Neuer Spiel-Raum erstellt: {room.room_code}, Master: {request.session.session_key}"))
    return redirect('game:room_page', room_code=room.room_code)


def join_room(request):
    """Allows user to join an existing room by entering a room code."""
    if request.method == 'POST':
        room_code = request.POST.get('room_code', '').strip().upper()
        if room_code:
            try:
                room = GameRoom.objects.get(room_code=room_code)
                
                # Check if room is inactive (ended)
                if not room.is_active:
                    return render(request, 'game/join_room.html', {
                        'error': _('Dieser Raum wurde beendet.'),
                        'room_code': room_code
                    })
                
                # Ensure session has a key
                if not request.session.session_key:
                    request.session.create()
                
                request.session['room_code'] = room.room_code
                request.session.modified = True
                request.session.save()
                
                # Update GameSession tracking
                from .signals import update_game_session
                update_game_session(request.session.session_key)
                
                # Sync room data to session (includes master flag)
                sync_session_from_room(request)
                
                # Update session_to_cyclist mapping if this session has assignments
                if request.session.session_key:
                    device_assignments = request.session.get('device_assignments', {})
                    if device_assignments:
                        # Get the first cyclist assigned by this session
                        assignment_owners = request.session.get('assignment_owners', {})
                        for device, cyclist in device_assignments.items():
                            if assignment_owners.get(device) == request.session.session_key:
                                session_to_cyclist = room.session_to_cyclist or {}
                                session_to_cyclist[request.session.session_key] = cyclist
                                room.session_to_cyclist = session_to_cyclist
                                room.save()
                                logger.info(f"✅ Updated session_to_cyclist on join: {session_to_cyclist}")
                                break
                
                logger.info(_(f"✅ Raum beigetreten: {room_code}, Master: {is_master(request, room)}"))
                return redirect('game:room_page', room_code=room_code)
            except GameRoom.DoesNotExist:
                return render(request, 'game/join_room.html', {
                    'error': _('Raum nicht gefunden. Bitte Code überprüfen.'),
                    'room_code': room_code
                })
    
    return render(request, 'game/join_room.html')


def room_page(request, room_code):
    """Main game page for a specific room."""
    try:
        room = GameRoom.objects.get(room_code=room_code, is_active=True)
        
        # CRITICAL: If user is admin and master_session_key indicates admin should become master
        # This allows admins to take control of rooms from the admin interface
        # Supports two modes:
        # 1. Normal: Only if there's no active master (admin_pending_{user_id}_{username})
        # 2. Force: Override existing master (admin_pending_force_{user_id}_{username})
        if request.user.is_staff and request.session.session_key:
            current_master = room.master_session_key
            if current_master and current_master.startswith('admin_pending_'):
                # Extract admin user info from the marker
                parts = current_master.split('_')
                is_force = len(parts) >= 4 and parts[2] == 'force'
                
                # Determine admin user ID based on mode
                if is_force:
                    admin_user_id = parts[3] if len(parts) >= 4 else None
                else:
                    admin_user_id = parts[2] if len(parts) >= 3 else None
                
                # Check if this matches the current admin user
                if admin_user_id and str(request.user.id) == admin_user_id:
                    active_sessions = room.active_sessions or []
                    
                    # Check if there's an active master (for non-force mode)
                    has_active_master = False
                    if not is_force:
                        # In normal mode, check if there's an active master session
                        # (other than the pending admin marker)
                        for session in active_sessions:
                            if session and session != current_master and not session.startswith('admin_pending_'):
                                has_active_master = True
                                break
                    
                    # Set as master if: force mode OR no active master exists
                    if is_force or not has_active_master:
                        # Set current session as master
                        room.master_session_key = request.session.session_key
                        
                        # Add to active_sessions if not already present
                        if request.session.session_key not in active_sessions:
                            active_sessions.append(request.session.session_key)
                            room.active_sessions = active_sessions
                        
                        # Update session_to_cyclist mapping
                        session_to_cyclist = room.session_to_cyclist or {}
                        session_to_cyclist[request.session.session_key] = f"admin_{request.user.username}"
                        room.session_to_cyclist = session_to_cyclist
                        
                        room.save()
                        mode_text = "erzwungen" if is_force else "kein aktiver Master vorhanden"
                        logger.info(f"👑 Admin {request.user.username} wurde automatisch als Master für Raum {room_code} gesetzt ({mode_text})")
                    else:
                        logger.info(f"ℹ️ Admin {request.user.username} betrat Raum {room_code}, aber es existiert bereits ein aktiver Master")
        
        request.session['room_code'] = room_code
        request.session.modified = True
        # Sync room data to session
        sync_session_from_room(request)
        
        # Build full URL for QR code
        base_url = request.build_absolute_uri('/')[:-1]
        room_url = f"{base_url}{reverse('game:room_page', args=[room_code])}"
        
        # Get current target_km from session (synced from room)
        current_target_km = request.session.get('current_target_km', 0.0)
        if current_target_km is None:
            current_target_km = 0.0
        else:
            current_target_km = float(current_target_km)
        
        # Get master flag
        is_master_flag = request.session.get('is_master', False)
        
        # Get all top-level parent groups (schools) for filtering
        top_groups = Group.objects.filter(
            parent__isnull=True,
            is_visible=True
        ).order_by('name')
        
        context = {
            'logo_left': settings.MCC_LOGO_LEFT,
            'logo_right': settings.MCC_LOGO_RIGHT,
            'winner_photo': settings.MCC_WINNER_PHOTO,
            'cyclists': Cyclist.objects.filter(is_visible=True).values('user_id', 'id_tag').order_by('user_id'),
            'devices': Device.objects.filter(is_visible=True).values('name', 'display_name').order_by('display_name', 'name'),
            'top_groups': top_groups,
            'room_code': room_code,
            'room_url': room_url,
            'current_target_km': current_target_km,  # For initializing input field and checkboxes
            'is_master': is_master_flag,  # Master flag for template
        }
        return render(request, 'game/mcc_game.html', context)
    except GameRoom.DoesNotExist:
        return render(request, 'game/join_room.html', {
            'error': _('Raum nicht gefunden. Bitte Code überprüfen.')
        })


def leave_room(request):
    """Leaves the current room and returns to normal game mode. Removes all assignments of the leaving participant from the room."""
    if 'room_code' in request.session:
        room_code = request.session['room_code']
        current_session_key = request.session.session_key
        
        try:
            room = GameRoom.objects.get(room_code=room_code, is_active=True)
            
            # Get assignment_owners from session to identify which assignments belong to this session
            assignment_owners = request.session.get('assignment_owners', {})
            
            # Find all devices assigned by this session
            devices_to_remove = []
            for device, owner_session in assignment_owners.items():
                if owner_session == current_session_key:
                    devices_to_remove.append(device)
            
            # Remove assignments from room
            if devices_to_remove:
                device_assignments = room.device_assignments or {}
                cyclists_to_remove = []
                
                for device in devices_to_remove:
                    if device in device_assignments:
                        cyclist = device_assignments[device]
                        cyclists_to_remove.append(cyclist)
                        del device_assignments[device]
                        logger.info(f"🗑️ Entferne Zuweisung {device} -> {cyclist} von Session {current_session_key}")
                
                room.device_assignments = device_assignments
                
                # Update start_distances and stop_distances if game is active
                start_distances = room.start_distances or {}
                stop_distances = room.stop_distances or {}
                for cyclist in cyclists_to_remove:
                    if cyclist in start_distances:
                        del start_distances[cyclist]
                    if cyclist in stop_distances:
                        del stop_distances[cyclist]
                
                room.start_distances = start_distances
                room.stop_distances = stop_distances
                
                # Remove from session_to_cyclist mapping
                session_to_cyclist = room.session_to_cyclist or {}
                if current_session_key in session_to_cyclist:
                    del session_to_cyclist[current_session_key]
                    room.session_to_cyclist = session_to_cyclist
                
                # Remove from active_sessions
                active_sessions = room.active_sessions or []
                if current_session_key in active_sessions:
                    active_sessions.remove(current_session_key)
                    room.active_sessions = active_sessions
                
                # If leaving user was master, we need to transfer master to another participant
                if room.master_session_key == current_session_key:
                    # Master is leaving - find a new master from remaining participants
                    # Use the already updated active_sessions (current_session_key already removed)
                    active_sessions_after_leave = active_sessions
                    
                    if active_sessions_after_leave:
                        # Choose the first remaining active session as new master
                        new_master_session = active_sessions_after_leave[0]
                        room.master_session_key = new_master_session
                        
                        # Get cyclist name for logging
                        session_to_cyclist = room.session_to_cyclist or {}
                        new_master_cyclist = session_to_cyclist.get(new_master_session, 'Unbekannt')
                        
                        logger.info(f"👑 Master verlässt Raum {room_code}, neuer Master: {new_master_session} (Cyclist: {new_master_cyclist})")
                    else:
                        # No other participants - end the room
                        logger.warning(f"⚠️ Master verlässt Raum {room_code}, keine anderen Teilnehmer, Raum wird beendet")
                        room.is_active = False
                
                room.save()
                logger.info(f"✅ Zuweisungen entfernt: {devices_to_remove}")
            
            # Clear room-related data from session
            if 'room_code' in request.session:
                del request.session['room_code']
            if 'is_master' in request.session:
                del request.session['is_master']
            # Also clear assignments from session (they're removed from room anyway)
            request.session['device_assignments'] = {}
            if 'assignment_owners' in request.session:
                del request.session['assignment_owners']
            if 'start_distances' in request.session:
                del request.session['start_distances']
            if 'stop_distances' in request.session:
                del request.session['stop_distances']
            if 'announced_winners' in request.session:
                del request.session['announced_winners']
            if 'current_target_km' in request.session:
                del request.session['current_target_km']
            
            request.session.modified = True
            logger.info(_(f"👋 Raum verlassen: {room_code}, Zuweisungen entfernt: {len(devices_to_remove) if devices_to_remove else 0}"))
            
        except GameRoom.DoesNotExist:
            # Room doesn't exist anymore, just clear session
            if 'room_code' in request.session:
                del request.session['room_code']
            if 'is_master' in request.session:
                del request.session['is_master']
            request.session.modified = True
            logger.warning(f"⚠️ Raum {room_code} existiert nicht mehr")
    
    return redirect('game:game_page')


def generate_qr_code(request, room_code):
    """Generates a QR code image for the room URL."""
    # Try to import at runtime in case it's available now but wasn't at module load
    # (e.g. after installing the package and restarting the server)
    try:
        import qrcode
        from PIL import Image
    except ImportError as e:
        logger.error(f"qrcode/PIL not available at runtime: {e}. Install with: pip install qrcode[pil]")
        return HttpResponse("QR code generation not available. Please install qrcode[pil] and restart the server.", status=503)
    
    try:
        # Build full URL
        base_url = request.build_absolute_uri('/')[:-1]
        room_url = f"{base_url}{reverse('game:room_page', args=[room_code])}"
        
        # Generate QR code
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(room_url)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Convert to HTTP response
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        
        return HttpResponse(buffer.getvalue(), content_type='image/png')
    except Exception as e:
        logger.error(f"Error generating QR code: {e}", exc_info=True)
        return HttpResponse(f"Error generating QR code: {str(e)}", status=500)


@csrf_exempt
def end_room(request):
    """Ends a game room (only master can do this)."""
    room_code = request.session.get('room_code')
    if not room_code:
        return JsonResponse({"error": _("Kein Raum aktiv")}, status=400)
    
    try:
        room = GameRoom.objects.get(room_code=room_code, is_active=True)
        if not is_master(request, room):
            logger.warning(f"❌ Nicht-Master versucht Raum zu beenden: {room_code}")
            return JsonResponse({"error": _("Nur der Spielleiter kann den Raum beenden")}, status=403)
        
        room.is_active = False
        room.save()
        request.session.flush()
        logger.info(_(f"🏁 Raum beendet: {room_code}"))
        return JsonResponse({"status": "room_ended"})
    except GameRoom.DoesNotExist:
        return JsonResponse({"error": _("Raum nicht gefunden")}, status=404)


@csrf_exempt
def transfer_master(request):
    """Transfers master role to another participant."""
    room_code = request.session.get('room_code')
    if not room_code:
        logger.warning("❌ transfer_master: Kein Raum aktiv")
        return JsonResponse({"error": _("Kein Raum aktiv")}, status=400)
    
    try:
        room = GameRoom.objects.get(room_code=room_code, is_active=True)
        if not is_master(request, room):
            logger.warning(f"❌ Nicht-Master versucht Master-Rolle zu übertragen: {room_code}, Session: {request.session.session_key}")
            return JsonResponse({"error": _("Nur der Spielleiter kann die Rolle übertragen")}, status=403)
        
        # Get cyclist user_id from POST (we'll find the session via session_to_cyclist mapping)
        cyclist_user_id = request.POST.get('cyclist_user_id')
        if not cyclist_user_id:
            logger.warning(f"❌ transfer_master: Kein cyclist_user_id übergeben. POST data: {dict(request.POST)}")
            return JsonResponse({"error": _("Ungültige Parameter")}, status=400)
        
        logger.info(f"🔍 transfer_master: Suche Session für Cyclist {cyclist_user_id}")
        
        # Find session key for this cyclist
        session_to_cyclist = room.session_to_cyclist or {}
        logger.info(f"🔍 transfer_master: session_to_cyclist Mapping: {session_to_cyclist}")
        
        new_master_session = None
        for session_key, cyclist_id in session_to_cyclist.items():
            if cyclist_id == cyclist_user_id:
                new_master_session = session_key
                logger.info(f"✅ transfer_master: Gefundene Session {session_key} für Cyclist {cyclist_user_id}")
                break
        
        if not new_master_session:
            # Fallback: Try to find via device_assignments and assignment_owners
            logger.warning(f"⚠️ transfer_master: Cyclist nicht in session_to_cyclist gefunden, versuche Fallback")
            device_assignments = room.device_assignments or {}
            # We need assignment_owners, but that's in sessions, not in room
            # For now, just return error with helpful message
            return JsonResponse({
                "error": _("Teilnehmer nicht gefunden. Bitte stellen Sie sicher, dass der Teilnehmer eine Zuweisung hat."),
                "debug": {
                    "cyclist_user_id": cyclist_user_id,
                    "session_to_cyclist": session_to_cyclist,
                    "device_assignments": device_assignments
                }
            }, status=404)
        
        room.master_session_key = new_master_session
        # CRITICAL: Update last_activity to trigger immediate sync for all clients
        room.save()  # This updates last_activity automatically
        
        # CRITICAL: Update old master's session immediately
        request.session['is_master'] = False
        request.session.modified = True
        
        # CRITICAL: Force immediate sync for new master by updating room's last_activity
        # This ensures the new master's next request will see the updated master status
        # We can't directly update the new master's session, but updating last_activity
        # ensures sync_session_from_room will be called on their next request
        from django.utils import timezone
        room.last_activity = timezone.now()
        room.save(update_fields=['last_activity'])
        
        logger.info(_(f"👑 Master-Rolle übertragen: {room_code}, neuer Master: {new_master_session} (Cyclist: {cyclist_user_id})"))
        return JsonResponse({
            "status": "master_transferred",
            "new_master_session": new_master_session,
            "room_code": room_code
        })
    except GameRoom.DoesNotExist:
        logger.error(f"❌ transfer_master: Raum nicht gefunden: {room_code}")
        return JsonResponse({"error": _("Raum nicht gefunden")}, status=404)


@csrf_exempt
def sync_session_endpoint(request):
    """HTMX endpoint to force sync_session_from_room - useful after master transfer."""
    sync_session_from_room(request)
    return JsonResponse({"status": "synced", "is_master": request.session.get('is_master', False)})


def render_game_buttons(request):
    """HTMX endpoint to render game control buttons based on current master status."""
    # Sync from room if in a shared room
    sync_session_from_room(request)
    
    room_code = request.session.get('room_code')
    is_master_flag = False
    if room_code:
        try:
            room = GameRoom.objects.get(room_code=room_code, is_active=True)
            is_master_flag = is_master(request, room)
        except GameRoom.DoesNotExist:
            pass
    
    context = {
        'room_code': room_code,
        'is_master': is_master_flag,
    }
    return render(request, 'game/partials/game_buttons.html', context)


def get_filtered_cyclists(request):
    """HTMX endpoint to get filtered cyclists based on group filters and search."""
    top_group_id = request.GET.get('top_group', '').strip()
    subgroup_id = request.GET.get('subgroup', '').strip()
    # Support both 'search' and 'cyclist_search' parameter names
    search_query = request.GET.get('cyclist_search', request.GET.get('search', '')).strip()
    
    logger.info(f"🔍 get_filtered_cyclists: top_group_id={top_group_id}, subgroup_id={subgroup_id}, search_query={search_query}")
    
    # Start with all visible cyclists (this handles the case when all filters are reset)
    cyclists_qs = Cyclist.objects.filter(is_visible=True)
    
    # Filter by subgroup if specified (subgroup takes priority)
    # CRITICAL: Only filter if subgroup_id is not empty
    if subgroup_id and subgroup_id != '':
        try:
            subgroup = Group.objects.get(id=int(subgroup_id), is_visible=True)
            cyclists_qs = cyclists_qs.filter(groups__id=subgroup.id).distinct()
            logger.info(f"✅ Filtering by subgroup: {subgroup.name} (ID: {subgroup.id})")
        except (Group.DoesNotExist, ValueError) as e:
            logger.warning(f"⚠️ Invalid subgroup ID: {subgroup_id}, error: {e}")
            pass
    # Filter by top group if specified (but no subgroup)
    # CRITICAL: Only filter if top_group_id is not empty
    elif top_group_id and top_group_id != '':
        try:
            top_group = Group.objects.get(id=int(top_group_id), is_visible=True)
            # Get all descendant group IDs
            def get_all_descendant_ids(ancestor_id, visited=None):
                if visited is None:
                    visited = set()
                if ancestor_id in visited:
                    return set()
                visited.add(ancestor_id)
                
                descendant_ids = set()
                direct_children = Group.objects.filter(
                    parent_id=ancestor_id,
                    is_visible=True
                ).values_list('id', flat=True)
                descendant_ids.update(direct_children)
                
                for child_id in direct_children:
                    descendant_ids.update(get_all_descendant_ids(child_id, visited))
                
                return descendant_ids
            
            descendant_ids = get_all_descendant_ids(top_group.id)
            descendant_ids.add(top_group.id)  # Include the top group itself
            
            logger.info(f"✅ Filtering by top group: {top_group.name} (ID: {top_group.id}), descendant_ids: {descendant_ids}")
            cyclists_qs = cyclists_qs.filter(groups__id__in=descendant_ids).distinct()
        except (Group.DoesNotExist, ValueError) as e:
            logger.warning(f"⚠️ Invalid top group ID: {top_group_id}, error: {e}")
            pass
    
    # Apply search filter if provided
    if search_query:
        cyclists_qs = cyclists_qs.filter(
            Q(user_id__icontains=search_query) |
            Q(id_tag__icontains=search_query)
        )
    
    # Log final query count for debugging
    final_count = cyclists_qs.count()
    logger.info(f"✅ get_filtered_cyclists: Query returns {final_count} cyclists (top_group_id='{top_group_id}', subgroup_id='{subgroup_id}', search_query='{search_query}')")
    
    # CRITICAL: If no filters are applied, we should return ALL visible cyclists
    # Log the actual query being executed for debugging
    if not top_group_id and not subgroup_id and not search_query:
        logger.info(f"✅ get_filtered_cyclists: No filters applied - returning ALL {final_count} visible cyclists")
    
    # Get cyclists with their group information for display
    cyclists = []
    for cyclist in cyclists_qs.select_related().prefetch_related('groups').order_by('user_id')[:100]:  # Limit to 100 for performance
        # Get primary group info for display
        primary_group = cyclist.groups.first()
        group_label = ''
        if primary_group:
            # Try to get subgroup name and top parent name
            subgroup_name = primary_group.get_kiosk_label()
            top_parent = primary_group.top_parent_name if hasattr(primary_group, 'top_parent_name') else ''
            if top_parent and top_parent != subgroup_name:
                group_label = f"{top_parent} - {subgroup_name}"
            else:
                group_label = subgroup_name
        
        cyclists.append({
            'user_id': cyclist.user_id,
            'id_tag': cyclist.id_tag,
            'group_label': group_label,
        })
    
    logger.info(f"✅ get_filtered_cyclists: Returning {len(cyclists)} cyclists in response")
    return render(request, 'game/partials/cyclist_options.html', {'cyclists': cyclists})


def get_subgroups(request):
    """HTMX endpoint to get subgroups for a selected top group."""
    top_group_id = request.GET.get('top_group', '')
    
    if not top_group_id:
        return render(request, 'game/partials/subgroup_options.html', {'subgroups': []})
    
    try:
        top_group = Group.objects.get(id=int(top_group_id), is_visible=True)
        # Get direct children (subgroups)
        subgroups = top_group.children.filter(is_visible=True).order_by('name')
        
        subgroups_data = []
        for subgroup in subgroups:
            subgroups_data.append({
                'id': subgroup.id,
                'name': subgroup.get_kiosk_label(),
            })
        
        return render(request, 'game/partials/subgroup_options.html', {'subgroups': subgroups_data})
    except (Group.DoesNotExist, ValueError):
        return render(request, 'game/partials/subgroup_options.html', {'subgroups': []})


def get_filtered_devices(request):
    """HTMX endpoint to get filtered devices (using display_name).
    
    Devices are typically assigned to top-level groups only, as multiple classes
    can use the same device. Therefore, we only filter by top_group, not by subgroup.
    """
    top_group_id = request.GET.get('top_group', '').strip()
    # Support both 'search' and 'device_search' parameter names
    search_query = request.GET.get('device_search', request.GET.get('search', '')).strip()
    
    logger.info(f"🔍 get_filtered_devices: top_group_id={top_group_id}, search_query={search_query}")
    
    # Start with all visible devices
    devices_qs = Device.objects.filter(is_visible=True)
    
    # Filter by top group if specified
    # Note: Devices are typically assigned to top-level groups only
    # CRITICAL: Only filter if top_group_id is not empty
    if top_group_id and top_group_id != '':
        try:
            top_group = Group.objects.get(id=int(top_group_id), is_visible=True)
            # Filter devices that are assigned to this top group
            devices_qs = devices_qs.filter(group=top_group)
            logger.info(f"✅ Filtering devices by top group: {top_group.name} (ID: {top_group.id})")
        except (Group.DoesNotExist, ValueError) as e:
            logger.warning(f"⚠️ Invalid top group ID: {top_group_id}, error: {e}")
            pass
    else:
        logger.info(f"✅ No top group filter applied - returning all visible devices")
    
    # Apply search filter if provided
    if search_query:
        devices_qs = devices_qs.filter(
            Q(display_name__icontains=search_query) |
            Q(name__icontains=search_query)
        )
    
    # Get devices ordered by display_name (or name if display_name is empty)
    devices = []
    for device in devices_qs.order_by('display_name', 'name')[:100]:  # Limit to 100 for performance
        # Use display_name if available, otherwise fall back to name
        display_name = device.display_name if device.display_name else device.name
        devices.append({
            'name': device.name,  # Keep original name for form submission
            'display_name': display_name,  # Display name for user
        })
    
    logger.info(f"✅ Returning {len(devices)} filtered devices")
    return render(request, 'game/partials/device_options.html', {'devices': devices})