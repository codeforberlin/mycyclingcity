# Generated manually for OLED display lock fields.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('iot', '0014_velos_device_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='deviceconfiguration',
            name='display_velos_locked',
            field=models.BooleanField(
                default=False,
                help_text='When true, OLED shows frozen_display_velos instead of live session Velos.',
                verbose_name='OLED Velos eingefroren',
            ),
        ),
        migrations.AddField(
            model_name='deviceconfiguration',
            name='frozen_display_velos',
            field=models.IntegerField(
                default=0,
                help_text='Velos shown on OLED while display_velos_locked is active.',
                verbose_name='Eingefrorene OLED-Velos',
            ),
        ),
    ]
