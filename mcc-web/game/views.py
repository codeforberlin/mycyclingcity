# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    views.py
# @author  Roland Rutz

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
                logger.info(_(f"Zuweisung hinzugefügt: {cyclist} -> {device}"))
        
        elif action == 'remove':
            cyclist_to_remove = request.POST.get('cyclist')
            
            if cyclist_to_remove:
                device_key = next((d for d, p in active_assignments.items() if p == cyclist_to_remove), None)
                if device_key:
                    del active_assignments[device_key]
                    request.session['device_assignments'] = active_assignments
                    logger.info(_(f"Zuweisung entfernt: {cyclist_to_remove}"))
        
        elif action == 'clear':
            request.session['device_assignments'] = {}
            request.session['start_distances'] = {}
            request.session['is_game_stopped'] = False
            logger.info(_("Alle Zuweisungen gelöscht."))

    return render_results_table(request) 


def render_results_table(request):
    """Renders the updated results table fragment (for HTMX triggers)."""
    device_assignments = request.session.get('device_assignments', {})
    start_distances = request.session.get('start_distances', {})
    
    # Update interval is now fixed
    update_interval = 10 
    
    game_is_active = bool(start_distances)
    
    if not device_assignments:
        return render(request, 'game/results_table_fragment.html', {'game_results': []})

    device_names = device_assignments.keys()
    devices = Device.objects.filter(name__in=device_names).values('name', 'distance_total')
    user_ids = device_assignments.values()
    
    cyclists = Cyclist.objects.filter(user_id__in=user_ids).values('user_id', 'coin_conversion_factor')
    cyclist_factors = {c['user_id']: c['coin_conversion_factor'] for c in cyclists}

    game_results = []
    
    for device in devices:
        device_name = device['name']
        user_id = device_assignments.get(device_name)
        
        current_distance_total = device['distance_total']
        
        if game_is_active:
            start_distance = start_distances.get(device_name, 0)
            distance_gained = (current_distance_total - start_distance)
        else:
            distance_gained = 0
            
        # Default value 100 from settings is used if not found
        coin_factor = cyclist_factors.get(user_id, settings.DEFAULT_COIN_CONVERSION_FACTOR) 
        coins_gained = distance_gained * coin_factor
        
        game_results.append({
            "cyclist_name": user_id,
            "device_name": device_name,
            "distance_km": round(distance_gained, 2),
            "coins": round(coins_gained, 0)
        })
        
    target_km = float(request.GET.get('target_km', 0) or 0)
    is_game_stopped = request.session.get('is_game_stopped', False)
    
    winner_name = None
    if target_km > 0 and not is_game_stopped:
        for result in game_results:
            if result['distance_km'] >= target_km:
                winner_name = result['cyclist_name']
                request.session['is_game_stopped'] = True 
                break 

    context = {
        'game_results': game_results,
        'winner_name': winner_name,
        'game_is_active': game_is_active, 
        'update_interval': update_interval, 
        'is_game_stopped': is_game_stopped,
    }
    return render(request, 'game/results_table_fragment.html', context)


@csrf_exempt
def start_game(request):
    """Starts the game and saves the initial distances (reads assignments from session)."""
    if request.method == 'POST':
        if request.POST.get('action') == 'stop':
            request.session['is_game_stopped'] = True
            logger.info(_("Spiel via Stopp-Button gestoppt."))
            return JsonResponse({"status": "game_stopped"})

        device_assignments = request.session.get('device_assignments', {})
        if not device_assignments:
             logger.warning(_("❌ Start fehlgeschlagen: Keine Zuweisungen in der Session gefunden."))
             return JsonResponse({"error": _("Keine Zuweisungen aktiv.")}, status=400) 

        device_names = device_assignments.keys()
        current_devices = Device.objects.filter(name__in=device_names).values('name', 'distance_total')
        start_distances = {device['name']: device['distance_total'] for device in current_devices}
        
        request.session['start_distances'] = start_distances
        request.session['is_game_stopped'] = False
        
        logger.info(_(f"✅ Spiel gestartet. Startdistanzen: {start_distances}"))
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