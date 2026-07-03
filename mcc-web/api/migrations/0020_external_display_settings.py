# Generated manually for external GUI km display settings.

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0019_velos_travel_progress'),
    ]

    operations = [
        migrations.CreateModel(
            name='ExternalDisplaySettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                (
                    'show_km_in_leaderboard_footer',
                    models.BooleanField(
                        default=True,
                        help_text='Zeigt die Summe der Kilometer (HourlyMetric) neben den Velos im Footer von Leaderboard und Kiosk-Leaderboard an.',
                        verbose_name='Kilometer im Leaderboard-Footer',
                    ),
                ),
                (
                    'show_km_in_ranking_headers',
                    models.BooleanField(
                        default=True,
                        help_text='Zeigt Kilometer zusätzlich zu Velos in den Kopfzeilen der Ranking-Hierarchie.',
                        verbose_name='Kilometer in Ranking-Gruppenköpfen',
                    ),
                ),
                (
                    'km_display_decimals',
                    models.IntegerField(
                        default=1,
                        help_text='Anzahl Dezimalstellen für Kilometer-Anzeigen in externen GUIs (0–2).',
                        validators=[MinValueValidator(0), MaxValueValidator(2)],
                        verbose_name='Kilometer Dezimalstellen',
                    ),
                ),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Aktualisiert am')),
            ],
            options={
                'verbose_name': 'Externe GUI-Anzeige',
                'verbose_name_plural': 'Externe GUI-Anzeige',
            },
        ),
    ]
