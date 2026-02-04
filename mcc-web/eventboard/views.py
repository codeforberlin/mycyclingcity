# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    views.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

from django.shortcuts import render
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from datetime import timedelta, datetime
from api.models import Event, GroupEventStatus, Group, Cyclist, CyclistDeviceCurrentMileage
from .utils import get_active_cyclists_for_eventboard, get_all_subgroup_ids
from decimal import Decimal
import json


def eventboard_page(request: HttpRequest) -> HttpResponse:
    """
    Eventboard-Seite - funktioniert sowohl als normale URL als auch in Kiosk-Modus.
    
    Query-Parameter:
    - event_id: Filter für spezifisches Event
    - group_filter_id: Filter für TOP-Gruppe
    - kiosk: Wird automatisch gesetzt, wenn über Kiosk-Playlist aufgerufen
    """
    event_id = request.GET.get('event_id')
    group_filter_id = request.GET.get('group_filter_id')
    
    # Prüfe, ob über Kiosk aufgerufen
    is_kiosk = (
        request.GET.get('kiosk') == 'true' or
        'kiosk/playlist' in request.META.get('HTTP_REFERER', '')
    )
    
    # Wenn keine Event-ID: Zeige Event-Auswahl
    if not event_id:
        from django.utils import timezone
        
        # Lade verfügbare Events
        available_events = Event.objects.filter(is_active=True).prefetch_related('group_statuses')
        
        # Filtere nach TOP-Gruppe, falls angegeben
        if group_filter_id:
            try:
                top_group = Group.objects.get(id=group_filter_id, parent__isnull=True)
                all_group_ids = get_all_subgroup_ids(top_group)
                # Nur Events, an denen Gruppen der TOP-Gruppe teilnehmen
                event_ids = GroupEventStatus.objects.filter(
                    group__id__in=all_group_ids
                ).values_list('event_id', flat=True).distinct()
                available_events = available_events.filter(id__in=event_ids)
            except Group.DoesNotExist:
                available_events = Event.objects.none()
        
        # Bereite Event-Daten für Auswahl vor
        now = timezone.now()
        active_cutoff = now - timedelta(seconds=60)
        events_data = []
        
        # Batch-Query: Hole alle aktiven Radler für alle Events auf einmal
        all_event_ids = list(available_events.values_list('id', flat=True))
        
        # Hole alle Gruppen, die an Events teilnehmen
        # WICHTIG: Wenn eine TOP-Gruppe am Event teilnimmt, müssen auch alle ihre Untergruppen berücksichtigt werden
        event_groups_map = {}
        if all_event_ids:
            event_groups = GroupEventStatus.objects.filter(
                event_id__in=all_event_ids
            ).select_related('group')
            
            for status in event_groups:
                event_id = status.event_id
                group = status.group
                
                if event_id not in event_groups_map:
                    event_groups_map[event_id] = []
                
                # Wenn es eine TOP-Gruppe ist, füge alle Untergruppen hinzu
                if group.parent is None:
                    # TOP-Gruppe: Hole alle Untergruppen
                    all_subgroup_ids = get_all_subgroup_ids(group)
                    all_subgroup_ids.append(group.id)  # Füge TOP-Gruppe selbst hinzu
                    event_groups_map[event_id].extend(all_subgroup_ids)
                else:
                    # Normale Gruppe: Prüfe, ob die TOP-Gruppe auch am Event teilnimmt
                    top_group = group
                    while top_group.parent:
                        top_group = top_group.parent
                    
                    # Wenn die TOP-Gruppe am Event teilnimmt, sind alle Untergruppen inkludiert
                    # Ansonsten füge nur diese Gruppe hinzu
                    top_group_in_event = GroupEventStatus.objects.filter(
                        event_id=event_id,
                        group=top_group
                    ).exists()
                    
                    if top_group_in_event:
                        # TOP-Gruppe ist im Event, alle Untergruppen sind bereits inkludiert
                        all_subgroup_ids = get_all_subgroup_ids(top_group)
                        all_subgroup_ids.append(top_group.id)
                        event_groups_map[event_id].extend(all_subgroup_ids)
                    else:
                        # Nur diese Gruppe hinzufügen
                        event_groups_map[event_id].append(group.id)
            
            # Entferne Duplikate
            for event_id in event_groups_map:
                event_groups_map[event_id] = list(set(event_groups_map[event_id]))
        
        # Hole alle aktiven Radler, die zu Event-Gruppen gehören
        active_cyclists_by_event = {}
        if event_groups_map:
            all_group_ids = set()
            for group_ids in event_groups_map.values():
                all_group_ids.update(group_ids)
            
            if all_group_ids:
                active_cyclists = Cyclist.objects.filter(
                    is_visible=True,
                    last_active__isnull=False,
                    last_active__gte=active_cutoff,
                    groups__id__in=all_group_ids
                ).prefetch_related('groups').distinct()
                
                # Gruppiere aktive Radler nach Event
                # Verwende ein Set, um Duplikate zu vermeiden
                for cyclist in active_cyclists:
                    cyclist_group_ids = set(cyclist.groups.values_list('id', flat=True))
                    for event_id, event_group_ids in event_groups_map.items():
                        # Prüfe, ob Radler zu mindestens einer Gruppe des Events gehört
                        if cyclist_group_ids & set(event_group_ids):
                            if event_id not in active_cyclists_by_event:
                                active_cyclists_by_event[event_id] = {}
                            # Verwende Dictionary mit cyclist.id als Key, um Duplikate zu vermeiden
                            active_cyclists_by_event[event_id][cyclist.id] = {
                                'id': cyclist.id,
                                'user_id': cyclist.user_id,
                            }
                
                # Konvertiere Dictionary-Values zu Listen
                for event_id in active_cyclists_by_event:
                    active_cyclists_by_event[event_id] = list(active_cyclists_by_event[event_id].values())
        
        for event in available_events:
            total_distance = float(event.get_total_distance_km())
            group_count = event.group_statuses.count()
            is_currently_active = event.is_currently_active()
            
            # Prüfe, ob Event aktive Radler hat
            active_cyclists_list = active_cyclists_by_event.get(event.id, [])
            active_cyclists_count = len(active_cyclists_list)
            
            # Live-Badge nur anzeigen, wenn Event aktuell aktiv ist UND aktive Radler hat
            has_active_cyclists = is_currently_active and active_cyclists_count > 0
            
            events_data.append({
                'id': event.id,
                'name': event.name,
                'event_type': event.get_event_type_display(),
                'event_type_code': event.event_type,
                'start_time': event.start_time,
                'end_time': event.end_time,
                'total_distance_km': total_distance,
                'group_count': group_count,
                'is_currently_active': is_currently_active,
                'has_active_cyclists': has_active_cyclists,
                'active_cyclists_count': active_cyclists_count if has_active_cyclists else 0,
                'description': event.description,
            })
        
        # Sortiere: Events mit aktiven Radlern zuerst, dann nach Aktivität und Zeit
        events_data.sort(key=lambda x: (
            not x['has_active_cyclists'],  # Events mit aktiven Radlern zuerst
            -x['active_cyclists_count'] if x['has_active_cyclists'] else 0,  # Mehr aktive Radler = höher
            not x['is_currently_active'],  # Aktive Events vor beendeten
            -(x['start_time'].timestamp() if x['start_time'] else 0)  # Neueste zuerst
        ), reverse=False)
        
        context = {
            'show_event_selection': True,
            'events': events_data,
            'group_filter_id': group_filter_id,
            'is_kiosk': is_kiosk,
        }
        return render(request, 'eventboard/eventboard_page.html', context)
    
    # Lade Event-Daten für spezifisches Event
    event = None
    groups_data = []
    statistics = {
        'total_distance_km': Decimal('0.00000'),
        'group_count': 0,
        'average_distance_km': Decimal('0.00000'),
    }
    
    if event_id:
        try:
            event = Event.objects.prefetch_related('group_statuses__group').get(id=event_id)
            
            # Lade Gruppen-Status für dieses Event
            group_statuses = GroupEventStatus.objects.filter(
                event=event
            ).select_related('group').order_by('-current_distance_km')
            
            # Filtere nach TOP-Gruppe, falls angegeben
            if group_filter_id:
                try:
                    top_group = Group.objects.get(id=group_filter_id, parent__isnull=True)
                    all_group_ids = get_all_subgroup_ids(top_group)
                    group_statuses = group_statuses.filter(group__id__in=all_group_ids)
                except Group.DoesNotExist:
                    pass
            
            # Bereite Gruppen-Daten vor
            for status in group_statuses:
                group = status.group
                groups_data.append({
                    'id': group.id,
                    'name': group.name,
                    'short_name': group.short_name,
                    'logo_url': group.logo.url if group.logo else None,
                    'color': group.color,
                    'current_distance_km': float(status.current_distance_km),
                    'group_type': group.group_type.name if group.group_type else None,
                })
            
            # Berechne Statistiken
            if groups_data:
                total = sum(g['current_distance_km'] for g in groups_data)
                statistics['total_distance_km'] = Decimal(str(total))
                statistics['group_count'] = len(groups_data)
                statistics['average_distance_km'] = Decimal(str(total / len(groups_data))) if groups_data else Decimal('0.00000')
                
                # Sortiere nach Distanz (absteigend)
                groups_data.sort(key=lambda x: x['current_distance_km'], reverse=True)
                
                # Füge Rang und Fortschritts-Prozentsatz hinzu
                for idx, group_data in enumerate(groups_data, start=1):
                    group_data['rank'] = idx
                    # Berechne Fortschritts-Prozentsatz für Fortschrittsbalken
                    if total > 0:
                        group_data['progress_percentage'] = (group_data['current_distance_km'] / total) * 100
                    else:
                        group_data['progress_percentage'] = 0.0
        except Event.DoesNotExist:
            event = None
    
    context = {
        'event': event,
        'groups': groups_data,
        'statistics': statistics,
        'event_id': event_id,
        'group_filter_id': group_filter_id,
        'is_kiosk': is_kiosk,
    }
    
    return render(request, 'eventboard/eventboard_page.html', context)


def eventboard_selection_api(request: HttpRequest) -> JsonResponse:
    """
    JSON API für Eventboard-Auswahlseite mit Live-Updates.
    Gibt alle Events mit aktualisierten Daten und aktiven Radlern zurück.
    """
    from django.utils import timezone
    from datetime import timedelta
    
    group_filter_id = request.GET.get('group_filter_id')
    
    # Lade verfügbare Events
    # WICHTIG: Kein prefetch_related verwenden, da wir get_total_distance_km() aufrufen,
    # das eine neue Datenbankabfrage macht. prefetch_related würde nur die bereits geladenen
    # Objekte verwenden, die möglicherweise veraltet sind.
    available_events = Event.objects.filter(is_active=True)
    
    # Filtere nach TOP-Gruppe, falls angegeben
    if group_filter_id:
        try:
            top_group = Group.objects.get(id=group_filter_id, parent__isnull=True)
            all_group_ids = get_all_subgroup_ids(top_group)
            # Nur Events, an denen Gruppen der TOP-Gruppe teilnehmen
            event_ids = GroupEventStatus.objects.filter(
                group__id__in=all_group_ids
            ).values_list('event_id', flat=True).distinct()
            available_events = available_events.filter(id__in=event_ids)
        except Group.DoesNotExist:
            available_events = Event.objects.none()
    
    # Bereite Event-Daten vor
    now = timezone.now()
    active_cutoff = now - timedelta(seconds=60)
    events_data = []
    
    # Batch-Query: Hole alle aktiven Radler für alle Events auf einmal
    # Prüfe für jedes Event, ob es aktive Radler hat
    all_event_ids = list(available_events.values_list('id', flat=True))
    
    # Hole alle Gruppen, die an Events teilnehmen
    # WICHTIG: Wenn eine TOP-Gruppe am Event teilnimmt, müssen auch alle ihre Untergruppen berücksichtigt werden
    event_groups_map = {}
    if all_event_ids:
        event_groups = GroupEventStatus.objects.filter(
            event_id__in=all_event_ids
        ).select_related('group')
        
        for status in event_groups:
            event_id = status.event_id
            group = status.group
            
            if event_id not in event_groups_map:
                event_groups_map[event_id] = []
            
            # Wenn es eine TOP-Gruppe ist, füge alle Untergruppen hinzu
            if group.parent is None:
                # TOP-Gruppe: Hole alle Untergruppen
                all_subgroup_ids = get_all_subgroup_ids(group)
                all_subgroup_ids.append(group.id)  # Füge TOP-Gruppe selbst hinzu
                event_groups_map[event_id].extend(all_subgroup_ids)
            else:
                # Normale Gruppe: Prüfe, ob die TOP-Gruppe auch am Event teilnimmt
                top_group = group
                while top_group.parent:
                    top_group = top_group.parent
                
                # Wenn die TOP-Gruppe am Event teilnimmt, sind alle Untergruppen inkludiert
                # Ansonsten füge nur diese Gruppe hinzu
                top_group_in_event = GroupEventStatus.objects.filter(
                    event_id=event_id,
                    group=top_group
                ).exists()
                
                if top_group_in_event:
                    # TOP-Gruppe ist im Event, alle Untergruppen sind bereits inkludiert
                    # Füge nur hinzu, wenn noch nicht vorhanden
                    all_subgroup_ids = get_all_subgroup_ids(top_group)
                    all_subgroup_ids.append(top_group.id)
                    event_groups_map[event_id].extend(all_subgroup_ids)
                else:
                    # Nur diese Gruppe hinzufügen
                    event_groups_map[event_id].append(group.id)
        
        # Entferne Duplikate
        for event_id in event_groups_map:
            event_groups_map[event_id] = list(set(event_groups_map[event_id]))
    
    # Hole alle aktiven Radler, die zu Event-Gruppen gehören
    active_cyclists_by_event = {}
    if event_groups_map:
        all_group_ids = set()
        for group_ids in event_groups_map.values():
            all_group_ids.update(group_ids)
        
        if all_group_ids:
            active_cyclists = Cyclist.objects.filter(
                is_visible=True,
                last_active__isnull=False,
                last_active__gte=active_cutoff,
                groups__id__in=all_group_ids
            ).prefetch_related('groups').distinct()
            
            # Gruppiere aktive Radler nach Event
            # Verwende ein Dictionary, um Duplikate zu vermeiden
            for cyclist in active_cyclists:
                cyclist_group_ids = set(cyclist.groups.values_list('id', flat=True))
                for event_id, event_group_ids in event_groups_map.items():
                    # Prüfe, ob Radler zu mindestens einer Gruppe des Events gehört
                    if cyclist_group_ids & set(event_group_ids):
                        if event_id not in active_cyclists_by_event:
                            active_cyclists_by_event[event_id] = {}
                        # Verwende Dictionary mit cyclist.id als Key, um Duplikate zu vermeiden
                        active_cyclists_by_event[event_id][cyclist.id] = {
                            'id': cyclist.id,
                            'user_id': cyclist.user_id,
                        }
            
            # Konvertiere Dictionary-Values zu Listen
            for event_id in active_cyclists_by_event:
                active_cyclists_by_event[event_id] = list(active_cyclists_by_event[event_id].values())
    
    # Erstelle Event-Daten mit aktiven Radlern
    # WICHTIG: Refresh jedes Event-Objekt von der Datenbank, um sicherzustellen,
    # dass wir die neuesten Daten haben (insbesondere für get_total_distance_km())
    for event in available_events:
        # Refresh event from database to ensure we have the latest data
        event.refresh_from_db()
        total_distance = float(event.get_total_distance_km())
        group_count = event.group_statuses.count()
        is_currently_active = event.is_currently_active()
        
        # Prüfe, ob Event aktive Radler hat
        active_cyclists_list = active_cyclists_by_event.get(event.id, [])
        active_cyclists_count = len(active_cyclists_list)
        
        # Live-Badge nur anzeigen, wenn Event aktuell aktiv ist UND aktive Radler hat
        has_active_cyclists = is_currently_active and active_cyclists_count > 0
        
        events_data.append({
            'id': event.id,
            'name': event.name,
            'event_type': event.get_event_type_display(),
            'event_type_code': event.event_type,
            'start_time': event.start_time.isoformat() if event.start_time else None,
            'end_time': event.end_time.isoformat() if event.end_time else None,
            'total_distance_km': total_distance,
            'group_count': group_count,
            'is_currently_active': is_currently_active,
            'has_active_cyclists': has_active_cyclists,
            'active_cyclists_count': active_cyclists_count if has_active_cyclists else 0,
            'description': event.description,
        })
    
    # Sortiere: Events mit aktiven Radlern zuerst, dann nach Aktivität und Zeit
    # start_time ist ein ISO-Format-String, daher müssen wir ihn zu einem Timestamp konvertieren
    # für die korrekte Sortierung (neueste zuerst = größerer Timestamp, daher negieren)
    events_data.sort(key=lambda x: (
        not x['has_active_cyclists'],  # Events mit aktiven Radlern zuerst (False < True)
        -x['active_cyclists_count'] if x['has_active_cyclists'] else 0,  # Mehr aktive Radler = höher
        not x['is_currently_active'],  # Aktive Events vor beendeten (False < True)
        # Für start_time: Konvertiere zu Timestamp für korrekte Sortierung (neueste zuerst = größerer Timestamp)
        -(datetime.fromisoformat(x['start_time'].replace('Z', '+00:00')).timestamp() if x['start_time'] else 0)
    ), reverse=False)
    
    return JsonResponse({
        'events': events_data,
        'last_update': now.isoformat(),
    })


def eventboard_api(request: HttpRequest) -> JsonResponse:
    """
    JSON API für Eventboard-Daten (für AJAX-Updates).
    Gleiche Parameter wie eventboard_page.
    """
    event_id = request.GET.get('event_id')
    group_filter_id = request.GET.get('group_filter_id')
    
    # Gleiche Logik wie eventboard_page, aber als JSON
    event_data = None
    groups_data = []
    statistics = {
        'total_distance_km': 0.0,
        'group_count': 0,
        'average_distance_km': 0.0,
    }
    
    if event_id:
        try:
            event = Event.objects.prefetch_related('group_statuses__group').get(id=event_id)
            
            group_statuses = GroupEventStatus.objects.filter(
                event=event
            ).select_related('group').order_by('-current_distance_km')
            
            if group_filter_id:
                try:
                    top_group = Group.objects.get(id=group_filter_id, parent__isnull=True)
                    all_group_ids = get_all_subgroup_ids(top_group)
                    group_statuses = group_statuses.filter(group__id__in=all_group_ids)
                except Group.DoesNotExist:
                    pass
            
            for status in group_statuses:
                group = status.group
                groups_data.append({
                    'id': group.id,
                    'name': group.name,
                    'short_name': group.short_name,
                    'logo_url': group.logo.url if group.logo else None,
                    'color': group.color,
                    'current_distance_km': float(status.current_distance_km),
                    'group_type': group.group_type.name if group.group_type else None,
                })
            
            if groups_data:
                total = sum(g['current_distance_km'] for g in groups_data)
                statistics['total_distance_km'] = total
                statistics['group_count'] = len(groups_data)
                statistics['average_distance_km'] = total / len(groups_data) if groups_data else 0.0
                
                groups_data.sort(key=lambda x: x['current_distance_km'], reverse=True)
                
                for idx, group_data in enumerate(groups_data, start=1):
                    group_data['rank'] = idx
                    # Berechne Fortschritts-Prozentsatz für Fortschrittsbalken
                    if total > 0:
                        group_data['progress_percentage'] = (group_data['current_distance_km'] / total) * 100
                    else:
                        group_data['progress_percentage'] = 0.0
            
            event_data = {
                'id': event.id,
                'name': event.name,
                'event_type': event.event_type,
                'description': event.description,
                'start_time': event.start_time.isoformat() if event.start_time else None,
                'end_time': event.end_time.isoformat() if event.end_time else None,
                'is_active': event.is_active,
            }
        except Event.DoesNotExist:
            pass
    
    return JsonResponse({
        'event': event_data,
        'groups': groups_data,
        'statistics': statistics,
    })


def eventboard_ticker(request: HttpRequest) -> HttpResponse:
    """
    Ticker-Endpoint für Activity Toasts im Eventboard.
    Filtert aktive Radler basierend auf Event und Gruppen-Filter.
    Verwendet die gleiche Logik wie Map und Leaderboard.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    from django.utils import timezone
    from datetime import timedelta
    
    event_id = request.GET.get('event_id')
    group_filter_id = request.GET.get('group_filter_id')
    
    now = timezone.now()
    active_cutoff = now - timedelta(seconds=60)
    
    logger.info(f"Eventboard ticker: event_id={event_id}, group_filter_id={group_filter_id}, active_cutoff={active_cutoff}")
    
    # Basis-Query: Sichtbare Radler mit aktiver Session (gleiche Logik wie Map/Leaderboard)
    # WICHTIG: Prüfe auch Radler ohne last_active (könnte None sein)
    base_cyclists = Cyclist.objects.filter(
        is_visible=True,
        last_active__isnull=False,
        last_active__gte=active_cutoff
    ).select_related('cyclistdevicecurrentmileage').prefetch_related('groups')
    
    base_count = base_cyclists.count()
    logger.info(f"Eventboard ticker: Base query found {base_count} cyclists")
    
    # Debug: Zeige Details der ersten 3 Radler
    if base_count > 0:
        for cyclist in base_cyclists[:3]:
            logger.info(f"  - Cyclist: {cyclist.user_id}, last_active={cyclist.last_active}, "
                        f"groups={[g.id for g in cyclist.groups.all()]}")
    else:
        # Prüfe, warum keine Radler gefunden wurden
        all_visible = Cyclist.objects.filter(is_visible=True).count()
        with_last_active = Cyclist.objects.filter(is_visible=True, last_active__isnull=False).count()
        recent_active = Cyclist.objects.filter(
            is_visible=True,
            last_active__isnull=False,
            last_active__gte=active_cutoff
        ).count()
        logger.warning(f"Eventboard ticker: NO ACTIVE CYCLISTS FOUND! visible={all_visible}, "
                      f"with_last_active={with_last_active}, recent_active={recent_active}")
    
    # Event-Filterung
    if event_id:
        try:
            event_id_int = int(event_id)
            # Prüfe, ob Event existiert
            try:
                event = Event.objects.get(id=event_id_int)
                logger.info(f"Eventboard ticker: Event {event_id_int} exists: {event.name}")
            except Event.DoesNotExist:
                logger.warning(f"Eventboard ticker: Event {event_id_int} does not exist")
                base_cyclists = Cyclist.objects.none()
            else:
                # Hole alle Gruppen, die am Event teilnehmen
                event_groups = GroupEventStatus.objects.filter(
                    event_id=event_id_int
                ).values_list('group_id', flat=True)
                
                logger.info(f"Eventboard ticker: Event {event_id_int} has {event_groups.count()} groups")
                
                # Filtere Radler, die zu diesen Gruppen gehören
                # WICHTIG: Berücksichtige auch Untergruppen der Event-Gruppen
                if event_groups.exists():
                    event_group_list = list(event_groups)
                    logger.info(f"Eventboard ticker: Event groups: {event_group_list}")
                    
                    # Hole alle Untergruppen der Event-Gruppen rekursiv
                    all_event_group_ids = set(event_group_list)
                    for event_group_id in event_group_list:
                        try:
                            event_group = Group.objects.get(id=event_group_id)
                            # Hole alle Untergruppen dieser Event-Gruppe
                            subgroup_ids = get_all_subgroup_ids(event_group)
                            all_event_group_ids.update(subgroup_ids)
                            all_event_group_ids.add(event_group_id)  # Include the group itself
                        except Group.DoesNotExist:
                            pass
                    
                    all_event_group_ids = list(all_event_group_ids)
                    logger.info(f"Eventboard ticker: Event groups (including subgroups): {all_event_group_ids}")
                    
                    before_filter_count = base_cyclists.count()
                    base_cyclists = base_cyclists.filter(groups__id__in=all_event_group_ids).distinct()
                    after_filter_count = base_cyclists.count()
                    logger.info(f"Eventboard ticker: After event filter: {before_filter_count} -> {after_filter_count} cyclists")
                    
                    # Debug: Zeige welche Radler-Gruppen vorhanden sind
                    if before_filter_count > 0 and after_filter_count == 0:
                        logger.warning(f"Eventboard ticker: WARNING - Event filter excluded all cyclists!")
                        sample_cyclists = Cyclist.objects.filter(
                            is_visible=True,
                            last_active__isnull=False,
                            last_active__gte=active_cutoff
                        )[:3]
                        for cyclist in sample_cyclists:
                            cyclist_groups = list(cyclist.groups.values_list('id', flat=True))
                            logger.warning(f"  - Sample cyclist {cyclist.user_id} groups: {cyclist_groups}")
                else:
                    # Keine Gruppen am Event -> zeige alle aktiven Radler (keine Filterung)
                    logger.info(f"Eventboard ticker: No groups in event, showing all active cyclists (no event filter)")
                    # base_cyclists bleibt unverändert (alle aktiven Radler)
        except (ValueError, TypeError) as e:
            # Ungültige event_id -> keine Radler
            logger.warning(f"Eventboard ticker: Invalid event_id={event_id}: {e}")
            base_cyclists = Cyclist.objects.none()
    
    # TOP-Gruppen-Filterung
    if group_filter_id:
        try:
            group_filter_id_int = int(group_filter_id)
            top_group = Group.objects.get(id=group_filter_id_int, parent__isnull=True)
            all_group_ids = get_all_subgroup_ids(top_group)
            all_group_ids.append(top_group.id)  # Include the top group itself
            
            # Filtere Radler, die zu diesen Gruppen gehören
            base_cyclists = base_cyclists.filter(groups__id__in=all_group_ids).distinct()
        except (ValueError, TypeError, Group.DoesNotExist):
            # Ungültige group_filter_id oder Gruppe nicht gefunden -> keine Radler
            base_cyclists = Cyclist.objects.none()
    
    # Bereite Ticker-Daten vor (gleiche Logik wie Map/Leaderboard)
    final_count = base_cyclists.count()
    logger.info(f"Eventboard ticker: Processing {final_count} cyclists")
    ticker_data = []
    for cyclist in base_cyclists.order_by('-last_active'):
        # Get session kilometers from CyclistDeviceCurrentMileage (gleiche Logik wie Map/Leaderboard)
        session_km = 0.0
        try:
            mileage_obj = cyclist.cyclistdevicecurrentmileage
            if mileage_obj and mileage_obj.cumulative_mileage is not None:
                session_km = float(mileage_obj.cumulative_mileage)
        except (AttributeError, CyclistDeviceCurrentMileage.DoesNotExist):
            session_km = 0.0
        
        # Get primary group's short name (gleiche Logik wie Map/Leaderboard)
        group_short_name = ''
        primary_group = cyclist.groups.filter(is_visible=True).first()
        if not primary_group:
            primary_group = cyclist.groups.first()
        
        if primary_group:
            try:
                # Verwende get_kiosk_label() wie in Map/Leaderboard
                group_short_name = primary_group.get_kiosk_label()
            except (RecursionError, AttributeError, RuntimeError):
                # Fallback zu short_name oder name
                group_short_name = primary_group.short_name or primary_group.name
        
        # Always include cyclist, even if session_km is 0 (gleiche Logik wie Map)
        ticker_data.append({
            'id': cyclist.id,
            'user_id': cyclist.user_id,
            'group_short_name': group_short_name,
            'session_km': session_km,
            'last_active': cyclist.last_active.isoformat() if cyclist.last_active else None,
        })
    
    # Sortiere nach Session-Kilometern (absteigend) - gleiche Logik wie Map/Leaderboard
    ticker_data.sort(key=lambda x: x['session_km'], reverse=True)
    
    logger.info(f"Eventboard ticker: Returning {len(ticker_data)} active cyclists")
    if len(ticker_data) > 0:
        logger.info(f"Eventboard ticker: First cyclist: {ticker_data[0]}")
    else:
        logger.warning(f"Eventboard ticker: NO CYCLISTS RETURNED! Check filters and active cyclists.")
    
    # Serialisiere als JSON-String, um Locale-Probleme zu vermeiden (z.B. Komma statt Punkt bei Zahlen)
    active_cyclists_json = json.dumps(ticker_data, ensure_ascii=False)
    
    return render(request, 'eventboard/partials/ticker.html', {
        'active_cyclists': ticker_data,
        'active_cyclists_json': active_cyclists_json,
        'event_id': event_id,
        'group_filter_id': group_filter_id,
    })
