# Generated manually for MyCyclingCity
# Adds last_session_start_time field to HourlyMetric to track which session was last processed

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0003_milestone_assigned_to_group_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='hourlymetric',
            name='last_session_start_time',
            field=models.DateTimeField(blank=True, help_text='Startzeit der zuletzt verarbeiteten Session für diese Stunde. Wird verwendet, um zu erkennen, ob eine Session bereits verarbeitet wurde.', null=True, verbose_name='Letzte Session Startzeit'),
        ),
    ]
