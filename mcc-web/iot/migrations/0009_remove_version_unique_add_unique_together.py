# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('iot', '0008_add_firmware_checksum_sha256_and_environment'),
    ]

    operations = [
        # Remove unique constraint from version
        migrations.AlterField(
            model_name='firmwareimage',
            name='version',
            field=models.CharField(help_text="Versionskennung (z.B. '1.2.3' oder 'v2.0.1')", max_length=50, verbose_name='Version'),
        ),
        # Add unique_together constraint on (version, environment)
        migrations.AlterUniqueTogether(
            name='firmwareimage',
            unique_together={('version', 'environment')},
        ),
    ]
