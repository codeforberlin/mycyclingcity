# mcc/api/management/commands/mcc_worker.py

# MCC General service processor (runs every 60 seconds)
# Updates HourlyMetric with active session data for leaderboard calculations
### * * * * * /home/roland/venv_mcc/bin/python /nas/public/dev/mcc-web/manage.py mcc_worker >> /nas/public/dev/mcc-web/logs/mcc_worker.log 2>&1

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings
from django.db.models import Sum
from api.models import CyclistDeviceCurrentMileage, HourlyMetric
from datetime import timedelta
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)

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
                    
                    if session_start_hour == hour_timestamp:
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
                    if existing_metric:
                        if hourly_distance <= existing_metric.distance_km:
                            logger.debug(f"Hourly distance calculation for expired session {sess.cyclist.user_id}/{sess.device.id}: "
                                       f"hourly_distance={hourly_distance}, "
                                       f"existing_metric={existing_metric.distance_km}, "
                                       f"no update needed (hourly_distance <= existing)")
                            continue
                    
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
                                'group_at_time': primary_group
                            }
                        )
                    
                    if not created:
                        # If metric already exists, it means we're updating it
                        # The hourly_distance should replace the existing value, not be added
                        # (unless there are multiple sessions in the same hour, then we sum)
                        # Actually, if a metric exists, it means we already processed this session
                        # So we should update it only if the new value is higher (session continued)
                        if hourly_distance > metric.distance_km:
                            old_distance = metric.distance_km
                            metric.distance_km = hourly_distance
                            # Update group if it changed
                            if metric.group_at_time != primary_group:
                                metric.group_at_time = primary_group
                            metric.save()
                            logger.info(f"Updated HourlyMetric for expired session: {sess.cyclist.user_id}, "
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
            
            for sess in active_sessions:
                # Only process sessions with mileage > 0
                if not sess.cumulative_mileage or sess.cumulative_mileage <= 0:
                    continue
                
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
                
                if session_start_hour == hour_timestamp:
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
                # The hourly_distance calculated above is the TOTAL distance for this hour
                # If a metric already exists, we should update it if the new total is higher
                if existing_metric:
                    if hourly_distance <= existing_metric.distance_km:
                        logger.debug(f"Hourly distance calculation for {sess.cyclist.user_id}/{sess.device.id}: "
                                   f"hourly_distance={hourly_distance}, "
                                   f"existing_metric={existing_metric.distance_km}, "
                                   f"no update needed (hourly_distance <= existing)")
                        # Don't update if the calculated distance is not higher
                        continue
                    # hourly_distance is higher, so we'll update the metric below
                
                if hourly_distance <= 0:
                    logger.debug(f"Hourly distance is {hourly_distance} for active session {sess.cyclist.user_id}/{sess.device.id}, skipping. "
                               f"cumulative_mileage={sess.cumulative_mileage}, "
                               f"session_start={sess.start_time}")
                    continue
                
                # Create or update metric entry for this hour
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
                            'group_at_time': primary_group
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
                    # The hourly_distance is the NEW distance for this hour (not cumulative)
                    # So we need to add it to the existing metric, or replace if it's higher
                    # Actually, hourly_distance is the total distance for this hour based on cumulative_mileage
                    # So we should replace the existing value if it's higher
                    if hourly_distance > metric.distance_km:
                        old_distance = metric.distance_km
                        metric.distance_km = hourly_distance
                        # Update group if it changed
                        if metric.group_at_time != primary_group:
                            metric.group_at_time = primary_group
                        metric.save()
                        updated_count += 1
                        logger.info(f"Updated HourlyMetric for active session: {sess.cyclist.user_id}, "
                                  f"hourly distance: {hourly_distance} km (was {old_distance} km)")
                        self.stdout.write(f"  → HourlyMetric aktualisiert für aktive Session: "
                                        f"{sess.cyclist.user_id} auf {sess.device.name}, "
                                        f"{hourly_distance} km für diese Stunde (war {old_distance} km)")
                    else:
                        logger.debug(f"HourlyMetric already has correct value for {sess.cyclist.user_id}")
            
            if saved_count > 0 or updated_count > 0:
                self.stdout.write(self.style.SUCCESS(
                    f"Erfolgreich {saved_count} neue HourlyMetric-Einträge erstellt, "
                    f"{updated_count} aktualisiert für aktive Sessions."
                ))
            else:
                self.stdout.write("Keine aktiven Sessions mit Kilometer-Daten gefunden.")
        else:
            self.stdout.write("Keine aktiven Sessions gefunden.")


