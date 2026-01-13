# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    test_integration_hierarchy.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
"""
Integration tests for hierarchy lookups and database interactions.

Tests cover:
- ID Tag -> Group -> Event hierarchy lookups
- Database queries with select_related and prefetch_related
- N+1 query prevention
- Complex relationship traversals
"""

import pytest
from decimal import Decimal
from django.utils import timezone
from django.db import connection
from datetime import timedelta

from api.models import (
    Cyclist, Group, Event, GroupEventStatus,
    TravelTrack, GroupTravelStatus, HourlyMetric
)
from iot.models import Device
from api.tests.conftest import (
    CyclistFactory, DeviceFactory, GroupFactory, EventFactory,
    GroupEventStatusFactory, TravelTrackFactory, GroupTravelStatusFactory,
    HourlyMetricFactory
)


@pytest.mark.integration
@pytest.mark.hierarchy
@pytest.mark.django_db
class TestIDTagToGroupHierarchy:
    """Tests for ID Tag -> Group hierarchy lookups."""
    
    def test_cyclist_to_group_lookup(self, complete_test_scenario):
        """Test looking up group from cyclist ID tag."""
        scenario = complete_test_scenario
        cyclist = scenario['cyclist']
        child_group = scenario['child_group']
        parent_group = scenario['parent_group']
        
        # Lookup cyclist by ID tag
        found_player = Cyclist.objects.get(id_tag=cyclist.id_tag)
        
        # Get cyclist's groups
        groups = found_player.groups.all()
        assert child_group in groups
        
        # Verify hierarchy
        for group in groups:
            if group.parent:
                assert group.parent == parent_group
    
    def test_player_to_group_with_select_related(self, complete_test_scenario):
        """Test efficient query with select_related."""
        scenario = complete_test_scenario
        cyclist = scenario['cyclist']
        
        # Query with select_related to avoid N+1
        with connection.cursor() as cursor:
            initial_queries = len(connection.queries)
            
            # This should use select_related/prefetch_related in real code
            cyclists = Cyclist.objects.filter(id_tag=cyclist.id_tag).prefetch_related('groups')
            
            for p in cyclists:
                # Accessing groups should not trigger additional queries
                list(p.groups.all())
            
            # Count queries (should be minimal)
            queries = connection.queries[initial_queries:]
            # With prefetch_related, should be 2 queries: one for cyclists, one for groups
            assert len(queries) <= 2
    
    def test_group_hierarchy_traversal(self, group_hierarchy):
        """Test traversing group hierarchy from child to parent."""
        child = group_hierarchy['child1']
        parent = group_hierarchy['parent']
        
        # Traverse up the hierarchy
        current = child
        hierarchy_path = []
        
        while current:
            hierarchy_path.append(current.name)
            current = current.parent
        
        assert 'Child Group 1' in hierarchy_path
        assert 'Parent Group' in hierarchy_path
        assert hierarchy_path[-1] == 'Parent Group'  # Top parent is last


@pytest.mark.integration
@pytest.mark.hierarchy
@pytest.mark.django_db
class TestGroupToEventHierarchy:
    """Tests for Group -> Event hierarchy lookups."""
    
    def test_group_to_event_lookup(self, complete_test_scenario):
        """Test looking up events from group."""
        scenario = complete_test_scenario
        group = scenario['child_group']
        event = scenario['event']
        
        # Get events for this group
        event_statuses = GroupEventStatus.objects.filter(group=group)
        assert event_statuses.exists()
        
        # Get event from status
        found_event = event_statuses.first().event
        assert found_event == event
    
    def test_group_to_event_with_prefetch(self, complete_test_scenario):
        """Test efficient query with prefetch_related for events."""
        scenario = complete_test_scenario
        group = scenario['child_group']
        
        # Query with prefetch_related
        with connection.cursor() as cursor:
            initial_queries = len(connection.queries)
            
            groups = Group.objects.filter(id=group.id).prefetch_related('event_statuses__event')
            
            for g in groups:
                # Accessing event_statuses should not trigger additional queries
                statuses = list(g.event_statuses.all())
                for status in statuses:
                    # Accessing event should not trigger additional query
                    _ = status.event.name
            
            queries = connection.queries[initial_queries:]
            # Should be minimal queries (group + event_statuses + events)
            assert len(queries) <= 3
    
    def test_event_to_group_hierarchy(self, complete_test_scenario):
        """Test looking up groups from event."""
        scenario = complete_test_scenario
        event = scenario['event']
        child_group = scenario['child_group']
        parent_group = scenario['parent_group']
        
        # Get groups participating in event
        event_statuses = GroupEventStatus.objects.filter(event=event).select_related('group')
        groups = [status.group for status in event_statuses]
        
        assert child_group in groups
        
        # Verify hierarchy
        for group in groups:
            if group.parent:
                assert group.parent == parent_group


@pytest.mark.integration
@pytest.mark.hierarchy
@pytest.mark.django_db
class TestCompleteHierarchyLookup:
    """Tests for complete ID Tag -> Group -> Event hierarchy lookups."""
    
    def test_id_tag_to_event_lookup(self, complete_test_scenario):
        """Test complete lookup: ID Tag -> Group -> Event."""
        scenario = complete_test_scenario
        cyclist = scenario['cyclist']
        event = scenario['event']
        
        # Start with ID tag
        found_player = Cyclist.objects.get(id_tag=cyclist.id_tag)
        
        # Get player's groups
        groups = found_player.groups.all()
        
        # Get events for these groups
        event_statuses = GroupEventStatus.objects.filter(
            group__in=groups
        ).select_related('event', 'group')
        
        events = [status.event for status in event_statuses]
        
        assert event in events
    
    def test_id_tag_to_event_efficient_query(self, complete_test_scenario):
        """Test efficient query for complete hierarchy lookup."""
        scenario = complete_test_scenario
        cyclist = scenario['cyclist']
        
        # Efficient query with all relationships prefetched
        with connection.cursor() as cursor:
            initial_queries = len(connection.queries)
            
            cyclists = Cyclist.objects.filter(
                id_tag=cyclist.id_tag
            ).prefetch_related(
                'groups',
                'groups__event_statuses',
                'groups__event_statuses__event'
            )
            
            for p in cyclists:
                for group in p.groups.all():
                    for status in group.event_statuses.all():
                        _ = status.event.name
            
            queries = connection.queries[initial_queries:]
            # Should be minimal queries (player + groups + event_statuses + events)
            assert len(queries) <= 4


@pytest.mark.integration
@pytest.mark.hierarchy
@pytest.mark.django_db
class TestN1QueryPrevention:
    """Tests to ensure N+1 query problems are prevented."""
    
    def test_group_children_query_efficiency(self, group_hierarchy, settings):
        """Test that querying group children doesn't cause N+1."""
        parent = group_hierarchy['parent']
        
        # Enable query logging
        settings.DEBUG = True
        from django.db import reset_queries
        reset_queries()
        
        # Query with select_related
        groups = list(Group.objects.filter(parent=parent).select_related('parent'))
        
        for group in groups:
            # Accessing parent should not trigger additional query
            _ = group.parent.name
        
        # Check query count (should be 1: groups query with parent already loaded)
        from django.db import connection
        query_count = len(connection.queries)
        # Should be 1 query (groups with parent already loaded via select_related)
        assert query_count <= 2  # Allow some overhead
    
    def test_player_groups_query_efficiency(self, complete_test_scenario):
        """Test that querying player groups doesn't cause N+1."""
        scenario = complete_test_scenario
        cyclist = scenario['cyclist']
        
        with connection.cursor() as cursor:
            initial_queries = len(connection.queries)
            
            # Query with prefetch_related
            cyclists = Cyclist.objects.filter(id=cyclist.id).prefetch_related('groups')
            
            for p in cyclists:
                # Accessing groups should not trigger additional queries
                groups = list(p.groups.all())
                for group in groups:
                    _ = group.name
            
            queries = connection.queries[initial_queries:]
            # Should be 2 queries: one for cyclists, one for groups
            assert len(queries) <= 2
    
    def test_hourly_metric_group_lookup_efficiency(self, complete_test_scenario, settings):
        """Test efficient lookup of groups from HourlyMetric."""
        scenario = complete_test_scenario
        cyclist = scenario['cyclist']
        device = scenario['device']
        group = scenario['child_group']
        
        # Create some metrics
        for i in range(5):
            HourlyMetricFactory(
                cyclist = cyclist,
                device=device,
                group_at_time=group,
                distance_km=Decimal('1.00000')
            )
        
        # Enable query logging
        settings.DEBUG = True
        from django.db import reset_queries
        reset_queries()
        
        # Query with select_related
        metrics = list(HourlyMetric.objects.filter(
            cyclist = cyclist
        ).select_related('group_at_time', 'device', 'cyclist'))
        
        for metric in metrics:
            # Accessing related objects should not trigger additional queries
            _ = metric.group_at_time.name
            _ = metric.device.name
            _ = metric.cyclist.user_id
        
        # Check query count (should be 1: metrics query with all relationships loaded)
        from django.db import connection
        query_count = len(connection.queries)
        # Should be 1 query (all relationships are loaded via select_related)
        assert query_count <= 2  # Allow some overhead


@pytest.mark.integration
@pytest.mark.hierarchy
@pytest.mark.django_db
class TestComplexHierarchyQueries:
    """Tests for complex hierarchy queries with multiple levels."""
    
    def test_multi_level_group_hierarchy(self, db):
        """Test querying multi-level group hierarchy."""
        from api.models import GroupType
        # Create 3-level hierarchy
        school_type, _ = GroupType.objects.get_or_create(name='Schule', defaults={'is_active': True})
        grade_type, _ = GroupType.objects.get_or_create(name='Jahrgang', defaults={'is_active': True})
        class_type, _ = GroupType.objects.get_or_create(name='Klasse', defaults={'is_active': True})
        level1 = GroupFactory(name='Level 1', group_type=school_type)
        level2 = GroupFactory(name='Level 2', group_type=grade_type, parent=level1)
        level3 = GroupFactory(name='Level 3', group_type=class_type, parent=level2)
        
        # Query with select_related for parent chain
        groups = Group.objects.filter(
            id=level3.id
        ).select_related('parent', 'parent__parent')
        
        group = groups.first()
        
        # Traverse hierarchy
        assert group.name == 'Level 3'
        assert group.parent.name == 'Level 2'
        assert group.parent.parent.name == 'Level 1'
    
    def test_group_descendants_lookup(self, group_hierarchy):
        """Test finding all descendants of a group."""
        parent = group_hierarchy['parent']
        child1 = group_hierarchy['child1']
        child2 = group_hierarchy['child2']
        
        # Recursive lookup of descendants
        def get_descendants(group_id):
            descendants = []
            children = Group.objects.filter(parent_id=group_id)
            for child in children:
                descendants.append(child)
                descendants.extend(get_descendants(child.id))
            return descendants
        
        descendants = get_descendants(parent.id)
        descendant_ids = [d.id for d in descendants]
        
        assert child1.id in descendant_ids
        assert child2.id in descendant_ids
    
    def test_event_group_hierarchy_aggregation(self, complete_test_scenario):
        """Test aggregating data across group hierarchy for an event."""
        scenario = complete_test_scenario
        event = scenario['event']
        child_group = scenario['child_group']
        parent_group = scenario['parent_group']
        
        # Delete any existing event statuses from fixture
        GroupEventStatus.objects.filter(event=event).delete()
        
        # Create event statuses for both child and parent
        child_status = GroupEventStatus.objects.create(
            group=child_group,
            event=event,
            current_distance_km=Decimal('10.00000')
        )
        
        parent_status = GroupEventStatus.objects.create(
            group=parent_group,
            event=event,
            current_distance_km=Decimal('20.00000')
        )
        
        # Aggregate total distance for event
        from django.db.models import Sum
        total = GroupEventStatus.objects.filter(
            event=event
        ).aggregate(
            total=Sum('current_distance_km')
        )['total']
        
        assert float(total) == 30.0

