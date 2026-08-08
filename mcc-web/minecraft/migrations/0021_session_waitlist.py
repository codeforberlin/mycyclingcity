import secrets

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def ensure_waitlist_tokens(apps, schema_editor):
    config_model = apps.get_model("minecraft", "MinecraftIntegrationConfig")
    for config in config_model.objects.all():
        if not (config.waitlist_public_token or "").strip():
            config.waitlist_public_token = secrets.token_urlsafe(24)
            config.save(update_fields=["waitlist_public_token"])


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("minecraft", "0020_builder_session_bootstrap_preset"),
    ]

    operations = [
        migrations.AddField(
            model_name="minecraftintegrationconfig",
            name="player_min_velos",
            field=models.PositiveIntegerField(
                default=300,
                help_text="Mindestbetrag für eine Spiel-Session aus der Warteliste.",
                verbose_name="Mindest-Velos Spiel-Warteliste",
            ),
        ),
        migrations.AddField(
            model_name="minecraftintegrationconfig",
            name="player_velos_per_minute",
            field=models.PositiveIntegerField(
                default=20,
                help_text="Beispiel: 300 Velos ÷ 20 = 15 Minuten Minecraft-Spielzeit.",
                verbose_name="Velos pro Spielminute",
            ),
        ),
        migrations.AddField(
            model_name="minecraftintegrationconfig",
            name="waitlist_public_enabled",
            field=models.BooleanField(
                default=False,
                help_text="Erlaubt die anonyme Live-Anzeige per Token-URL (nur Ticket-Nummern, keine Namen).",
                verbose_name="Öffentliche Wartelisten-Anzeige aktiv",
            ),
        ),
        migrations.AddField(
            model_name="minecraftintegrationconfig",
            name="waitlist_public_token",
            field=models.CharField(
                blank=True,
                help_text="Geheimer Token für die öffentliche Display-URL. Leer = automatisch generieren.",
                max_length=64,
                verbose_name="Token öffentliche Anzeige",
            ),
        ),
        migrations.CreateModel(
            name="MinecraftSessionWaitlistEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "queue_type",
                    models.CharField(
                        choices=[("player", "Spieler (Arena)"), ("builder", "Bau-Team")],
                        db_index=True,
                        max_length=16,
                        verbose_name="Wartelisten-Typ",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("waiting", "Wartend"),
                            ("active", "Aktiv"),
                            ("done", "Erledigt"),
                            ("cancelled", "Abgebrochen"),
                        ],
                        db_index=True,
                        default="waiting",
                        max_length=16,
                        verbose_name="Status",
                    ),
                ),
                (
                    "ticket_number",
                    models.CharField(
                        db_index=True,
                        help_text="Anonyme Kennung vom Flyer (öffentliche Anzeige).",
                        max_length=16,
                        verbose_name="Ticket-Nummer",
                    ),
                ),
                (
                    "guest_label",
                    models.CharField(
                        blank=True,
                        help_text="Nur für Operatoren sichtbar, nicht auf öffentlicher Anzeige.",
                        max_length=120,
                        verbose_name="Interner Name",
                    ),
                ),
                ("velos_cost", models.PositiveIntegerField(default=0, verbose_name="Velos (Einlösung)")),
                ("duration_minutes", models.PositiveIntegerField(verbose_name="Session-Dauer (Min.)")),
                ("internal_note", models.CharField(blank=True, max_length=255, verbose_name="Interne Notiz")),
                ("queued_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Eingetragen am")),
                ("started_at", models.DateTimeField(blank=True, null=True, verbose_name="Gestartet am")),
                ("finished_at", models.DateTimeField(blank=True, null=True, verbose_name="Beendet am")),
                (
                    "assigned_builder_registration",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="waitlist_entries",
                        to="minecraft.minecraftteamregistration",
                        verbose_name="Zugewiesenes Bau-Team",
                    ),
                ),
                (
                    "assigned_play_account",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="waitlist_entries",
                        to="minecraft.minecraftplayaccount",
                        verbose_name="Zugewiesener Spiel-Account",
                    ),
                ),
                (
                    "mc_session",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="waitlist_entries",
                        to="minecraft.mcsession",
                        verbose_name="Minecraft-Session",
                    ),
                ),
                (
                    "queued_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Eingetragen von",
                    ),
                ),
                (
                    "started_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Gestartet von",
                    ),
                ),
            ],
            options={
                "verbose_name": "Session-Wartelisteneintrag",
                "verbose_name_plural": "Session-Warteliste",
                "ordering": ["queued_at"],
            },
        ),
        migrations.AddIndex(
            model_name="minecraftsessionwaitlistentry",
            index=models.Index(fields=["queue_type", "status", "queued_at"], name="minecraft_waitlist_q_status"),
        ),
        migrations.RunPython(ensure_waitlist_tokens, migrations.RunPython.noop),
    ]
