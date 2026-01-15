# Generated manually for API key rotation grace period

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('iot', '0002_add_ap_password'),
    ]

    operations = [
        migrations.AddField(
            model_name='deviceconfiguration',
            name='previous_api_key',
            field=models.CharField(blank=True, help_text='Der vorherige API-Key bleibt für 48 Stunden nach Rotation gültig, damit das Gerät den neuen Key abholen kann.', max_length=200, null=True, verbose_name='Vorheriger API-Key'),
        ),
        migrations.AddField(
            model_name='deviceconfiguration',
            name='previous_api_key_expires_at',
            field=models.DateTimeField(blank=True, help_text='Zeitpunkt, ab dem der vorherige API-Key nicht mehr gültig ist', null=True, verbose_name='Vorheriger API-Key läuft ab am'),
        ),
    ]
