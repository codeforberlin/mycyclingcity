# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    0013_add_popup_colors_and_opacity.py
# @author  Roland Rutz

#
import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0012_add_map_popup_settings'),
    ]

    operations = [
        migrations.AddField(
            model_name='mappopupsettings',
            name='milestone_popup_background_color',
            field=models.CharField(default='#007bff', help_text='Hintergrundfarbe des Meilenstein Popups (Hex-Farbe, z.B. #007bff für Blau)', max_length=7, verbose_name='Meilenstein Popup Hintergrundfarbe'),
        ),
        migrations.AddField(
            model_name='mappopupsettings',
            name='milestone_popup_opacity',
            field=models.DecimalField(decimal_places=2, default=1.0, help_text='Transparenz des Meilenstein Popups (0.01 = fast transparent, 1.00 = vollständig opak)', max_digits=3, validators=[django.core.validators.MinValueValidator(0.01), django.core.validators.MaxValueValidator(1.0)], verbose_name='Meilenstein Popup Transparenz'),
        ),
        migrations.AddField(
            model_name='mappopupsettings',
            name='weltmeister_popup_background_color',
            field=models.CharField(default='#ffd700', help_text='Hintergrundfarbe des Kilometer-Weltmeister Popups (Hex-Farbe, z.B. #ffd700 für Gold)', max_length=7, verbose_name='Kilometer-Weltmeister Popup Hintergrundfarbe'),
        ),
        migrations.AddField(
            model_name='mappopupsettings',
            name='weltmeister_popup_background_color_end',
            field=models.CharField(default='#ffed4e', help_text='Endfarbe für den Gradient-Hintergrund (Hex-Farbe, z.B. #ffed4e für helles Gold)', max_length=7, verbose_name='Kilometer-Weltmeister Popup Hintergrundfarbe Ende (Gradient)'),
        ),
        migrations.AddField(
            model_name='mappopupsettings',
            name='weltmeister_popup_opacity',
            field=models.DecimalField(decimal_places=2, default=1.0, help_text='Transparenz des Kilometer-Weltmeister Popups (0.01 = fast transparent, 1.00 = vollständig opak)', max_digits=3, validators=[django.core.validators.MinValueValidator(0.01), django.core.validators.MaxValueValidator(1.0)], verbose_name='Kilometer-Weltmeister Popup Transparenz'),
        ),
    ]
