# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    conftest.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
"""
Shared pytest fixtures and factory definitions for MCC-Web test suite.

This module provides:
- Factory classes for all models using factory_boy
- Shared fixtures for common test scenarios
- Test data helpers
"""

import pytest
import factory
import os
from decimal import Decimal
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth import get_user_model

from api.models import (
    Group, Cyclist, GroupType, HourlyMetric, CyclistDeviceCurrentMileage,
    TravelTrack, Milestone, GroupTravelStatus, Event, GroupEventStatus,
    EventHistory, TravelHistory
)
from iot.models import Device, DeviceConfiguration
from kiosk.models import KioskDevice, KioskPlaylistEntry

User = get_user_model()


# ============================================================================
# Factory Classes
# ============================================================================

class UserFactory(factory.django.DjangoModelFactory):
    """Factory for Django User model."""
    class Meta:
        model = User
        django_get_or_create = ('username',)
    
    username = factory.Sequence(lambda n: f'testuser{n}')
    email = factory.LazyAttribute(lambda obj: f'{obj.username}@example.com')
    password = factory.PostGenerationMethodCall('set_password', 'testpass123')


class GroupFactory(factory.django.DjangoModelFactory):
    """Factory for Group model."""
    class Meta:
        model = Group
        django_get_or_create = ('name', 'group_type')
    
    group_type = factory.LazyFunction(lambda: GroupType.objects.get_or_create(name='TestType', defaults={'is_active': True})[0])
    name = factory.Sequence(lambda n: f'Group{n}')
    distance_total = Decimal('0.00000')
    coins_total = 0
    is_visible = True
    short_name = None
    color = None


class CyclistFactory(factory.django.DjangoModelFactory):
    """Factory for Cyclist model."""
    class Meta:
        model = Cyclist
        django_get_or_create = ('id_tag',)
    
    user_id = factory.Sequence(lambda n: f'cyclist{n}')
    id_tag = factory.Sequence(lambda n: f'tag-{n:04d}')
    mc_username = factory.LazyAttribute(lambda obj: f'mc_{obj.user_id}')
    distance_total = Decimal('0.00000')
    coins_total = 0
    coins_spendable = 0
    coin_conversion_factor = 100.0
    is_visible = True
    is_km_collection_enabled = True
    last_active = None


class DeviceFactory(factory.django.DjangoModelFactory):
    """Factory for Device model."""
    class Meta:
        model = Device
        django_get_or_create = ('name',)
    
    name = factory.Sequence(lambda n: f'device{n}')
    display_name = factory.LazyAttribute(lambda obj: f'Device {obj.name}')
    distance_total = Decimal('0.00000')
    is_visible = True
    is_km_collection_enabled = True
    last_active = None
    last_reported_interval = Decimal('0.000')
    last_reported_at = None
    
    @factory.post_generation
    def create_configuration(self, create, extracted, **kwargs):
        """Automatically create DeviceConfiguration with generated API key."""
        if not create:
            return
        
        # Create DeviceConfiguration if it doesn't exist
        config, created = DeviceConfiguration.objects.get_or_create(
            device=self,
            defaults={
                'device_name': self.name,
                'default_id_tag': '',
                'send_interval_seconds': 60,
                'debug_mode': False,
                'test_mode': False,
                'deep_sleep_seconds': 0,
                'wheel_size': 2075.0,  # 26 Zoll = 2075 mm
            }
        )
        
        # Generate API key if not already set
        if not config.device_specific_api_key:
            config.generate_api_key()


class TravelTrackFactory(factory.django.DjangoModelFactory):
    """Factory for TravelTrack model."""
    class Meta:
        model = TravelTrack
        django_get_or_create = ('name',)
    
    name = factory.Sequence(lambda n: f'Track{n}')
    total_length_km = Decimal('100.00000')
    is_active = True
    is_visible_on_map = True
    start_time = None
    end_time = None


class EventFactory(factory.django.DjangoModelFactory):
    """Factory for Event model."""
    class Meta:
        model = Event
        django_get_or_create = ('name',)
    
    name = factory.Sequence(lambda n: f'Event{n}')
    event_type = 'competition'
    description = factory.LazyAttribute(lambda obj: f'Description for {obj.name}')
    is_active = True
    is_visible_on_map = True
    start_time = None
    end_time = None
    hide_after_date = None


class MilestoneFactory(factory.django.DjangoModelFactory):
    """Factory for Milestone model."""
    class Meta:
        model = Milestone
    
    track = factory.SubFactory(TravelTrackFactory)
    name = factory.Sequence(lambda n: f'Milestone{n}')
    description = factory.LazyAttribute(lambda obj: f'Description for {obj.name}')
    distance_km = factory.Sequence(lambda n: Decimal(str(n * 10)))
    gps_latitude = Decimal('52.5200')
    gps_longitude = Decimal('13.4050')
    reward_text = None
    winner_group = None
    reached_at = None


class GroupTravelStatusFactory(factory.django.DjangoModelFactory):
    """Factory for GroupTravelStatus model."""
    class Meta:
        model = GroupTravelStatus
        django_get_or_create = ('group',)
    
    group = factory.SubFactory(GroupFactory)
    track = factory.SubFactory(TravelTrackFactory)
    current_travel_distance = Decimal('0.00000')
    start_km_offset = Decimal('0.00000')


class GroupEventStatusFactory(factory.django.DjangoModelFactory):
    """Factory for GroupEventStatus model."""
    class Meta:
        model = GroupEventStatus
        django_get_or_create = ('group', 'event')
    
    group = factory.SubFactory(GroupFactory)
    event = factory.SubFactory(EventFactory)
    current_distance_km = Decimal('0.00000')
    start_km_offset = Decimal('0.00000')


class HourlyMetricFactory(factory.django.DjangoModelFactory):
    """Factory for HourlyMetric model."""
    class Meta:
        model = HourlyMetric
    
    device = factory.SubFactory(DeviceFactory)
    cyclist = factory.SubFactory(CyclistFactory)
    timestamp = factory.LazyFunction(lambda: timezone.now().replace(minute=0, second=0, microsecond=0))
    distance_km = Decimal('1.00000')
    group_at_time = factory.SubFactory(GroupFactory)


class CyclistDeviceCurrentMileageFactory(factory.django.DjangoModelFactory):
    """Factory for CyclistDeviceCurrentMileage model."""
    class Meta:
        model = CyclistDeviceCurrentMileage
        django_get_or_create = ('cyclist',)
    
    cyclist = factory.SubFactory(CyclistFactory)
    device = factory.SubFactory(DeviceFactory)
    cumulative_mileage = Decimal('0.00000')
    start_time = factory.LazyFunction(timezone.now)
    last_activity = factory.LazyFunction(timezone.now)


class KioskDeviceFactory(factory.django.DjangoModelFactory):
    """Factory for KioskDevice model."""
    class Meta:
        model = KioskDevice
        django_get_or_create = ('uid',)
    
    name = factory.Sequence(lambda n: f'Kiosk Device {n}')
    uid = factory.Sequence(lambda n: f'kiosk-{n:04d}')
    brightness = 100
    is_active = True
    command_queue = factory.LazyFunction(list)


class KioskPlaylistEntryFactory(factory.django.DjangoModelFactory):
    """Factory for KioskPlaylistEntry model."""
    class Meta:
        model = KioskPlaylistEntry
    
    device = factory.SubFactory(KioskDeviceFactory)
    view_type = 'leaderboard'
    event_filter = None
    group_filter = None
    display_duration = 30
    order = factory.Sequence(lambda n: n)
    is_active = True


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def api_key(settings):
    """Fixture providing the API key for testing."""
    api_key = 'TEST-API-KEY-12345'
    settings.MCC_APP_API_KEY = api_key
    return api_key


@pytest.fixture
def admin_user(db):
    """Fixture creating an admin user."""
    return UserFactory(username='admin', is_superuser=True, is_staff=True)


@pytest.fixture
def group_hierarchy(db):
    """Fixture creating a simple group hierarchy for testing."""
    school_type, _ = GroupType.objects.get_or_create(name='Schule', defaults={'is_active': True})
    class_type, _ = GroupType.objects.get_or_create(name='Klasse', defaults={'is_active': True})
    parent = GroupFactory(name='Parent Group', group_type=school_type)
    child1 = GroupFactory(name='Child Group 1', group_type=class_type, parent=parent)
    child2 = GroupFactory(name='Child Group 2', group_type=class_type, parent=parent)
    return {
        'parent': parent,
        'child1': child1,
        'child2': child2,
    }


@pytest.fixture
def cyclist_with_group(db):
    """Fixture creating a cyclist with a group."""
    group = GroupFactory()
    cyclist = CyclistFactory()
    cyclist.groups.add(group)
    return {
        'cyclist': cyclist,
        'group': group,
    }


@pytest.fixture
def device_with_group(db):
    """Fixture creating a device with a group."""
    group = GroupFactory()
    device = DeviceFactory(group=group)
    return {
        'device': device,
        'group': group,
    }


@pytest.fixture
def active_travel_track(db):
    """Fixture creating an active travel track with milestones."""
    track = TravelTrackFactory(
        name='Test Track',
        total_length_km=Decimal('100.00000'),
        is_active=True,
        start_time=timezone.now() - timedelta(days=1),
        end_time=timezone.now() + timedelta(days=1)
    )
    # Create some milestones
    MilestoneFactory(track=track, distance_km=Decimal('25.00000'), name='Milestone 1')
    MilestoneFactory(track=track, distance_km=Decimal('50.00000'), name='Milestone 2')
    MilestoneFactory(track=track, distance_km=Decimal('75.00000'), name='Milestone 3')
    return track


@pytest.fixture
def active_event(db):
    """Fixture creating an active event."""
    return EventFactory(
        name='Test Event',
        is_active=True,
        start_time=timezone.now() - timedelta(days=1),
        end_time=timezone.now() + timedelta(days=1)
    )


@pytest.fixture
def complete_test_scenario(db):
    """Fixture creating a complete test scenario with all entities."""
    # Create hierarchy
    school_type, _ = GroupType.objects.get_or_create(name='Schule', defaults={'is_active': True})
    class_type, _ = GroupType.objects.get_or_create(name='Klasse', defaults={'is_active': True})
    parent_group = GroupFactory(name='School A', group_type=school_type)
    child_group = GroupFactory(name='Class 1a', group_type=class_type, parent=parent_group)
    
    # Create cyclist and device
    cyclist = CyclistFactory(user_id='testcyclist', id_tag='test-tag-001')
    cyclist.groups.add(child_group)
    
    device = DeviceFactory(name='test-device-01', group=child_group)
    
    # Create travel track
    track = TravelTrackFactory(name='Test Track', total_length_km=Decimal('100.00000'))
    GroupTravelStatusFactory(group=child_group, track=track)
    
    # Create event
    event = EventFactory(name='Test Event')
    GroupEventStatusFactory(group=child_group, event=event)
    
    return {
        'parent_group': parent_group,
        'child_group': child_group,
        'cyclist': cyclist,
        'device': device,
        'track': track,
        'event': event,
    }


@pytest.fixture
def midnight_time():
    """Fixture providing a datetime at midnight for testing date boundaries."""
    now = timezone.now()
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


@pytest.fixture
def today_start():
    """Fixture providing the start of today (00:00:00)."""
    now = timezone.now()
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


@pytest.fixture
def yesterday_start(today_start):
    """Fixture providing the start of yesterday."""
    return today_start - timedelta(days=1)


@pytest.fixture
def tomorrow_start(today_start):
    """Fixture providing the start of tomorrow."""
    return today_start + timedelta(days=1)


# ============================================================================
# Pytest Configuration for Live API Tests
# ============================================================================

def pytest_addoption(parser):
    """Add command-line options for live API tests."""
    DEFAULT_BASE_URL = os.getenv('TEST_BASE_URL', 'http://127.0.0.1:8000')
    DEFAULT_API_KEY = os.getenv('TEST_API_KEY', 'MCC-APP-API-KEY-SECRET')
    
    parser.addoption(
        '--base-url',
        action='store',
        default=DEFAULT_BASE_URL,
        help='Base URL for live API tests (default: http://127.0.0.1:8000)'
    )
    parser.addoption(
        '--api-key',
        action='store',
        default=DEFAULT_API_KEY,
        help='API key for authentication'
    )

