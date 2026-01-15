# Generated manually for ap_password field addition

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('iot', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='deviceconfiguration',
            name='ap_password',
            field=models.CharField(blank=True, help_text='Passwort für den Config-WLAN-Hotspot (MCC_XXXX). Minimum 8 Zeichen (WPA2-Anforderung).', max_length=64, null=True, verbose_name='Config-WLAN-Passwort'),
        ),
    ]
