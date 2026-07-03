# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Travel progress based on earned Velos (fair across wheel sizes).

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Optional, Union

from api.velos import track_reference_velos


def get_track_goal_velos(track) -> int:
    """Velos required to complete a travel track (29\" reference, no device bonus)."""
    if track is None:
        return 0
    cached = getattr(track, 'goal_velos', None)
    if cached and int(cached) > 0:
        return int(cached)
    if track.total_length_km:
        return track_reference_velos(track.total_length_km)
    return 0


def get_milestone_position_velos(milestone) -> int:
    """Velos threshold for a milestone on a travel track."""
    if milestone is None:
        return 0
    cached = getattr(milestone, 'position_velos', None)
    if cached and int(cached) > 0:
        return int(cached)
    return track_reference_velos(milestone.distance_km)


def travel_progress_ratio(current_velos: int, goal_velos: int) -> float:
    if goal_velos <= 0:
        return 0.0
    return min(1.0, max(0.0, int(current_velos) / goal_velos))


def velos_progress_to_km(
    current_velos: int,
    goal_velos: int,
    total_length_km: Union[Decimal, float, int],
) -> float:
    """Map Velos progress to a km position on the track polyline (geometry only)."""
    ratio = travel_progress_ratio(current_velos, goal_velos)
    return float(total_length_km or 0) * ratio


def sync_travel_distance_km_from_velos(current_velos: int, track) -> Decimal:
    """Keep legacy km field aligned with Velos-based progress for derived displays."""
    km = velos_progress_to_km(
        current_velos,
        get_track_goal_velos(track),
        track.total_length_km if track else 0,
    )
    return Decimal(str(round(km, 5)))


def build_travel_status_avatar_fields(status) -> Dict[str, Any]:
    """Velos progress fields for map avatar JSON payloads."""
    track = status.track
    current_velos = int(getattr(status, 'current_travel_velos', 0) or 0)
    goal_velos = get_track_goal_velos(track)
    ratio = travel_progress_ratio(current_velos, goal_velos)
    current_km = velos_progress_to_km(current_velos, goal_velos, track.total_length_km)
    goal_reached = goal_velos > 0 and current_velos >= goal_velos
    return {
        'velos': current_velos,
        'goal_velos': goal_velos,
        'progress_ratio': ratio,
        'km': current_km,
        'track_total_length_km': float(track.total_length_km or 0),
        'goal_reached': goal_reached,
    }


def refresh_track_goal_velos(track, *, save: bool = True) -> int:
    goal = track_reference_velos(track.total_length_km) if track.total_length_km else 0
    track.goal_velos = goal
    if save:
        track.save(update_fields=['goal_velos'])
    return goal


def refresh_milestone_position_velos(milestone, *, save: bool = True) -> int:
    position = track_reference_velos(milestone.distance_km) if milestone.distance_km else 0
    milestone.position_velos = position
    if save:
        milestone.save(update_fields=['position_velos'])
    return position
