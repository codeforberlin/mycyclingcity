# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.core.management.base import BaseCommand

from api.models import (
    GroupTravelStatus,
    LeafGroupTravelContribution,
    Milestone,
    TravelTrack,
)
from api.travel_velos import refresh_milestone_position_velos, refresh_track_goal_velos
from api.velos import track_reference_velos


class Command(BaseCommand):
    help = "Backfill travel Velos fields from legacy km progress (29\" reference)."

    def handle(self, *args, **options):
        track_count = 0
        for track in TravelTrack.objects.all():
            refresh_track_goal_velos(track)
            track_count += 1

        milestone_count = 0
        for milestone in Milestone.objects.all():
            refresh_milestone_position_velos(milestone)
            milestone_count += 1

        status_updated = 0
        for status in GroupTravelStatus.objects.select_related('track'):
            velos = track_reference_velos(status.current_travel_distance or 0)
            offset = track_reference_velos(status.start_km_offset or 0)
            if status.current_travel_velos != velos or status.start_velos_offset != offset:
                status.current_travel_velos = velos
                status.start_velos_offset = offset
                status.save(update_fields=['current_travel_velos', 'start_velos_offset'])
                status_updated += 1

        contrib_updated = 0
        for contribution in LeafGroupTravelContribution.objects.all():
            velos = track_reference_velos(contribution.current_travel_distance or 0)
            if contribution.current_travel_velos != velos:
                contribution.current_travel_velos = velos
                contribution.save(update_fields=['current_travel_velos'])
                contrib_updated += 1

        self.stdout.write(self.style.SUCCESS(
            f"Done. Tracks: {track_count}, milestones: {milestone_count}, "
            f"statuses updated: {status_updated}, contributions updated: {contrib_updated}"
        ))
