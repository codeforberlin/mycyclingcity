# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.core.management.base import BaseCommand

from api.models import HourlyMetric
from api.velos import calculate_velos_for_device


class Command(BaseCommand):
    help = "Backfill HourlyMetric.velos from distance_km and device FKM factor."

    def add_arguments(self, parser):
        parser.add_argument(
            '--batch-size',
            type=int,
            default=500,
            help='Number of rows to process per batch (default: 500)',
        )

    def handle(self, *args, **options):
        batch_size = options['batch_size']
        qs = HourlyMetric.objects.select_related('device__configuration').order_by('id')
        total = qs.count()
        updated = 0

        self.stdout.write(f"Backfilling velos for {total} HourlyMetric rows...")

        batch = []
        for metric in qs.iterator(chunk_size=batch_size):
            velos = calculate_velos_for_device(metric.distance_km, metric.device)
            if metric.velos != velos:
                metric.velos = velos
                batch.append(metric)
            if len(batch) >= batch_size:
                HourlyMetric.objects.bulk_update(batch, ['velos'])
                updated += len(batch)
                batch.clear()
                self.stdout.write(f"  … {updated} updated")

        if batch:
            HourlyMetric.objects.bulk_update(batch, ['velos'])
            updated += len(batch)

        self.stdout.write(self.style.SUCCESS(f"Done. Updated {updated} of {total} rows."))
