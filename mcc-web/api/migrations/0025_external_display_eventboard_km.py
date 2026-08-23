# Generated manually — eventboard km display toggle (default off).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0024_external_display_km_defaults'),
    ]

    operations = [
        migrations.AddField(
            model_name='externaldisplaysettings',
            name='show_km_in_eventboard',
            field=models.BooleanField(
                default=False,
                help_text=(
                    'Zeigt Event-km zusätzlich zu Velos auf dem Eventboard (Gruppenkarten, Podest, '
                    'Statistik). Standard: aus — bestehende Events zeigen nur Velos, bis km '
                    'zuverlässig erfasst sind.'
                ),
                verbose_name='Kilometer im Eventboard',
            ),
        ),
    ]
