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
from django.http import JsonResponse, FileResponse, Http404
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from api.models import Cyclist
from iot.models import Device
from django.db.models.functions import Coalesce 
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


# --- HTML View ---
def game_page(request):
    """Serves the main page of the kilometer challenge (replaces mcc_game.py:/)."""
    context = {
        # Path correction: Only send the relative path, {% static %} in template handles the rest
        'logo_left': settings.MCC_LOGO_LEFT,
        'logo_right': settings.MCC_LOGO_RIGHT,
        'winner_photo': settings.MCC_WINNER_PHOTO,
        'cyclists': Cyclist.objects.all().values('user_id', 'id_tag').order_by('user_id'),
        'devices': Device.objects.all().values('name').order_by('name'),
    }
    return render(request, 'game/mcc_game.html', context)

# --- NEW HTMX Views ---

@csrf_exempt
def end_session(request):
    """Ends the current user session by deleting all session data."""
    
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
    active_assignments = request.session.get('device_assignments', {})
    
    if request.method == 'POST':
        action = request.POST.get('action') 
        
        if action == 'add':
            cyclist = request.POST.get('cyclist')
            device = request.POST.get('device')
            
            if cyclist and device and device not in active_assignments and cyclist not in active_assignments.values():
                active_assignments[device] = cyclist
                request.session['device_assignments'] = active_assignments
                request.session.modified = True  # CRITICAL: Ensure session is saved
                logger.info(_(f"Zuweisung hinzugefügt: {cyclist} -> {device}"))
            else:
                logger.warning(_(f"Zuweisung konnte nicht hinzugefügt werden: cyclist={cyclist}, device={device}, active_assignments={active_assignments}"))
        
        elif action == 'remove':
            cyclist_to_remove = request.POST.get('cyclist')
            
            if cyclist_to_remove:
                device_key = next((d for d, p in active_assignments.items() if p == cyclist_to_remove), None)
                if device_key:
                    del active_assignments[device_key]
                    request.session['device_assignments'] = active_assignments
                    request.session.modified = True  # CRITICAL: Ensure session is saved
                    logger.info(_(f"Zuweisung entfernt: {cyclist_to_remove}"))
        
        elif action == 'clear':
            request.session['device_assignments'] = {}
            request.session['start_distances'] = {}
            request.session['is_game_stopped'] = False
            if 'announced_winners' in request.session:
                del request.session['announced_winners']
            request.session.modified = True  # CRITICAL: Ensure session is saved
            logger.info(_("Alle Zuweisungen gelöscht."))

    return render_results_table(request) 


def render_results_table(request):
    """Renders the updated results table fragment (for HTMX triggers)."""
    device_assignments = request.session.get('device_assignments', {})
    start_distances = request.session.get('start_distances', {})
    stop_distances = request.session.get('stop_distances', {})
    is_game_stopped = request.session.get('is_game_stopped', False)
    
    # Update interval is now fixed
    update_interval = 10 
    
    game_is_active = bool(start_distances)
    
    if not device_assignments:
        return render(request, 'game/results_table_fragment.html', {'game_results': []})

    device_names = device_assignments.keys()
    devices = Device.objects.filter(name__in=device_names).values('name')
    user_ids = device_assignments.values()
    
    # CRITICAL: Get cyclist data including distance_total (not device distance)
    cyclists = Cyclist.objects.filter(user_id__in=user_ids).values('user_id', 'distance_total', 'coin_conversion_factor')
    cyclist_data = {c['user_id']: c for c in cyclists}
    cyclist_factors = {c['user_id']: c['coin_conversion_factor'] for c in cyclists}

    game_results = []
    
    # Iterate through device assignments to maintain device-cyclist mapping
    for device_name in device_names:
        user_id = device_assignments.get(device_name)
        
        if not user_id or user_id not in cyclist_data:
            continue  # Skip if cyclist not found
        
        cyclist = cyclist_data[user_id]
        
        # CRITICAL: Use cyclist distance_total, not device distance_total
        # Convert Decimal to float for consistent calculations
        current_distance_total = float(cyclist['distance_total'])
        
        if game_is_active and not is_game_stopped:
            # Game is running - calculate distance gained since game start
            start_distance = start_distances.get(user_id, current_distance_total)
            distance_gained = max(0, current_distance_total - start_distance)
        elif game_is_active and is_game_stopped:
            # Game was stopped - use frozen distance at stop time
            start_distance = start_distances.get(user_id, current_distance_total)
            stop_distance = stop_distances.get(user_id, current_distance_total)
            # Use the distance at stop time, not current distance
            distance_gained = max(0, stop_distance - start_distance)
        else:
            # Before game start, always show 0 km
            distance_gained = 0
            
        # Default value 100 from settings is used if not found
        coin_factor = cyclist_factors.get(user_id, settings.DEFAULT_COIN_CONVERSION_FACTOR) 
        coins_gained = distance_gained * coin_factor
        
        game_results.append({
            "cyclist_name": user_id,
            "device_name": device_name,
            "distance_km": round(distance_gained, 2),
            "coins": round(coins_gained, 0),
            "progress_percent": 0.0  # Will be calculated after target_km is known
        })
    
    # Get target_km from GET parameter (can be empty string, 0, or a number)
    target_km_str = request.GET.get('target_km', '') or ''
    target_km = float(target_km_str) if target_km_str else 0.0
    
    # Sort game results by distance_km (descending - highest first)
    game_results.sort(key=lambda x: x['distance_km'], reverse=True)
    
    # Calculate progress percentage for each result if target is set
    if target_km > 0:
        for result in game_results:
            progress = (result['distance_km'] / target_km) * 100
            result['progress_percent'] = min(100.0, round(progress, 1))
    else:
        for result in game_results:
            result['progress_percent'] = 0.0
    
    # Get previous target_km from session to detect changes
    previous_target_km = request.session.get('current_target_km', None)
    
    # Convert to float for comparison (handle None case)
    if previous_target_km is not None:
        previous_target_km = float(previous_target_km)
    else:
        previous_target_km = 0.0
    
    # If target_km changed, reset announced_winners to allow new winners for new target
    # Use a small epsilon for float comparison to handle floating point precision issues
    if abs(target_km - previous_target_km) > 0.01:
        logger.info(f"🔍 Target KM changed: {previous_target_km} -> {target_km}, resetting announced_winners")
        if 'announced_winners' in request.session:
            del request.session['announced_winners']
        request.session['current_target_km'] = target_km
        request.session.modified = True
    
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

    context = {
        'game_results': game_results,
        'winner_names': winner_names,  # List of all winners who reached target
        'new_winners': new_winners,  # Winners who just reached target (for popup)
        'game_is_active': game_is_active, 
        'update_interval': update_interval, 
        'is_game_stopped': is_game_stopped,
        'target_km': target_km,  # Target kilometers for progress bar
    }
    return render(request, 'game/results_table_fragment.html', context)


@csrf_exempt
def start_game(request):
    """Starts the game and saves the initial distances (reads assignments from session)."""
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