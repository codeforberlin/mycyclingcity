# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from decimal import Decimal

import pytest

from api.models import GroupTravelStatus, LeafGroupTravelContribution, update_group_hierarchy_progress
from api.tests.conftest import GroupFactory, TravelTrackFactory
from api.travel_velos import (
    build_travel_status_avatar_fields,
    get_track_goal_velos,
    travel_progress_ratio,
    velos_progress_to_km,
)
from api.velos import track_reference_velos


class TestTravelVelosHelpers:
    def test_track_reference_velos_for_10km(self):
        assert track_reference_velos(10) == 1000

    def test_travel_progress_ratio_caps_at_one(self):
        assert travel_progress_ratio(1500, 1000) == 1.0
        assert travel_progress_ratio(500, 1000) == 0.5

    def test_velos_progress_to_km(self):
        assert velos_progress_to_km(500, 1000, 200) == 100.0


@pytest.mark.django_db
class TestTravelVelosProgress:
    def test_update_group_hierarchy_progress_adds_velos_not_km(self):
        group = GroupFactory()
        travel_track = TravelTrackFactory(
            total_length_km=Decimal('100.00000'),
            is_active=True,
            start_time=None,
            end_time=None,
        )
        travel_track.goal_velos = track_reference_velos(travel_track.total_length_km)
        travel_track.save()

        GroupTravelStatus.objects.create(
            group=group,
            track=travel_track,
            current_travel_velos=0,
            current_travel_distance=Decimal('0.00000'),
        )

        update_group_hierarchy_progress(group, Decimal('5.00000'), 650)

        status = GroupTravelStatus.objects.get(group=group)
        assert status.current_travel_velos == 650
        assert status.current_travel_distance == Decimal(
            str(velos_progress_to_km(
                650,
                get_track_goal_velos(travel_track),
                travel_track.total_length_km,
            ))
        )

    def test_operator_velos_zero_skips_travel_progress(self):
        group = GroupFactory()
        travel_track = TravelTrackFactory(
            total_length_km=Decimal('50.00000'),
            is_active=True,
            start_time=None,
            end_time=None,
        )
        travel_track.goal_velos = track_reference_velos(travel_track.total_length_km)
        travel_track.save()

        GroupTravelStatus.objects.create(group=group, track=travel_track)

        update_group_hierarchy_progress(group, Decimal('2.00000'), 0)

        status = GroupTravelStatus.objects.get(group=group)
        assert status.current_travel_velos == 0

    def test_leaf_contribution_tracks_velos(self):
        group = GroupFactory()
        leaf_group = GroupFactory(parent=group)

        travel_track = TravelTrackFactory(
            total_length_km=Decimal('80.00000'),
            is_active=True,
            start_time=None,
            end_time=None,
        )
        travel_track.goal_velos = track_reference_velos(travel_track.total_length_km)
        travel_track.save()

        GroupTravelStatus.objects.create(group=group, track=travel_track)

        update_group_hierarchy_progress(leaf_group, Decimal('3.00000'), 400)

        contribution = LeafGroupTravelContribution.objects.get(
            leaf_group=leaf_group,
            track=travel_track,
        )
        assert contribution.current_travel_velos == 400

    def test_avatar_payload_includes_progress_ratio(self):
        group = GroupFactory()
        travel_track = TravelTrackFactory(total_length_km=Decimal('100.00000'))
        travel_track.goal_velos = 10000
        travel_track.save()

        status = GroupTravelStatus.objects.create(
            group=group,
            track=travel_track,
        )
        GroupTravelStatus.objects.filter(pk=status.pk).update(
            current_travel_velos=2500,
            current_travel_distance=Decimal('25.00000'),
        )
        status.refresh_from_db()

        payload = build_travel_status_avatar_fields(status)
        assert payload['velos'] == 2500
        assert payload['goal_velos'] == 10000
        assert payload['progress_ratio'] == 0.25
        assert payload['km'] == 25.0
