# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    signals.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
"""
Django signals for the game app.

This module handles automatic tracking of game sessions in the database.
"""
from django.db.models.signals import post_save
from django.contrib.sessions.models import Session
from django.dispatch import receiver
from .models import GameSession
from .session_admin import decode_session_data, is_game_session
import logging

logger = logging.getLogger(__name__)


def update_game_session(session_key, session_data=None):
    """
    Update or create a GameSession record based on session data.
    
    This function can be called from views when session data changes,
    or from signals when sessions are saved.
    
    Args:
        session_key: The Django session key
        session_data: Optional session data (if None, will be fetched from Session model)
    """
    if not session_key:
        return
    
    try:
        # If session_data is not provided, fetch it from the Session model
        if session_data is None:
            try:
                session = Session.objects.get(session_key=session_key)
                session_data = session.session_data
            except Session.DoesNotExist:
                # Session doesn't exist, delete GameSession if it exists
                GameSession.objects.filter(session_key=session_key).delete()
                return
        
        # Decode session data
        session_dict = decode_session_data(session_data)
        
        # Check if this is a game session
        if not is_game_session_from_dict(session_dict):
            # Not a game session, delete GameSession if it exists
            GameSession.objects.filter(session_key=session_key).delete()
            return
        
        # Extract game session data
        room_code = session_dict.get('room_code') or None
        is_master = session_dict.get('is_master', False)
        device_assignments = session_dict.get('device_assignments', {})
        has_assignments = isinstance(device_assignments, dict) and len(device_assignments) > 0
        target_km = session_dict.get('current_target_km', 0.0)
        has_target_km = 'current_target_km' in session_dict and target_km and target_km > 0
        
        # Update or create GameSession
        GameSession.objects.update_or_create(
            session_key=session_key,
            defaults={
                'room_code': room_code,
                'is_master': is_master,
                'has_assignments': has_assignments,
                'has_target_km': has_target_km,
            }
        )
        logger.debug(f"✅ Updated GameSession for session_key={session_key[:10]}...")
    except Exception as e:
        logger.error(f"Error updating GameSession for session_key={session_key[:10]}...: {e}", exc_info=True)


def is_game_session_from_dict(session_dict):
    """
    Check if a session dictionary represents a game session.
    
    This is a simplified version of is_game_session that works with
    already-decoded session data.
    """
    # 1. User is in a room
    has_room_code = 'room_code' in session_dict and session_dict.get('room_code')
    
    # 2. User has device assignments
    device_assignments = session_dict.get('device_assignments', {})
    has_assignments = isinstance(device_assignments, dict) and len(device_assignments) > 0
    
    # 3. User is a master
    has_master = 'is_master' in session_dict and session_dict.get('is_master')
    
    # 4. User has set a target
    target_km = session_dict.get('current_target_km', 0.0)
    has_target_km = 'current_target_km' in session_dict and target_km and target_km > 0
    
    return has_room_code or has_assignments or has_master or has_target_km


@receiver(post_save, sender=Session)
def session_saved(sender, instance, **kwargs):
    """
    Signal handler that updates GameSession when a Session is saved.
    
    Note: This only works if the session data is already updated.
    For immediate updates, call update_game_session() directly from views.
    """
    # Only update if session has data (not empty)
    if instance.session_data:
        try:
            update_game_session(instance.session_key, instance.session_data)
        except Exception as e:
            logger.debug(f"Could not update GameSession from signal: {e}")
