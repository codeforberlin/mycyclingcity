# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('iot', '0007_convert_wheel_size_to_millimeters'),
    ]

    operations = [
        migrations.AddField(
            model_name='firmwareimage',
            name='checksum_sha256',
            field=models.CharField(blank=True, help_text='SHA256-Prüfsumme der Firmware-Datei zur Verifizierung', max_length=64, null=True, verbose_name='SHA256-Prüfsumme'),
        ),
        migrations.AddField(
            model_name='firmwareimage',
            name='environment',
            field=models.CharField(blank=True, help_text='Hardware-Environment (z.B. heltec_wifi_lora_32_V3, wemos_d1_mini32)', max_length=100, null=True, verbose_name='Environment'),
        ),
    ]
