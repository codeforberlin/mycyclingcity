from django.db import migrations, models


DEFAULT_PRESETS = [
    {
        "slug": "day-clear",
        "name": "Tag & schönes Wetter",
        "category": "world",
        "sort_order": 10,
        "description": "Heller Tag, klares Wetter, Tageszyklus pausiert.",
        "commands": ["time set day", "weather clear", "gamerule doDaylightCycle false"],
    },
    {
        "slug": "day-cycle",
        "name": "Tag mit Tageszyklus",
        "category": "world",
        "sort_order": 20,
        "description": "Tag, klares Wetter, Tageszyklus läuft weiter.",
        "commands": ["time set day", "weather clear", "gamerule doDaylightCycle true"],
    },
    {
        "slug": "noon",
        "name": "Mittag (bestes Licht)",
        "category": "world",
        "sort_order": 30,
        "description": "Mittagshelligkeit für Screenshots und Präsentationen.",
        "commands": ["time set noon", "weather clear", "gamerule doDaylightCycle false"],
    },
    {
        "slug": "night",
        "name": "Nacht für Präsentation",
        "category": "world",
        "sort_order": 40,
        "description": "Nacht, klares Wetter, Tageszyklus pausiert.",
        "commands": ["time set night", "weather clear", "gamerule doDaylightCycle false"],
    },
    {
        "slug": "city-gamerules",
        "name": "Stadtmodus (Spielregeln)",
        "category": "gamerule",
        "sort_order": 10,
        "description": "Schützt Bauwerke: keine Mob-Zerstörung, kein Feuer, Inventar behalten.",
        "commands": [
            "gamerule mobGriefing false",
            "gamerule doFireTick false",
            "gamerule keepInventory true",
        ],
    },
]


def seed_default_presets(apps, schema_editor):
    preset_model = apps.get_model("minecraft", "MinecraftRconPreset")
    for data in DEFAULT_PRESETS:
        preset_model.objects.update_or_create(
            slug=data["slug"],
            defaults={
                "name": data["name"],
                "category": data["category"],
                "sort_order": data["sort_order"],
                "description": data["description"],
                "commands": data["commands"],
                "enabled": True,
            },
        )


def unseed_default_presets(apps, schema_editor):
    preset_model = apps.get_model("minecraft", "MinecraftRconPreset")
    slugs = [item["slug"] for item in DEFAULT_PRESETS]
    preset_model.objects.filter(slug__in=slugs).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("minecraft", "0007_bridge_connection"),
    ]

    operations = [
        migrations.CreateModel(
            name="MinecraftRconPreset",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("slug", models.SlugField(max_length=64, unique=True, verbose_name="Slug")),
                ("name", models.CharField(max_length=64, verbose_name="Name")),
                (
                    "category",
                    models.CharField(
                        choices=[
                            ("world", "Welt & Wetter"),
                            ("gamerule", "Spielregeln"),
                            ("other", "Sonstiges"),
                        ],
                        default="world",
                        max_length=32,
                        verbose_name="Kategorie",
                    ),
                ),
                ("description", models.TextField(blank=True, verbose_name="Beschreibung")),
                (
                    "commands",
                    models.JSONField(
                        default=list,
                        help_text="Liste von Befehlen, die nacheinander ausgeführt werden.",
                        verbose_name="RCON-Befehle",
                    ),
                ),
                ("sort_order", models.PositiveIntegerField(default=0, verbose_name="Sortierung")),
                ("enabled", models.BooleanField(default=True, verbose_name="Aktiv")),
            ],
            options={
                "verbose_name": "Minecraft RCON Preset",
                "verbose_name_plural": "Minecraft RCON Presets",
                "ordering": ["category", "sort_order", "name"],
            },
        ),
        migrations.RunPython(seed_default_presets, unseed_default_presets),
    ]
