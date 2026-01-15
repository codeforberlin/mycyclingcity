# Generated manually for request_config_comparison field

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('iot', '0004_add_config_fetch_interval'),
    ]

    operations = [
        migrations.AddField(
            model_name='deviceconfiguration',
            name='request_config_comparison',
            field=models.BooleanField(default=False, help_text='Wenn aktiviert, wird beim nächsten Config-Report vom Gerät ein Vergleich durchgeführt und Unterschiede werden im Admin GUI angezeigt. Wird nach dem Vergleich automatisch zurückgesetzt.', verbose_name='Konfigurationsvergleich anfordern'),
        ),
    ]
