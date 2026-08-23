# Enable eventboard km display by default (km tracking is now reliable).

from django.db import migrations, models


def enable_eventboard_km(apps, schema_editor):
    ExternalDisplaySettings = apps.get_model('api', 'ExternalDisplaySettings')
    ExternalDisplaySettings.objects.filter(pk=1).update(show_km_in_eventboard=True)


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0025_external_display_eventboard_km'),
    ]

    operations = [
        migrations.AlterField(
            model_name='externaldisplaysettings',
            name='show_km_in_eventboard',
            field=models.BooleanField(
                default=True,
                help_text=(
                    'Zeigt Event-km zusätzlich zu Velos auf dem Eventboard (Event-Auswahl, '
                    'Gruppenkarten, Podest, Statistik).'
                ),
                verbose_name='Kilometer im Eventboard',
            ),
        ),
        migrations.RunPython(enable_eventboard_km, migrations.RunPython.noop),
    ]
