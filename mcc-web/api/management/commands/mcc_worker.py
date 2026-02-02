# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    mcc_worker.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings
from django.db.models import Sum
from api.models import CyclistDeviceCurrentMileage, HourlyMetric
from datetime import timedelta
from decimal import Decimal
from config.logger_utils import get_logger

logger = get_logger(__name__)

class Command(BaseCommand):
    help = 'Central MCC service processor for background tasks'

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE(f"--- Starte MCC Worker: {timezone.now()} ---"))
        
        # Task 1: Save active sessions to hourly history
        self.save_active_sessions_to_history()
        
        # Task 2: Clean up inactive sessions
        self.cleanup_expired_sessions()
        
        # HERE additional tasks can be called in the future:
        # self.generate_daily_reports()
        # self.sync_external_data()

        self.stdout.write(self.style.NOTICE("--- MCC Worker beendet ---"))

    def cleanup_expired_sessions(self):
        """Deletes sessions that have exceeded the inactivity limit."""
        now = timezone.now()
        timeout_min = getattr(settings, 'MCC_SESSION_TIMEOUT_MINUTES', 5)
        timeout_limit = now - timedelta(minutes=timeout_min)

        expired_sessions = CyclistDeviceCurrentMileage.objects.filter(
            last_activity__lt=timeout_limit
        )
        
        count = expired_sessions.count()
        if count > 0:
            saved_count = 0
            for sess in expired_sessions:
                logger.info(f"Cleaning up expired session: {sess.cyclist.user_id} (inactive since {sess.last_activity})")
                self.stdout.write(f"Bereinige Sitzung: {sess.cyclist.user_id} (Inaktiv seit {sess.last_activity})")
                
                # Save session to HourlyMetric before deleting
                if sess.cumulative_mileage and sess.cumulative_mileage > 0:
                    # Get the cyclist's primary group at the time of session end
                    primary_group = sess.cyclist.groups.first()
                    
                    # Round timestamp to the hour to aggregate metrics within the same hour
                    hour_timestamp = sess.last_activity.replace(minute=0, second=0, microsecond=0)
                    
                    # Check if there's already a metric entry for this hour
                    existing_metric = HourlyMetric.objects.filter(
                        cyclist=sess.cyclist,
                        device=sess.device,
                        timestamp=hour_timestamp
                    ).first()
                    
                    # Calculate distance for this hour only (not cumulative)
                    # IMPORTANT: cumulative_mileage is the distance since session start, not total distance
                    session_start_hour = sess.start_time.replace(minute=0, second=0, microsecond=0)
                    
                    # Track if session started in current hour (needed for new session detection)
                    session_started_in_current_hour = (session_start_hour == hour_timestamp)
                    
                    if session_started_in_current_hour:
                        # Session started in this hour, so cumulative_mileage is the distance for this hour
                        hourly_distance = sess.cumulative_mileage
                        logger.debug(f"Expired session started in this hour for {sess.cyclist.user_id}: "
                                   f"cumulative_mileage={sess.cumulative_mileage}, "
                                   f"hourly_distance={hourly_distance}")
                    else:
                        # Session started before this hour
                        # Calculate the mileage at the start of this hour from HourlyMetrics
                        mileage_at_hour_start = HourlyMetric.objects.filter(
                            cyclist=sess.cyclist,
                            device=sess.device,
                            timestamp__lt=hour_timestamp
                        ).aggregate(total=Sum('distance_km'))['total'] or Decimal('0.00000')
                        
                        # Find the distance at session start from HourlyMetrics
                        mileage_at_session_start = HourlyMetric.objects.filter(
                            cyclist=sess.cyclist,
                            device=sess.device,
                            timestamp__lt=session_start_hour
                        ).aggregate(total=Sum('distance_km'))['total'] or Decimal('0.00000')
                        
                        # Total distance now = mileage_at_session_start + cumulative_mileage
                        total_distance_now = mileage_at_session_start + sess.cumulative_mileage
                        
                        # Distance for this hour = total_distance_now - mileage_at_hour_start
                        hourly_distance = total_distance_now - mileage_at_hour_start
                        
                        logger.debug(f"Calculating hourly distance for expired session {sess.cyclist.user_id}: "
                                   f"session_start={sess.start_time}, "
                                   f"cumulative_mileage={sess.cumulative_mileage}, "
                                   f"mileage_at_session_start={mileage_at_session_start}, "
                                   f"mileage_at_hour_start={mileage_at_hour_start}, "
                                   f"total_distance_now={total_distance_now}, "
                                   f"hourly_distance={hourly_distance}")
                    
                    # If an existing metric exists, we need to check if we should update it
                    # CRITICAL: For expired sessions that started in the current hour, we need to distinguish
                    # between a NEW session (should ADD to existing metric) and an UPDATE (should REPLACE if higher).
                    # We use last_session_start_time to track which session was last processed to avoid double-counting.
                    if existing_metric:
                        if session_started_in_current_hour:
                            # Expired session started in current hour - check if it's a NEW session or UPDATE
                            # Use last_session_start_time to determine if this session was already processed
                            session_already_processed = (
                                existing_metric.last_session_start_time is not None and
                                sess.start_time == existing_metric.last_session_start_time
                            )
                            
                            if hourly_distance < existing_metric.distance_km:
                                # hourly_distance is smaller than existing metric
                                if session_already_processed:
                                    # This session was already processed - skip to avoid double-counting
                                    logger.debug(f"Expired session already processed for {sess.cyclist.user_id}: "
                                               f"start_time={sess.start_time}, "
                                               f"last_session_start_time={existing_metric.last_session_start_time}, "
                                               f"hourly_distance={hourly_distance}, "
                                               f"existing_metric={existing_metric.distance_km}")
                                    continue
                                else:
                                    # NEW SESSION: This expired session should be ADDED to existing metric
                                    # (e.g., first session expired, second session started in same hour)
                                    old_distance = existing_metric.distance_km
                                    existing_metric.distance_km += hourly_distance  # ADDITION
                                    existing_metric.last_session_start_time = sess.start_time  # Track this session
                                    existing_metric.last_session_distance_km = hourly_distance  # Track session distance
                                    # Update group if it changed
                                    if existing_metric.group_at_time != primary_group:
                                        existing_metric.group_at_time = primary_group
                                    existing_metric.save()
                                    logger.info(f"Added expired session to HourlyMetric for {sess.cyclist.user_id}: "
                                              f"added {hourly_distance} km (total now: {existing_metric.distance_km} km, was {old_distance} km)")
                                    self.stdout.write(f"  → Abgelaufene Session hinzugefügt zu HourlyMetric: "
                                                    f"{sess.cyclist.user_id} auf {sess.device.name}, "
                                                    f"+{hourly_distance} km (Gesamt: {existing_metric.distance_km} km)")
                                    saved_count += 1
                                    continue  # Skip to next session
                            elif hourly_distance > existing_metric.distance_km:
                                # hourly_distance is larger than existing metric
                                if session_already_processed:
                                    # Expired session was already processed and has grown
                                    # Calculate difference based on last_session_distance_km if available
                                    if existing_metric.last_session_distance_km is not None:
                                        distance_delta = hourly_distance - existing_metric.last_session_distance_km
                                    else:
                                        # Fallback: use difference from total metric
                                        distance_delta = hourly_distance - existing_metric.distance_km
                                    old_distance = existing_metric.distance_km
                                    existing_metric.distance_km += distance_delta  # Add only the difference
                                    existing_metric.last_session_distance_km = hourly_distance  # Update tracking
                                    existing_metric.last_session_start_time = sess.start_time  # Update tracking
                                    # Update group if it changed
                                    if existing_metric.group_at_time != primary_group:
                                        existing_metric.group_at_time = primary_group
                                    existing_metric.save()
                                    logger.info(f"Updated HourlyMetric for expired session: {sess.cyclist.user_id}, "
                                              f"added {distance_delta} km (total now: {hourly_distance} km, was {old_distance} km)")
                                    self.stdout.write(f"  → HourlyMetric aktualisiert für abgelaufene Session: "
                                                    f"{sess.cyclist.user_id} auf {sess.device.name}, "
                                                    f"+{distance_delta} km (Gesamt: {hourly_distance} km, war {old_distance} km)")
                                    saved_count += 1
                                    continue  # Skip to next session
                                else:
                                    # This is a different session or the metric was reset
                                    logger.warning(f"Unexpected case for expired session {sess.cyclist.user_id}: "
                                                f"hourly_distance={hourly_distance} > existing={existing_metric.distance_km}, "
                                                f"but session not tracked")
                                    old_distance = existing_metric.distance_km
                                    existing_metric.distance_km = hourly_distance
                                    existing_metric.last_session_start_time = sess.start_time
                                    existing_metric.last_session_distance_km = hourly_distance
                                    if existing_metric.group_at_time != primary_group:
                                        existing_metric.group_at_time = primary_group
                                    existing_metric.save()
                                    saved_count += 1
                                    continue
                            else:
                                # hourly_distance == existing_metric.distance_km
                                if session_already_processed:
                                    # Session was already processed - check if it has changed
                                    if existing_metric.last_session_distance_km is not None:
                                        if hourly_distance > existing_metric.last_session_distance_km:
                                            # Session has grown but total metric hasn't - update
                                            distance_delta = hourly_distance - existing_metric.last_session_distance_km
                                            old_distance = existing_metric.distance_km
                                            existing_metric.distance_km += distance_delta
                                            existing_metric.last_session_distance_km = hourly_distance
                                            existing_metric.save()
                                            saved_count += 1
                                            logger.warning(f"Expired session grew but total didn't for {sess.cyclist.user_id}: "
                                                         f"added {distance_delta} km")
                                            continue
                                        elif hourly_distance == existing_metric.last_session_distance_km:
                                            # Session hasn't changed - skip
                                            logger.debug(f"Expired session already processed with no change for {sess.cyclist.user_id}")
                                            continue
                                    else:
                                        # No tracking info - skip
                                        logger.debug(f"Expired session already processed with no change for {sess.cyclist.user_id}")
                                        continue
                                else:
                                    # Update tracking but don't change distance
                                    existing_metric.last_session_start_time = sess.start_time
                                    existing_metric.last_session_distance_km = hourly_distance
                                    existing_metric.save()
                                    logger.debug(f"Updated tracking for expired session {sess.cyclist.user_id} "
                                               f"without changing distance")
                                    continue
                        else:
                            # Session started before this hour - hourly_distance is total for this hour
                            if hourly_distance <= existing_metric.distance_km:
                                logger.debug(f"Hourly distance calculation for expired session {sess.cyclist.user_id}/{sess.device.id}: "
                                           f"hourly_distance={hourly_distance}, "
                                           f"existing_metric={existing_metric.distance_km}, "
                                           f"no update needed (hourly_distance <= existing)")
                                continue
                            # hourly_distance is higher, so we'll update the metric below
                    
                    if hourly_distance <= 0:
                        logger.warning(f"Hourly distance is {hourly_distance} for expired session {sess.cyclist.user_id}, skipping. "
                                     f"cumulative_mileage={sess.cumulative_mileage}, "
                                     f"session_start={sess.start_time}")
                        continue
                    
                    # Create/update metric with cyclist AND device combination
                    # This allows reporting both by cyclist and by device
                    if existing_metric:
                        metric = existing_metric
                        created = False
                    else:
                        metric, created = HourlyMetric.objects.get_or_create(
                            cyclist=sess.cyclist,
                            device=sess.device,
                            timestamp=hour_timestamp,
                            defaults={
                                'distance_km': hourly_distance,
                                'group_at_time': primary_group,
                                'last_session_start_time': sess.start_time,  # Track the session that created this metric
                                'last_session_distance_km': hourly_distance  # Track session distance
                            }
                        )
                    
                    if not created:
                        # Update existing metric with current hourly distance
                        # This branch is only reached for expired sessions from previous hours
                        # (expired sessions in current hour are handled above)
                        # For expired sessions from previous hours: hourly_distance is total for this hour
                        if hourly_distance > metric.distance_km:
                            old_distance = metric.distance_km
                            metric.distance_km = hourly_distance
                            metric.last_session_start_time = sess.start_time  # Update tracking
                            metric.last_session_distance_km = hourly_distance  # Update tracking
                            # Update group if it changed
                            if metric.group_at_time != primary_group:
                                metric.group_at_time = primary_group
                            metric.save()
                            logger.info(f"Updated HourlyMetric for expired session from previous hour: {sess.cyclist.user_id}, "
                                      f"hourly distance: {hourly_distance} km (was {old_distance} km)")
                            self.stdout.write(f"  → HourlyMetric aktualisiert: {hourly_distance} km für diese Stunde "
                                            f"für {sess.cyclist.user_id} auf {sess.device.name}")
                        else:
                            logger.debug(f"HourlyMetric already exists with higher value for {sess.cyclist.user_id}")
                    else:
                        logger.info(f"Created HourlyMetric for expired session: {sess.cyclist.user_id}, "
                                  f"hourly distance: {hourly_distance} km")
                        self.stdout.write(f"  → HourlyMetric erstellt: {hourly_distance} km für diese Stunde "
                                        f"für {sess.cyclist.user_id} auf {sess.device.name}")
                    saved_count += 1
            
            expired_sessions.delete()
            self.stdout.write(self.style.SUCCESS(f"Erfolgreich {count} Sitzungen gelöscht, {saved_count} HourlyMetric-Einträge erstellt."))
        else:
            self.stdout.write("Keine abgelaufenen Sitzungen gefunden.")

    def save_active_sessions_to_history(self):
        """
        Saves active sessions to HourlyMetric periodically.
        This ensures that ongoing sessions are tracked in the hourly history
        even if they haven't expired yet.
        
        IMPORTANT: Each hour should track only the kilometers driven in that hour,
        not cumulative kilometers. Each hour starts from 0.
        """
        now = timezone.now()
        hour_timestamp = now.replace(minute=0, second=0, microsecond=0)
        
        # Get all active sessions
        active_sessions = CyclistDeviceCurrentMileage.objects.select_related('cyclist', 'device').all()
        
        count = active_sessions.count()
        if count > 0:
            saved_count = 0
            updated_count = 0
            skipped_count = 0  # Count sessions that were skipped (already processed, no change)
            sessions_with_mileage = 0  # Count sessions with mileage > 0
            
            for sess in active_sessions:
                # Only process sessions with mileage > 0
                if not sess.cumulative_mileage or sess.cumulative_mileage <= 0:
                    continue
                
                sessions_with_mileage += 1
                
                # Get the cyclist's primary group
                primary_group = sess.cyclist.groups.first()
                
                # Check if there's already a metric entry for this hour
                existing_metric = HourlyMetric.objects.filter(
                    cyclist=sess.cyclist,
                    device=sess.device,
                    timestamp=hour_timestamp
                ).first()
                
                # Calculate distance for this hour only (not cumulative)
                # IMPORTANT: cumulative_mileage is the distance since session start, not total distance
                # We need to calculate how much distance was driven in this hour
                
                # If session started in this hour, the cumulative_mileage is the distance for this hour
                session_start_hour = sess.start_time.replace(minute=0, second=0, microsecond=0)
                
                # Track if session started in current hour (needed for new session detection)
                session_started_in_current_hour = (session_start_hour == hour_timestamp)
                
                if session_started_in_current_hour:
                    # Session started in this hour, so cumulative_mileage is the distance for this hour
                    hourly_distance = sess.cumulative_mileage
                    logger.debug(f"Session started in this hour for {sess.cyclist.user_id}: "
                               f"cumulative_mileage={sess.cumulative_mileage}, "
                               f"hourly_distance={hourly_distance}")
                else:
                    # Session started before this hour
                    # Calculate the mileage at the start of this hour from HourlyMetrics
                    mileage_at_hour_start = HourlyMetric.objects.filter(
                        cyclist=sess.cyclist,
                        device=sess.device,
                        timestamp__lt=hour_timestamp
                    ).aggregate(total=Sum('distance_km'))['total'] or Decimal('0.00000')
                    
                    # The total distance (cumulative since session start + all previous HourlyMetrics)
                    # should equal cumulative_mileage + sum of all HourlyMetrics before session start
                    # But actually, cumulative_mileage is just since session start
                    # So we need to find the distance at session start from HourlyMetrics
                    mileage_at_session_start = HourlyMetric.objects.filter(
                        cyclist=sess.cyclist,
                        device=sess.device,
                        timestamp__lt=session_start_hour
                    ).aggregate(total=Sum('distance_km'))['total'] or Decimal('0.00000')
                    
                    # Total distance now = mileage_at_session_start + cumulative_mileage
                    total_distance_now = mileage_at_session_start + sess.cumulative_mileage
                    
                    # Distance for this hour = total_distance_now - mileage_at_hour_start
                    hourly_distance = total_distance_now - mileage_at_hour_start
                    
                    logger.debug(f"Calculating hourly distance for {sess.cyclist.user_id}: "
                               f"session_start={sess.start_time}, "
                               f"cumulative_mileage={sess.cumulative_mileage}, "
                               f"mileage_at_session_start={mileage_at_session_start}, "
                               f"mileage_at_hour_start={mileage_at_hour_start}, "
                               f"total_distance_now={total_distance_now}, "
                               f"hourly_distance={hourly_distance}")
                
                # If an existing metric exists, we need to check if we should update it
                # CRITICAL: For sessions that started in the current hour, we need to distinguish
                # between a NEW session (should ADD to existing metric) and a CONTINUED session
                # (should REPLACE if higher). We use last_session_start_time to track which session
                # was last processed to avoid double-counting.
                if existing_metric:
                    if session_started_in_current_hour:
                        # Session started in current hour - check if it's a NEW session or UPDATE
                        # Use last_session_start_time to determine if this session was already processed
                        session_already_processed = (
                            existing_metric.last_session_start_time is not None and
                            sess.start_time == existing_metric.last_session_start_time
                        )
                        
                        if hourly_distance < existing_metric.distance_km:
                            # hourly_distance is smaller than existing metric
                            if session_already_processed:
                                # This session was already processed - check if it has grown
                                if existing_metric.last_session_distance_km is not None:
                                    if hourly_distance > existing_metric.last_session_distance_km:
                                        # Session has grown - add the difference
                                        distance_delta = hourly_distance - existing_metric.last_session_distance_km
                                        old_distance = existing_metric.distance_km
                                        existing_metric.distance_km += distance_delta  # Add only the difference
                                        existing_metric.last_session_distance_km = hourly_distance  # Update tracking
                                        # Update group if it changed
                                        if existing_metric.group_at_time != primary_group:
                                            existing_metric.group_at_time = primary_group
                                        existing_metric.save()
                                        updated_count += 1
                                        logger.info(f"Updated HourlyMetric for grown session: {sess.cyclist.user_id}, "
                                                  f"added {distance_delta} km (session: {hourly_distance} km, was {existing_metric.last_session_distance_km} km, "
                                                  f"total now: {existing_metric.distance_km} km, was {old_distance} km)")
                                        self.stdout.write(f"  → HourlyMetric aktualisiert für gewachsene Session: "
                                                        f"{sess.cyclist.user_id} auf {sess.device.name}, "
                                                        f"+{distance_delta} km (Session: {hourly_distance} km, Gesamt: {existing_metric.distance_km} km)")
                                        continue
                                    elif hourly_distance == existing_metric.last_session_distance_km:
                                        # Session hasn't changed - skip to avoid double-counting
                                        skipped_count += 1
                                        logger.debug(f"Session already processed with no change for {sess.cyclist.user_id}: "
                                                   f"start_time={sess.start_time}, "
                                                   f"hourly_distance={hourly_distance}, "
                                                   f"last_session_distance_km={existing_metric.last_session_distance_km}")
                                        continue
                                    else:
                                        # hourly_distance < last_session_distance_km - shouldn't happen, but skip
                                        skipped_count += 1
                                        logger.warning(f"Session distance decreased for {sess.cyclist.user_id}: "
                                                     f"hourly_distance={hourly_distance}, "
                                                     f"last_session_distance_km={existing_metric.last_session_distance_km}")
                                        continue
                                else:
                                    # last_session_distance_km is None - this shouldn't happen if session_already_processed
                                    # But handle it by treating as unchanged
                                    skipped_count += 1
                                    logger.warning(f"Session already processed but last_session_distance_km is None for {sess.cyclist.user_id}")
                                    continue
                            else:
                                # NEW SESSION: This is a new session that should be ADDED to existing metric
                                # (e.g., old session expired, new session started in same hour)
                                old_distance = existing_metric.distance_km
                                existing_metric.distance_km += hourly_distance  # ADDITION
                                existing_metric.last_session_start_time = sess.start_time  # Track this session
                                existing_metric.last_session_distance_km = hourly_distance  # Track session distance
                                # Update group if it changed
                                if existing_metric.group_at_time != primary_group:
                                    existing_metric.group_at_time = primary_group
                                existing_metric.save()
                                updated_count += 1
                                logger.info(f"Added NEW session to HourlyMetric for {sess.cyclist.user_id}: "
                                          f"added {hourly_distance} km (total now: {existing_metric.distance_km} km, was {old_distance} km)")
                                self.stdout.write(f"  → Neue Session hinzugefügt zu HourlyMetric: "
                                                f"{sess.cyclist.user_id} auf {sess.device.name}, "
                                                f"+{hourly_distance} km (Gesamt: {existing_metric.distance_km} km)")
                                continue  # Skip to next session
                        elif hourly_distance > existing_metric.distance_km:
                            # hourly_distance is larger than existing metric
                            if session_already_processed:
                                # Session was already processed and has grown
                                # Calculate difference based on last_session_distance_km if available
                                if existing_metric.last_session_distance_km is not None:
                                    distance_delta = hourly_distance - existing_metric.last_session_distance_km
                                else:
                                    # Fallback: use difference from total metric
                                    distance_delta = hourly_distance - existing_metric.distance_km
                                old_distance = existing_metric.distance_km
                                existing_metric.distance_km += distance_delta  # Add only the difference
                                existing_metric.last_session_distance_km = hourly_distance  # Update tracking
                                existing_metric.last_session_start_time = sess.start_time  # Update tracking
                                # Update group if it changed
                                if existing_metric.group_at_time != primary_group:
                                    existing_metric.group_at_time = primary_group
                                existing_metric.save()
                                updated_count += 1
                                logger.info(f"Updated HourlyMetric for active session: {sess.cyclist.user_id}, "
                                          f"added {distance_delta} km (session: {hourly_distance} km, was {existing_metric.last_session_distance_km or existing_metric.distance_km} km, "
                                          f"total now: {existing_metric.distance_km} km, was {old_distance} km)")
                                self.stdout.write(f"  → HourlyMetric aktualisiert für aktive Session: "
                                                f"{sess.cyclist.user_id} auf {sess.device.name}, "
                                                f"+{distance_delta} km (Session: {hourly_distance} km, Gesamt: {existing_metric.distance_km} km)")
                                continue  # Skip to next session
                            else:
                                # This is a different session or the metric was reset
                                # This shouldn't happen normally, but handle it by replacing
                                logger.warning(f"Unexpected case for {sess.cyclist.user_id}: "
                                            f"hourly_distance={hourly_distance} > existing={existing_metric.distance_km}, "
                                            f"but session not tracked (start_time={sess.start_time}, "
                                            f"last_session_start_time={existing_metric.last_session_start_time})")
                                old_distance = existing_metric.distance_km
                                existing_metric.distance_km = hourly_distance
                                existing_metric.last_session_start_time = sess.start_time
                                existing_metric.last_session_distance_km = hourly_distance
                                if existing_metric.group_at_time != primary_group:
                                    existing_metric.group_at_time = primary_group
                                existing_metric.save()
                                updated_count += 1
                                logger.info(f"Updated HourlyMetric (unexpected case) for {sess.cyclist.user_id}: "
                                          f"set to {hourly_distance} km (was {old_distance} km)")
                                continue
                        else:
                            # hourly_distance == existing_metric.distance_km
                            if session_already_processed:
                                # Session was already processed - check if it has changed
                                if existing_metric.last_session_distance_km is not None:
                                    if hourly_distance > existing_metric.last_session_distance_km:
                                        # Session has grown but total metric hasn't - shouldn't happen, but update
                                        distance_delta = hourly_distance - existing_metric.last_session_distance_km
                                        old_distance = existing_metric.distance_km
                                        existing_metric.distance_km += distance_delta
                                        existing_metric.last_session_distance_km = hourly_distance
                                        existing_metric.save()
                                        updated_count += 1
                                        logger.warning(f"Session grew but total didn't for {sess.cyclist.user_id}: "
                                                     f"added {distance_delta} km")
                                        continue
                                    elif hourly_distance == existing_metric.last_session_distance_km:
                                        # Session hasn't changed - skip
                                        skipped_count += 1
                                        logger.debug(f"Session already processed with no change for {sess.cyclist.user_id}")
                                        continue
                                else:
                                    # No tracking info - skip
                                    skipped_count += 1
                                    logger.debug(f"Session already processed with no change for {sess.cyclist.user_id}")
                                    continue
                            else:
                                # This shouldn't happen - same distance but different session
                                # Could be a new session with same distance as existing total
                                # For safety, update the tracking but don't change the distance
                                existing_metric.last_session_start_time = sess.start_time
                                existing_metric.last_session_distance_km = hourly_distance
                                existing_metric.save()
                                logger.debug(f"Updated tracking for {sess.cyclist.user_id} "
                                           f"without changing distance (hourly_distance == existing)")
                                continue
                    else:
                        # Session started before this hour - hourly_distance is total for this hour
                        if hourly_distance <= existing_metric.distance_km:
                            skipped_count += 1
                            logger.debug(f"Hourly distance calculation for {sess.cyclist.user_id}/{sess.device.id}: "
                                       f"hourly_distance={hourly_distance}, "
                                       f"existing_metric={existing_metric.distance_km}, "
                                       f"no update needed (hourly_distance <= existing)")
                            # Don't update if the calculated distance is not higher
                            continue
                        # hourly_distance is higher, so we'll update the metric below
                
                if hourly_distance <= 0:
                    skipped_count += 1
                    logger.debug(f"Hourly distance is {hourly_distance} for active session {sess.cyclist.user_id}/{sess.device.id}, skipping. "
                               f"cumulative_mileage={sess.cumulative_mileage}, "
                               f"session_start={sess.start_time}")
                    continue
                
                # Create or update metric entry for this hour
                # Note: If existing_metric exists:
                # - For sessions in current hour: Already handled above (new session addition or update with delta)
                # - For sessions from previous hours: hourly_distance is total for this hour, handled below
                # Here we handle:
                # 1. No existing metric (create new)
                # 2. Existing metric with hourly_distance > existing for sessions from previous hours (replace total)
                if existing_metric:
                    metric = existing_metric
                    created = False
                else:
                        metric, created = HourlyMetric.objects.get_or_create(
                            cyclist=sess.cyclist,
                            device=sess.device,
                            timestamp=hour_timestamp,
                            defaults={
                                'distance_km': hourly_distance,
                                'group_at_time': primary_group,
                                'last_session_start_time': sess.start_time,  # Track the session that created this metric
                                'last_session_distance_km': hourly_distance  # Track session distance
                            }
                        )
                
                if created:
                    saved_count += 1
                    logger.info(f"Created HourlyMetric for active session: {sess.cyclist.user_id}, "
                              f"hourly distance: {hourly_distance} km (cumulative: {sess.cumulative_mileage} km)")
                    self.stdout.write(f"  → HourlyMetric erstellt für aktive Session: "
                                    f"{hourly_distance} km für diese Stunde "
                                    f"für {sess.cyclist.user_id} auf {sess.device.name}")
                else:
                    # Update existing metric with current hourly distance
                    # This branch is only reached for sessions from previous hours
                    # (sessions in current hour are handled above)
                    # For sessions from previous hours: hourly_distance is total for this hour
                    if hourly_distance > metric.distance_km:
                        old_distance = metric.distance_km
                        metric.distance_km = hourly_distance
                        metric.last_session_start_time = sess.start_time  # Update tracking
                        # Update group if it changed
                        if metric.group_at_time != primary_group:
                            metric.group_at_time = primary_group
                        metric.save()
                        updated_count += 1
                        logger.info(f"Updated HourlyMetric for active session from previous hour: {sess.cyclist.user_id}, "
                                  f"hourly distance: {hourly_distance} km (was {old_distance} km)")
                        self.stdout.write(f"  → HourlyMetric aktualisiert für aktive Session: "
                                        f"{sess.cyclist.user_id} auf {sess.device.name}, "
                                        f"{hourly_distance} km für diese Stunde (war {old_distance} km)")
                    else:
                        skipped_count += 1
                        logger.debug(f"HourlyMetric already has correct value for {sess.cyclist.user_id}")
            
            if saved_count > 0 or updated_count > 0:
                self.stdout.write(self.style.SUCCESS(
                    f"Erfolgreich {saved_count} neue HourlyMetric-Einträge erstellt, "
                    f"{updated_count} aktualisiert für aktive Sessions."
                ))
            else:
                if sessions_with_mileage > 0:
                    # Sessions exist but were all skipped (already processed, no changes)
                    self.stdout.write(f"{sessions_with_mileage} aktive Session(s) mit Kilometer-Daten gefunden, "
                                    f"aber keine Änderungen seit letztem Worker-Lauf.")
                else:
                    # No sessions with mileage > 0
                    self.stdout.write("Keine aktiven Sessions mit Kilometer-Daten gefunden.")
        else:
            self.stdout.write("Keine aktiven Sessions gefunden.")


