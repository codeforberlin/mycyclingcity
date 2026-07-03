# Generated manually for Velos Phase A

from django.db import migrations, models
import django.core.validators


def set_paedagogischer_bonus_from_wheel_size(apps, schema_editor):
    DeviceConfiguration = apps.get_model('iot', 'DeviceConfiguration')
    DeviceConfiguration.objects.filter(wheel_size__lte=1600).update(paedagogischer_bonus=0.3)


class Migration(migrations.Migration):

    dependencies = [
        ('iot', '0013_alter_devicemanagementsettings_iot_device_shared_api_key'),
    ]

    operations = [
        migrations.AddField(
            model_name='device',
            name='is_operator_box',
            field=models.BooleanField(
                default=False,
                help_text=(
                    'Reserviert für Phase H: RFID-Auslese ohne Strampel-Session. '
                    'Nur vom Systemadministrator setzbar.'
                ),
                verbose_name='Operator-Box',
            ),
        ),
        migrations.AddField(
            model_name='deviceconfiguration',
            name='paedagogischer_bonus',
            field=models.FloatField(
                default=0.0,
                help_text=(
                    'Zusatz zum FKM-Faktor für faire Velos: (2300 / Radumfang mm) + Bonus. '
                    'Typisch 0,3 für Kinder-/20"-Räder, 0,0 für Erwachsenenräder.'
                ),
                validators=[
                    django.core.validators.MinValueValidator(0.0),
                    django.core.validators.MaxValueValidator(2.0),
                ],
                verbose_name='Pädagogischer Bonus',
            ),
        ),
        migrations.RunPython(set_paedagogischer_bonus_from_wheel_size, migrations.RunPython.noop),
    ]
