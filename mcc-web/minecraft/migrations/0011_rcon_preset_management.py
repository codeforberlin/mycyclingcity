from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


SYSTEM_PRESET_SLUGS = (
    "day-clear",
    "day-cycle",
    "noon",
    "night",
    "city-gamerules",
)


def mark_system_presets(apps, schema_editor):
    preset_model = apps.get_model("minecraft", "MinecraftRconPreset")
    preset_model.objects.filter(slug__in=SYSTEM_PRESET_SLUGS).update(is_system=True)
    preset_model.objects.filter(slug="city-gamerules").update(moderator_can_run=True)


def unmark_system_presets(apps, schema_editor):
    preset_model = apps.get_model("minecraft", "MinecraftRconPreset")
    preset_model.objects.filter(slug__in=SYSTEM_PRESET_SLUGS).update(
        is_system=False,
        moderator_can_run=False,
    )


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("minecraft", "0010_update_city_gamerules_preset"),
    ]

    operations = [
        migrations.AddField(
            model_name="minecraftrconpreset",
            name="is_system",
            field=models.BooleanField(
                default=False,
                help_text="Von Migration geliefert; Löschen nur mit Sonderberechtigung.",
                verbose_name="System-Preset",
            ),
        ),
        migrations.AddField(
            model_name="minecraftrconpreset",
            name="moderator_can_run",
            field=models.BooleanField(
                default=False,
                help_text="Erlaubt Ausführung auch außerhalb der Kategorie „Welt & Wetter“.",
                verbose_name="Moderator darf ausführen",
            ),
        ),
        migrations.AddField(
            model_name="minecraftrconpreset",
            name="requires_confirmation",
            field=models.BooleanField(default=True, verbose_name="Bestätigung vor Ausführung"),
        ),
        migrations.AddField(
            model_name="minecraftrconpreset",
            name="stop_on_error",
            field=models.BooleanField(default=True, verbose_name="Bei Fehler abbrechen"),
        ),
        migrations.AddField(
            model_name="minecraftrconpreset",
            name="last_run_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Zuletzt ausgeführt"),
        ),
        migrations.AddField(
            model_name="minecraftrconpreset",
            name="last_run_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Zuletzt ausgeführt von",
            ),
        ),
        migrations.AddField(
            model_name="minecraftrconpreset",
            name="last_run_success",
            field=models.BooleanField(blank=True, null=True, verbose_name="Letzter Lauf erfolgreich"),
        ),
        migrations.AddField(
            model_name="minecraftrconpreset",
            name="last_run_output",
            field=models.TextField(blank=True, verbose_name="Letzte Ausgabe"),
        ),
        migrations.AlterModelOptions(
            name="minecraftrconpreset",
            options={
                "ordering": ["category", "sort_order", "name"],
                "permissions": [
                    ("run_rconpreset", "RCON-Presets ausführen"),
                    ("change_system_rconpreset", "System-Presets bearbeiten"),
                    ("delete_system_rconpreset", "System-Presets löschen"),
                    ("export_rconpreset", "RCON-Presets exportieren"),
                ],
                "verbose_name": "Minecraft RCON Preset",
                "verbose_name_plural": "Minecraft RCON Presets",
            },
        ),
        migrations.RunPython(mark_system_presets, unmark_system_presets),
    ]
