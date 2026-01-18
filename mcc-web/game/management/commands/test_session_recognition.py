# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    test_session_recognition.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
from django.core.management.base import BaseCommand
from django.contrib.sessions.models import Session
from django.utils import timezone
from game.session_admin import decode_session_data, is_game_session
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Test session recognition for game sessions'

    def add_arguments(self, parser):
        parser.add_argument(
            '--session-key',
            type=str,
            help='Test a specific session key',
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Test all active sessions',
        )

    def handle(self, *args, **options):
        now = timezone.now()
        
        if options['session_key']:
            # Test specific session
            try:
                session = Session.objects.get(session_key=options['session_key'])
                self.test_session(session, now)
            except Session.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"Session {options['session_key']} not found"))
        elif options['all']:
            # Test all active sessions
            sessions = Session.objects.filter(expire_date__gt=now)
            self.stdout.write(self.style.NOTICE(f"Testing {sessions.count()} active sessions..."))
            game_sessions = []
            for session in sessions:
                if self.test_session(session, now):
                    game_sessions.append(session)
            
            self.stdout.write(self.style.SUCCESS(f"\nFound {len(game_sessions)} game sessions:"))
            for session in game_sessions:
                self.stdout.write(f"  - {session.session_key}")
        else:
            # Test recent sessions (last 10)
            sessions = Session.objects.filter(expire_date__gt=now).order_by('-expire_date')[:10]
            self.stdout.write(self.style.NOTICE(f"Testing last 10 active sessions..."))
            for session in sessions:
                self.test_session(session, now)

    def test_session(self, session, now):
        """Test if a session is recognized as a game session."""
        self.stdout.write(f"\n--- Testing Session: {session.session_key[:20]}... ---")
        self.stdout.write(f"Expire Date: {session.expire_date}")
        self.stdout.write(f"Is Expired: {session.expire_date <= now}")
        
        # Decode session data
        session_dict = decode_session_data(session.session_data)
        self.stdout.write(f"Session Keys: {list(session_dict.keys())}")
        
        # Check specific game-related keys
        device_assignments = session_dict.get('device_assignments', {})
        room_code = session_dict.get('room_code')
        is_master = session_dict.get('is_master', False)
        target_km = session_dict.get('current_target_km', 0.0)
        
        self.stdout.write(f"  - device_assignments: {device_assignments} (type: {type(device_assignments)}, len: {len(device_assignments) if isinstance(device_assignments, dict) else 'N/A'})")
        self.stdout.write(f"  - room_code: {room_code}")
        self.stdout.write(f"  - is_master: {is_master}")
        self.stdout.write(f"  - current_target_km: {target_km}")
        
        # Test recognition
        is_game = is_game_session(session)
        if is_game:
            self.stdout.write(self.style.SUCCESS(f"✅ Recognized as GAME SESSION"))
        else:
            self.stdout.write(self.style.WARNING(f"❌ NOT recognized as game session"))
        
        return is_game
