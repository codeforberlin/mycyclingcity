# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    test_operator_permissions.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

"""
Tests for Operator role permissions and filtering.

Tests cover:
- Operator can only see/manage their assigned TOP-Groups and descendants
- Operator cannot see/manage other groups or related objects
- Operator cannot see hidden admin classes
- Recursive group filtering works correctly
"""

import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group as AuthGroup, Permission
from django.contrib.contenttypes.models import ContentType
from django.test import RequestFactory
from django.contrib.admin.sites import AdminSite

from api.models import (
    Group, Cyclist, TravelTrack, Milestone, GroupTravelStatus,
    TravelHistory, GroupMilestoneAchievement, GroupType
)
from eventboard.models import Event, EventHistory
from api.tests.conftest import (
    GroupFactory, CyclistFactory, TravelTrackFactory, MilestoneFactory,
    GroupTravelStatusFactory, EventFactory, GroupEventStatusFactory
)
from mgmt.admin import (
    GroupAdmin, CyclistAdmin, TravelTrackAdmin, MilestoneAdmin,
    GroupTravelStatusAdmin, TravelHistoryAdmin, GroupMilestoneAchievementAdmin,
    EventAdmin, EventHistoryAdmin, GroupTypeAdmin, CyclistDeviceCurrentMileageAdmin,
    HourlyMetricAdmin, get_operator_managed_group_ids
)

User = get_user_model()


@pytest.fixture
def operator_group(db):
    """Create Operator user group with permissions."""
    group, _ = AuthGroup.objects.get_or_create(name='Operatoren')
    
    # Assign permissions
    permissions = []
    for model in [Group, Cyclist, TravelTrack, Milestone, GroupTravelStatus, 
                  TravelHistory, GroupMilestoneAchievement, Event, EventHistory]:
        ct = ContentType.objects.get_for_model(model)
        if model == TravelHistory or model == EventHistory:
            # View only
            permissions.append(Permission.objects.get(codename='view_' + model.__name__.lower(), content_type=ct))
        elif model == GroupMilestoneAchievement:
            # View and change
            permissions.append(Permission.objects.get(codename='view_' + model.__name__.lower(), content_type=ct))
            permissions.append(Permission.objects.get(codename='change_' + model.__name__.lower(), content_type=ct))
        else:
            # Full permissions
            for action in ['add', 'change', 'delete', 'view']:
                permissions.append(Permission.objects.get(codename=f'{action}_{model.__name__.lower()}', content_type=ct))
    
    group.permissions.set(permissions)
    return group


@pytest.fixture
def operator_user(db, operator_group):
    """Create an operator user."""
    user = User.objects.create_user(
        username='operator1',
        email='operator1@test.com',
        password='testpass123',
        is_staff=True,
        is_superuser=False
    )
    user.groups.add(operator_group)
    return user


@pytest.fixture
def group_hierarchy_for_operator(db):
    """Create a group hierarchy for operator testing."""
    group_type = GroupType.objects.create(name='Schule', is_active=True)
    
    # TOP-Group (will be assigned to operator)
    top_group = GroupFactory(
        name='Schule A',
        group_type=group_type,
        parent=None,
        is_visible=True
    )
    
    # Sub-groups
    child1 = GroupFactory(
        name='Klasse 1a',
        group_type=group_type,
        parent=top_group,
        is_visible=True
    )
    
    child2 = GroupFactory(
        name='Klasse 1b',
        group_type=group_type,
        parent=top_group,
        is_visible=True
    )
    
    # Another TOP-Group (not assigned to operator)
    other_top_group = GroupFactory(
        name='Schule B',
        group_type=group_type,
        parent=None,
        is_visible=True
    )
    
    return {
        'top_group': top_group,
        'child1': child1,
        'child2': child2,
        'other_top_group': other_top_group,
    }


@pytest.mark.django_db
class TestOperatorPermissions:
    """Tests for Operator role permissions."""
    
    def test_operator_assigned_to_top_group(self, operator_user, group_hierarchy_for_operator):
        """Test that operator is assigned to a TOP-Group."""
        top_group = group_hierarchy_for_operator['top_group']
        top_group.managers.add(operator_user)
        
        assert operator_user in top_group.managers.all()
        assert operator_user.managed_groups.count() == 1
    
    def test_get_operator_managed_group_ids(self, operator_user, group_hierarchy_for_operator):
        """Test get_operator_managed_group_ids returns all descendant groups."""
        top_group = group_hierarchy_for_operator['top_group']
        child1 = group_hierarchy_for_operator['child1']
        child2 = group_hierarchy_for_operator['child2']
        other_top_group = group_hierarchy_for_operator['other_top_group']
        
        top_group.managers.add(operator_user)
        
        managed_ids = get_operator_managed_group_ids(operator_user)
        
        # Should include top_group and all children
        assert top_group.id in managed_ids
        assert child1.id in managed_ids
        assert child2.id in managed_ids
        # Should NOT include other_top_group
        assert other_top_group.id not in managed_ids
    
    def test_group_admin_filtering(self, operator_user, group_hierarchy_for_operator):
        """Test GroupAdmin filters groups for operators."""
        top_group = group_hierarchy_for_operator['top_group']
        child1 = group_hierarchy_for_operator['child1']
        other_top_group = group_hierarchy_for_operator['other_top_group']
        
        top_group.managers.add(operator_user)
        
        request = RequestFactory().get('/admin/api/group/')
        request.user = operator_user
        
        admin = GroupAdmin(Group, AdminSite())
        qs = admin.get_queryset(request)
        
        # Should see top_group and child1
        assert top_group in qs
        assert child1 in qs
        # Should NOT see other_top_group
        assert other_top_group not in qs
    
    def test_group_admin_permissions(self, operator_user, group_hierarchy_for_operator):
        """Test GroupAdmin permission methods."""
        top_group = group_hierarchy_for_operator['top_group']
        child1 = group_hierarchy_for_operator['child1']
        other_top_group = group_hierarchy_for_operator['other_top_group']
        
        top_group.managers.add(operator_user)
        
        request = RequestFactory().get('/admin/api/group/')
        request.user = operator_user
        
        admin = GroupAdmin(Group, AdminSite())
        
        # Can add groups
        assert admin.has_add_permission(request) is True
        
        # Can change managed groups
        assert admin.has_change_permission(request, top_group) is True
        assert admin.has_change_permission(request, child1) is True
        # Cannot change other groups
        assert admin.has_change_permission(request, other_top_group) is False
        
        # Can delete child groups
        assert admin.has_delete_permission(request, child1) is True
        # Cannot delete TOP-Group
        assert admin.has_delete_permission(request, top_group) is False
    
    def test_cyclist_admin_filtering(self, operator_user, group_hierarchy_for_operator):
        """Test CyclistAdmin filters cyclists for operators."""
        top_group = group_hierarchy_for_operator['top_group']
        child1 = group_hierarchy_for_operator['child1']
        other_top_group = group_hierarchy_for_operator['other_top_group']
        
        top_group.managers.add(operator_user)
        
        # Create cyclists
        cyclist1 = CyclistFactory()
        cyclist1.groups.add(child1)
        
        cyclist2 = CyclistFactory()
        cyclist2.groups.add(other_top_group)
        
        request = RequestFactory().get('/admin/api/cyclist/')
        request.user = operator_user
        
        admin = CyclistAdmin(Cyclist, AdminSite())
        qs = admin.get_queryset(request)
        
        # Should see cyclist1
        assert cyclist1 in qs
        # Should NOT see cyclist2
        assert cyclist2 not in qs
    
    def test_travel_track_admin_filtering(self, operator_user, group_hierarchy_for_operator):
        """Test TravelTrackAdmin filters tracks for operators."""
        top_group = group_hierarchy_for_operator['top_group']
        child1 = group_hierarchy_for_operator['child1']
        other_top_group = group_hierarchy_for_operator['other_top_group']
        
        top_group.managers.add(operator_user)
        
        # Create tracks
        track1 = TravelTrackFactory()
        status1 = GroupTravelStatusFactory(track=track1, group=child1)
        
        track2 = TravelTrackFactory()
        status2 = GroupTravelStatusFactory(track=track2, group=other_top_group)
        
        request = RequestFactory().get('/admin/api/traveltrack/')
        request.user = operator_user
        
        admin = TravelTrackAdmin(TravelTrack, AdminSite())
        qs = admin.get_queryset(request)
        
        # Should see track1
        assert track1 in qs
        # Should NOT see track2
        assert track2 not in qs
    
    def test_event_admin_filtering(self, operator_user, group_hierarchy_for_operator):
        """Test EventAdmin filters events for operators."""
        top_group = group_hierarchy_for_operator['top_group']
        child1 = group_hierarchy_for_operator['child1']
        other_top_group = group_hierarchy_for_operator['other_top_group']
        
        top_group.managers.add(operator_user)
        
        # Create events
        from eventboard.models import GroupEventStatus
        event1 = EventFactory()
        GroupEventStatusFactory(event=event1, group=child1)
        
        event2 = EventFactory()
        GroupEventStatusFactory(event=event2, group=other_top_group)
        
        request = RequestFactory().get('/admin/api/event/')
        request.user = operator_user
        
        admin = EventAdmin(Event, AdminSite())
        qs = admin.get_queryset(request)
        
        # Should see event1
        assert event1 in qs
        # Should NOT see event2
        assert event2 not in qs
    
    def test_hidden_admin_classes(self, operator_user):
        """Test that hidden admin classes are not visible to operators."""
        request = RequestFactory().get('/admin/api/grouptype/')
        request.user = operator_user
        
        admin = GroupTypeAdmin(GroupType, AdminSite())
        assert admin.has_module_permission(request) is False
        
        from api.models import CyclistDeviceCurrentMileage, HourlyMetric
        admin2 = CyclistDeviceCurrentMileageAdmin(CyclistDeviceCurrentMileage, AdminSite())
        assert admin2.has_module_permission(request) is False
        
        admin3 = HourlyMetricAdmin(HourlyMetric, AdminSite())
        assert admin3.has_module_permission(request) is False
