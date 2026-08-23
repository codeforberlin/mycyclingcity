# Generated manually — leaderboard footer km off by default; ranking help text.

from django.db import migrations, models


def disable_leaderboard_footer_km(apps, schema_editor):
    ExternalDisplaySettings = apps.get_model('api', 'ExternalDisplaySettings')
    ExternalDisplaySettings.objects.filter(pk=1).update(show_km_in_leaderboard_footer=False)


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0023_cyclistvelosredemption_redeem_permission'),
    ]

    operations = [
        migrations.AlterField(
            model_name='externaldisplaysettings',
            name='show_km_in_leaderboard_footer',
            field=models.BooleanField(
                default=False,
                help_text=(
                    'Zeigt die Summe der Kilometer (HourlyMetric) neben den Velos im Footer '
                    'von Leaderboard und Kiosk-Leaderboard an. Standard: aus — Leaderboard '
                    'zeigt nur Velos; offizielle Gesamt-km stehen im Ranking (Group.distance_total).'
                ),
                verbose_name='Kilometer im Leaderboard-Footer',
            ),
        ),
        migrations.AlterField(
            model_name='externaldisplaysettings',
            name='show_km_in_ranking_headers',
            field=models.BooleanField(
                default=True,
                help_text=(
                    'Zeigt Gesamt-km aus Group.distance_total zusätzlich zu Velos '
                    'in den Kopfzeilen der Ranking-Hierarchie.'
                ),
                verbose_name='Kilometer in Ranking-Gruppenköpfen',
            ),
        ),
        migrations.RunPython(disable_leaderboard_footer_km, migrations.RunPython.noop),
    ]
