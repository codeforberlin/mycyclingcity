"""
Management command to analyze and fix inconsistencies between Cyclist.distance_total
(Master data) and HourlyMetrics (History data).

Cyclist.distance_total is the master data source, written directly via update_data.
HourlyMetrics should reflect the historical breakdown of how Cyclist.distance_total
was accumulated through sessions.

This command:
1. Identifies players where HourlyMetrics sum != Cyclist.distance_total
2. Provides options to fix the inconsistency by either:
   - Recalculating HourlyMetrics from Cyclist.distance_total (if possible)
   - Or adjusting Cyclist.distance_total to match HourlyMetrics (not recommended)

Usage:
    python manage.py analyze_mileage_consistency
    python manage.py analyze_mileage_consistency --player-id=123
    python manage.py analyze_mileage_consistency --fix --strategy=recalculate_metrics
"""

from django.core.management.base import BaseCommand
from django.db.models import Sum, Q
from decimal import Decimal
from api.models import Cyclist, HourlyMetric, CyclistDeviceCurrentMileage


class Command(BaseCommand):
    help = 'Analyze and fix inconsistencies between Cyclist.distance_total and HourlyMetrics'

    def add_arguments(self, parser):
        parser.add_argument(
            '--player-id',
            type=int,
            help='Analyze only a specific player by ID',
        )
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Fix inconsistencies (requires --strategy)',
        )
        parser.add_argument(
            '--strategy',
            type=str,
            choices=['delete_extra_metrics', 'recalculate_from_player'],
            help='Strategy to fix inconsistencies',
        )
        parser.add_argument(
            '--threshold',
            type=float,
            default=0.001,
            help='Threshold for considering values different (default: 0.001 km)',
        )

    def handle(self, *args, **options):
        cyclist_id = options.get('cyclist_id')
        fix = options.get('fix', False)
        strategy = options.get('strategy')
        threshold = Decimal(str(options.get('threshold', 0.001)))
        
        if fix and not strategy:
            self.stdout.write(self.style.ERROR('--fix requires --strategy'))
            return
        
        # Get players to analyze
        if cyclist_id:
            cyclists = Cyclist.objects.filter(id=cyclist_id)
            if not players.exists():
                self.stdout.write(self.style.ERROR(f'Player with ID {cyclist_id} not found'))
                return
        else:
            cyclists = Cyclist.objects.filter(is_visible=True)
        
        self.stdout.write(f'Analyzing {players.count()} player(s)...')
        self.stdout.write('')
        
        inconsistencies = []
        
        for player in players:
            # Get master data
            player_total = cyclist.distance_total or Decimal('0.00000')
            
            # Get HourlyMetrics sum
            metrics_sum = HourlyMetric.objects.filter(
                cyclist = player
            ).aggregate(
                total=Sum('distance_km')
            )['total'] or Decimal('0.00000')
            
            # Check for active sessions that should be included
            active_sessions = CyclistDeviceCurrentMileage.objects.filter(cyclist = player)
            active_sessions_sum = sum(
                (sess.cumulative_mileage or Decimal('0')) for sess in active_sessions
            )
            
            # Total expected from HourlyMetrics + active sessions
            expected_total = metrics_sum + active_sessions_sum
            
            # Calculate difference
            difference = float(expected_total) - float(player_total)
            
            if abs(difference) > float(threshold):
                inconsistencies.append({
                    'cyclist': player,
                    'player_total': player_total,
                    'metrics_sum': metrics_sum,
                    'active_sessions_sum': active_sessions_sum,
                    'expected_total': expected_total,
                    'difference': difference,
                })
        
        # Report findings
        if not inconsistencies:
            self.stdout.write(self.style.SUCCESS('✓ No inconsistencies found!'))
            return
        
        self.stdout.write(self.style.WARNING(f'Found {len(inconsistencies)} inconsistency(ies):'))
        self.stdout.write('')
        
        for inc in inconsistencies:
            cyclist = inc['cyclist']
            self.stdout.write(f'Player: {cyclist.user_id} (ID: {cyclist.id})')
            self.stdout.write(f'  Cyclist.distance_total (MASTER): {inc["player_total"]} km')
            self.stdout.write(f'  HourlyMetrics sum: {inc["metrics_sum"]} km')
            self.stdout.write(f'  Active sessions sum: {inc["active_sessions_sum"]} km')
            self.stdout.write(f'  Expected total (Metrics + Sessions): {inc["expected_total"]} km')
            self.stdout.write(f'  Difference: {inc["difference"]:+.3f} km')
            
            if inc['difference'] > 0:
                self.stdout.write(
                    self.style.WARNING(
                        f'  ⚠️  HourlyMetrics contain MORE data than Cyclist.distance_total'
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f'  ⚠️  HourlyMetrics contain LESS data than Cyclist.distance_total'
                    )
                )
            
            # Show detailed breakdown
            metrics = HourlyMetric.objects.filter(cyclist = player).order_by('timestamp')
            if metrics.exists():
                self.stdout.write(f'  HourlyMetrics entries ({metrics.count()}):')
                for metric in metrics[:10]:  # Show first 10
                    self.stdout.write(
                        f'    - {metric.timestamp} | Device: {metric.device.name} | '
                        f'{metric.distance_km} km | Group: {metric.group_at_time.name if metric.group_at_time else "None"}'
                    )
                if metrics.count() > 10:
                    self.stdout.write(f'    ... and {metrics.count() - 10} more entries')
            
            self.stdout.write('')
        
        # Fix inconsistencies if requested
        if fix:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING('FIXING INCONSISTENCIES...'))
            self.stdout.write('')
            
            if strategy == 'delete_extra_metrics':
                self._delete_extra_metrics(inconsistencies, threshold)
            elif strategy == 'recalculate_from_player':
                self.stdout.write(
                    self.style.ERROR(
                        'Strategy "recalculate_from_player" not yet implemented. '
                        'This would require session history which may not be available.'
                    )
                )
        
        # Summary
        self.stdout.write('')
        self.stdout.write('Summary:')
        self.stdout.write(f'  Players analyzed: {players.count()}')
        self.stdout.write(f'  Inconsistencies found: {len(inconsistencies)}')
        
        if fix:
            self.stdout.write(self.style.SUCCESS('\nFix operation completed'))
        else:
            self.stdout.write(
                self.style.WARNING(
                    '\nTo fix inconsistencies, run with --fix --strategy=<strategy>'
                )
            )
    
    def _delete_extra_metrics(self, inconsistencies, threshold):
        """
        Delete HourlyMetrics that exceed Cyclist.distance_total.
        This is a conservative approach: we keep Cyclist.distance_total as master
        and remove excess HourlyMetrics.
        """
        deleted_count = 0
        
        for inc in inconsistencies:
            cyclist = inc['cyclist']
            player_total = inc['player_total']
            metrics_sum = inc['metrics_sum']
            
            # Only fix if HourlyMetrics have MORE data
            if inc['difference'] > float(threshold):
                excess = Decimal(str(inc['difference']))
                self.stdout.write(
                    f'Player {cyclist.user_id}: Removing {excess} km excess from HourlyMetrics'
                )
                
                # Get all metrics ordered by timestamp (oldest first)
                metrics = HourlyMetric.objects.filter(
                    cyclist = player
                ).order_by('timestamp', 'id')
                
                # Delete metrics until we match player_total
                remaining_to_remove = excess
                
                for metric in metrics:
                    if remaining_to_remove <= 0:
                        break
                    
                    if metric.distance_km <= remaining_to_remove:
                        # Delete entire metric
                        removed = metric.distance_km
                        metric.delete()
                        remaining_to_remove -= removed
                        deleted_count += 1
                        self.stdout.write(
                            f'  Deleted metric: {metric.timestamp} | {removed} km'
                        )
                    else:
                        # Reduce metric by remaining amount
                        metric.distance_km -= remaining_to_remove
                        metric.save()
                        self.stdout.write(
                            f'  Reduced metric: {metric.timestamp} | -{remaining_to_remove} km'
                        )
                        remaining_to_remove = Decimal('0')
                
                self.stdout.write('')
        
        self.stdout.write(f'Deleted/reduced {deleted_count} HourlyMetric entries')

