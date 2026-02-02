# Generated manually for MyCyclingCity
# Adds last_session_distance_km field to HourlyMetric to track how much of the last processed session was already saved

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0004_add_last_session_start_time_to_hourly_metric'),
    ]

    operations = [
        migrations.AddField(
            model_name='hourlymetric',
            name='last_session_distance_km',
            field=models.DecimalField(blank=True, decimal_places=5, help_text='Distanz der zuletzt verarbeiteten Session für diese Stunde. Wird verwendet, um zu erkennen, ob eine Session gewachsen ist.', max_digits=15, null=True, verbose_name='Letzte Session Distanz (km)'),
        ),
    ]
