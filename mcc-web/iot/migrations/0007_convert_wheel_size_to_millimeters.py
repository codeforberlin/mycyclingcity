# Generated manually for wheel_size conversion from inches to millimeters
# Copyright (c) 2026 SAI-Lab / MyCyclingCity

from django.db import migrations, models
from django.core.validators import MinValueValidator, MaxValueValidator


def convert_inches_to_millimeters(apps, schema_editor):
    """Convert wheel_size from inches (20, 24, 26, 28) to millimeters (circumference)."""
    DeviceConfiguration = apps.get_model('iot', 'DeviceConfiguration')
    
    # Conversion table: inches -> circumference in mm
    # 20 inches: 159.6 cm = 1596 mm
    # 24 inches: 191.6 cm = 1916 mm
    # 26 inches: 207.5 cm = 2075 mm
    # 28 inches: 223.2 cm = 2232 mm
    conversion_map = {
        20: 1596.0,
        24: 1916.0,
        26: 2075.0,
        28: 2232.0,
    }
    
    for config in DeviceConfiguration.objects.all():
        old_value = config.wheel_size
        if old_value in conversion_map:
            config.wheel_size = conversion_map[old_value]
            config.save(update_fields=['wheel_size'])


def reverse_convert_millimeters_to_inches(apps, schema_editor):
    """Reverse conversion: millimeters to inches (for rollback)."""
    DeviceConfiguration = apps.get_model('iot', 'DeviceConfiguration')
    
    # Reverse conversion: find closest inch value
    # 1596 mm -> 20 inches
    # 1916 mm -> 24 inches
    # 2075 mm -> 26 inches
    # 2232 mm -> 28 inches
    reverse_map = {
        1596.0: 20,
        1916.0: 24,
        2075.0: 26,
        2232.0: 28,
    }
    
    for config in DeviceConfiguration.objects.all():
        old_value = config.wheel_size
        # Find closest match (with tolerance)
        closest_inch = None
        min_diff = float('inf')
        for mm_value, inch_value in reverse_map.items():
            diff = abs(old_value - mm_value)
            if diff < min_diff and diff < 10.0:  # 10mm tolerance
                min_diff = diff
                closest_inch = inch_value
        
        if closest_inch:
            config.wheel_size = closest_inch
            config.save(update_fields=['wheel_size'])


class Migration(migrations.Migration):

    dependencies = [
        ('iot', '0006_alter_deviceconfiguration_previous_api_key_and_more'),
    ]

    operations = [
        # Step 1: Convert data from inches to millimeters
        migrations.RunPython(convert_inches_to_millimeters, reverse_convert_millimeters_to_inches),
        
        # Step 2: Change field type from IntegerField to FloatField
        migrations.AlterField(
            model_name='deviceconfiguration',
            name='wheel_size',
            field=models.FloatField(
                default=2075.0,
                help_text='Radumfang in Millimeter für Distanzberechnung. Gültiger Bereich: 500-3000 mm. Standard-Tachowerte können aus Hersteller-Tabellen entnommen werden (z.B. Sigma).',
                validators=[
                    MinValueValidator(500.0, message='Radumfang muss mindestens 500 mm betragen'),
                    MaxValueValidator(3000.0, message='Radumfang darf maximal 3000 mm betragen')
                ],
                verbose_name='Radumfang (mm)'
            ),
        ),
    ]
