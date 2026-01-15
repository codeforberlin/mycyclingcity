# Generated manually for config fetch interval

from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('iot', '0003_add_previous_api_key_grace_period'),
    ]

    operations = [
        migrations.AddField(
            model_name='deviceconfiguration',
            name='config_fetch_interval_seconds',
            field=models.IntegerField(default=3600, help_text='Intervall in Sekunden zum regelmäßigen Abrufen der Konfiguration vom Server. 0 = deaktiviert. Wird auch verwendet, wenn Deep Sleep deaktiviert ist.', validators=[django.core.validators.MinValueValidator(0)], verbose_name='Config-Abruf-Intervall (Sekunden)'),
        ),
    ]
