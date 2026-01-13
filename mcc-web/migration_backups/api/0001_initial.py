# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    0001_initial.py
# @author  Roland Rutz

#
import django.core.validators
import django.db.models.deletion
import django.utils.timezone
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Cyclist',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('user_id', models.CharField(max_length=20, verbose_name='Symbolischer Name')),
                ('avatar', models.ImageField(blank=True, null=True, upload_to='cyclist_avatars/', verbose_name='Radler Avatar')),
                ('id_tag', models.CharField(max_length=50, unique=True, verbose_name='RFID-UID')),
                ('mc_username', models.CharField(blank=True, max_length=100, null=True, verbose_name='Minecraft-Name')),
                ('distance_total', models.DecimalField(decimal_places=5, default=Decimal('0.00000'), max_digits=15, verbose_name='Gesamt-KM')),
                ('coins_total', models.IntegerField(default=0, verbose_name='Gesamt-Coins')),
                ('coins_spendable', models.IntegerField(default=0, verbose_name='Ausgebbare Coins')),
                ('coin_conversion_factor', models.FloatField(default=100.0, verbose_name='Coin-Faktor')),
                ('last_active', models.DateTimeField(blank=True, null=True, verbose_name='Zuletzt aktiv')),
                ('is_visible', models.BooleanField(default=True, verbose_name='In Map/Game anzeigen')),
                ('is_km_collection_enabled', models.BooleanField(default=True, help_text='Wenn deaktiviert, werden keine Kilometer für diesen Radler erfasst', verbose_name='Kilometer-Erfassung aktiv')),
            ],
            options={
                'verbose_name': 'Cyclist',
                'verbose_name_plural': 'Cyclists',
            },
        ),
        migrations.CreateModel(
            name='Event',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200, verbose_name='Event-Name')),
                ('event_type', models.CharField(choices=[('school_festival', 'Schulfest'), ('celebration', 'Feier'), ('fundraising', 'Spendensammeln'), ('competition', 'Wettbewerb'), ('other', 'Sonstiges')], default='other', max_length=50, verbose_name='Event-Typ')),
                ('description', models.TextField(blank=True, null=True, verbose_name='Beschreibung')),
                ('is_active', models.BooleanField(default=True, verbose_name='Aktiv')),
                ('is_visible_on_map', models.BooleanField(default=True, verbose_name='In Map/Game anzeigen')),
                ('start_time', models.DateTimeField(blank=True, null=True, verbose_name='Startzeitpunkt')),
                ('end_time', models.DateTimeField(blank=True, null=True, verbose_name='Endzeitpunkt')),
                ('hide_after_date', models.DateTimeField(blank=True, help_text='Events werden nach diesem Datum nicht mehr in der Karte angezeigt, auch wenn sie noch aktiv sind', null=True, verbose_name='Ab diesem Datum nicht mehr anzeigen')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Erstellt am')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Aktualisiert am')),
            ],
            options={
                'verbose_name': 'Event',
                'verbose_name_plural': 'Events',
                'ordering': ['-start_time', 'name'],
            },
        ),
        migrations.CreateModel(
            name='GroupType',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=50, unique=True, verbose_name='Typ-Name')),
                ('description', models.TextField(blank=True, null=True, verbose_name='Beschreibung')),
                ('is_active', models.BooleanField(default=True, verbose_name='Aktiv')),
            ],
            options={
                'verbose_name': 'Group Type',
                'verbose_name_plural': 'Group Types',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='LeafGroupTravelContribution',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('current_travel_distance', models.DecimalField(decimal_places=5, default=Decimal('0.00000'), help_text='Die von dieser Leaf-Gruppe während der aktuellen Reise zurückgelegte Distanz', max_digits=15, verbose_name='Aktuelle Reise-Distanz (km)')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Aktualisiert am')),
            ],
            options={
                'verbose_name': 'Leaf-Gruppe Reise-Beitrag',
                'verbose_name_plural': 'Leaf-Gruppe Reise-Beiträge',
            },
        ),
        migrations.CreateModel(
            name='MapPopupSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('weltmeister_popup_duration_seconds', models.IntegerField(default=6, help_text='Anzeigedauer des Kilometer-Weltmeister Popups in Sekunden (1-300)', validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(300)], verbose_name='Kilometer-Weltmeister Popup Dauer (Sekunden)')),
                ('milestone_popup_duration_seconds', models.IntegerField(default=30, help_text='Anzeigedauer des Meilenstein Popups in Sekunden (1-300)', validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(300)], verbose_name='Meilenstein Popup Dauer (Sekunden)')),
                ('weltmeister_popup_background_color', models.CharField(default='#ffd700', help_text='Hintergrundfarbe des Kilometer-Weltmeister Popups (Hex-Farbe, z.B. #ffd700 für Gold)', max_length=7, verbose_name='Kilometer-Weltmeister Popup Hintergrundfarbe')),
                ('weltmeister_popup_background_color_end', models.CharField(default='#ffed4e', help_text='Endfarbe für den Gradient-Hintergrund (Hex-Farbe, z.B. #ffed4e für helles Gold)', max_length=7, verbose_name='Kilometer-Weltmeister Popup Hintergrundfarbe Ende (Gradient)')),
                ('weltmeister_popup_opacity', models.DecimalField(decimal_places=2, default=1.0, help_text='Transparenz des Kilometer-Weltmeister Popups (0.01 = fast transparent, 1.00 = vollständig opak)', max_digits=3, validators=[django.core.validators.MinValueValidator(0.01), django.core.validators.MaxValueValidator(1.0)], verbose_name='Kilometer-Weltmeister Popup Transparenz')),
                ('milestone_popup_background_color', models.CharField(default='#007bff', help_text='Hintergrundfarbe des Meilenstein Popups (Hex-Farbe, z.B. #007bff für Blau)', max_length=7, verbose_name='Meilenstein Popup Hintergrundfarbe')),
                ('milestone_popup_opacity', models.DecimalField(decimal_places=2, default=1.0, help_text='Transparenz des Meilenstein Popups (0.01 = fast transparent, 1.00 = vollständig opak)', max_digits=3, validators=[django.core.validators.MinValueValidator(0.01), django.core.validators.MaxValueValidator(1.0)], verbose_name='Meilenstein Popup Transparenz')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Aktualisiert am')),
            ],
            options={
                'verbose_name': 'Map Popup Einstellungen',
                'verbose_name_plural': 'Map Popup Einstellungen',
            },
        ),
        migrations.CreateModel(
            name='Milestone',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, verbose_name='Bezeichnung')),
                ('description', models.TextField(blank=True, null=True, verbose_name='Beschreibung')),
                ('external_link', models.URLField(blank=True, null=True, verbose_name='Info-Link')),
                ('reward_text', models.CharField(blank=True, max_length=200, null=True, verbose_name='Belohnung')),
                ('distance_km', models.DecimalField(decimal_places=5, default=Decimal('0.00000'), max_digits=15, verbose_name='KM-Marke')),
                ('gps_latitude', models.DecimalField(decimal_places=6, max_digits=8, verbose_name='Breitengrad')),
                ('gps_longitude', models.DecimalField(decimal_places=6, max_digits=9, verbose_name='Längengrad')),
                ('reached_at', models.DateTimeField(blank=True, null=True, verbose_name='Erreicht am')),
            ],
            options={
                'verbose_name': 'Travels - Milestone',
                'verbose_name_plural': 'Travels - Milestones',
                'ordering': ['distance_km'],
            },
        ),
        migrations.CreateModel(
            name='TravelHistory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('start_time', models.DateTimeField(verbose_name='Startzeitpunkt')),
                ('end_time', models.DateTimeField(verbose_name='Endzeitpunkt')),
                ('total_distance_km', models.DecimalField(decimal_places=5, default=Decimal('0.00000'), max_digits=15, verbose_name='Gesammelte Kilometer')),
                ('action_type', models.CharField(choices=[('assigned', 'Zuordnung'), ('aborted', 'Abgebrochen'), ('completed', 'Beendet'), ('restarted', 'Neu gestartet'), ('removed', 'Entfernt')], default='completed', help_text='Art der Aktion, die zu diesem Historieeintrag geführt hat', max_length=20, verbose_name='Aktionstyp')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Erstellt am')),
            ],
            options={
                'verbose_name': 'Travels - History',
                'verbose_name_plural': 'Travels - Histories',
                'ordering': ['-end_time'],
            },
        ),
        migrations.CreateModel(
            name='TravelTrack',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, verbose_name='Name der Route')),
                ('track_file', models.FileField(blank=True, null=True, upload_to='tracks/', verbose_name='GPX-Datei')),
                ('geojson_data', models.TextField(blank=True, verbose_name='GeoJSON Daten')),
                ('total_length_km', models.DecimalField(decimal_places=5, default=Decimal('0.00000'), max_digits=15, verbose_name='Gesamtlänge (km)')),
                ('is_active', models.BooleanField(default=True, verbose_name='Aktiv')),
                ('is_visible_on_map', models.BooleanField(default=True, verbose_name='Auf Karte anzeigen')),
                ('auto_start', models.BooleanField(default=False, help_text='Wenn aktiviert, startet die Reise automatisch beim Eintreffen der ersten Kilometer. Wenn deaktiviert, muss eine Startzeit definiert werden.', verbose_name='Automatischer Start')),
                ('start_time', models.DateTimeField(blank=True, help_text="Optional: Definiert den Startzeitpunkt der Reise. Wird ignoriert, wenn 'Automatischer Start' aktiviert ist.", null=True, verbose_name='Startzeitpunkt')),
                ('end_time', models.DateTimeField(blank=True, help_text='Optional: Definiert den Endzeitpunkt der Reise. Wenn nicht gesetzt, läuft die Reise unbegrenzt.', null=True, verbose_name='Endzeitpunkt')),
            ],
            options={
                'verbose_name': 'Travels - Route',
                'verbose_name_plural': 'Travels - Routes',
            },
        ),
        migrations.CreateModel(
            name='CyclistDeviceCurrentMileage',
            fields=[
                ('cyclist', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, primary_key=True, serialize=False, to='api.cyclist', verbose_name='Radler')),
                ('cumulative_mileage', models.DecimalField(decimal_places=5, default=Decimal('0.00000'), max_digits=15, verbose_name='Sitzungs-Distanz (km)')),
                ('start_time', models.DateTimeField(default=django.utils.timezone.now, verbose_name='Startzeit')),
                ('last_activity', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Cyclist - Active Session',
                'verbose_name_plural': 'Cyclists - Active Sessions',
            },
        ),
        migrations.CreateModel(
            name='Group',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, verbose_name='Gruppenname')),
                ('distance_total', models.DecimalField(decimal_places=5, default=Decimal('0.00000'), max_digits=15, verbose_name='Gesamt-KM')),
                ('coins_total', models.IntegerField(default=0, verbose_name='Gesamt-Coins')),
                ('logo', models.ImageField(blank=True, null=True, upload_to='group_logos/', verbose_name='Logo für Karte')),
                ('comments', models.TextField(blank=True, null=True, verbose_name='Interne Kommentare (Admin)')),
                ('is_visible', models.BooleanField(default=True, verbose_name='In Map/Game anzeigen')),
                ('short_name', models.CharField(blank=True, help_text='Wird auf den Kiosk-Kacheln verwendet', max_length=15, null=True, verbose_name='Kurzname (z.B. 1a)')),
                ('color', models.CharField(blank=True, help_text="Hex-Farbcode (z.B. #3b82f6) für die Darstellung im Kiosk-Leaderboard. Wird für alle Untergruppen verwendet. Farbwähler: <a href='https://htmlcolorcodes.com/color-picker/' target='_blank'>HTML Color Codes</a> | <a href='https://colorpicker.me/' target='_blank'>Color Picker</a> | <a href='https://coolors.co/' target='_blank'>Coolors</a>", max_length=7, null=True, verbose_name='Farbe (Hex-Code)')),
                ('managers', models.ManyToManyField(blank=True, related_name='managed_groups', to=settings.AUTH_USER_MODEL, verbose_name='Manager')),
                ('parent', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='children', to='api.group', verbose_name='Übergeordnete Gruppe')),
                ('group_type', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='groups', to='api.grouptype', verbose_name='Gruppentyp')),
            ],
            options={
                'verbose_name': 'Group',
                'verbose_name_plural': 'Groups',
            },
        ),
        migrations.CreateModel(
            name='EventHistory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('start_time', models.DateTimeField(verbose_name='Startzeitpunkt')),
                ('end_time', models.DateTimeField(verbose_name='Endzeitpunkt')),
                ('total_distance_km', models.DecimalField(decimal_places=5, default=Decimal('0.00000'), max_digits=15, verbose_name='Gesammelte Kilometer')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Erstellt am')),
                ('event', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='history_entries', to='api.event', verbose_name='Event')),
                ('group', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='event_history', to='api.group', verbose_name='Gruppe')),
            ],
            options={
                'verbose_name': 'Events - History',
                'verbose_name_plural': 'Events - Histories',
                'ordering': ['-end_time'],
            },
        ),
        migrations.AddField(
            model_name='cyclist',
            name='groups',
            field=models.ManyToManyField(blank=True, related_name='members', to='api.group', verbose_name='Gruppen'),
        ),
        migrations.CreateModel(
            name='GroupEventStatus',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('current_distance_km', models.DecimalField(decimal_places=5, default=Decimal('0.00000'), max_digits=15, verbose_name='Aktuelle Distanz (km)')),
                ('start_km_offset', models.DecimalField(decimal_places=5, default=Decimal('0.00000'), max_digits=15, verbose_name='Start-Offset (km)')),
                ('joined_at', models.DateTimeField(auto_now_add=True, verbose_name='Beigetreten am')),
                ('event', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='group_statuses', to='api.event', verbose_name='Event')),
                ('group', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='event_statuses', to='api.group', verbose_name='Gruppe')),
            ],
            options={
                'verbose_name': 'Gruppen-Event-Status',
                'verbose_name_plural': 'Gruppen-Event-Status',
            },
        ),
        migrations.CreateModel(
            name='GroupMilestoneAchievement',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('reached_at', models.DateTimeField(verbose_name='Erreicht am')),
                ('reached_distance', models.DecimalField(blank=True, decimal_places=5, max_digits=15, null=True, verbose_name='Erreichte Distanz (km)')),
                ('reward_text', models.CharField(blank=True, help_text='Die Belohnung, die zum Zeitpunkt des Erreichens des Meilensteins definiert war. Diese bleibt unverändert, auch wenn die Meilenstein-Belohnung später geändert wird.', max_length=200, null=True, verbose_name='Belohnung')),
                ('is_redeemed', models.BooleanField(default=False, help_text='Gibt an, ob die Belohnung bereits eingelöst wurde. Eine Belohnung kann nur einmal eingelöst werden.', verbose_name='Eingelöst')),
                ('redeemed_at', models.DateTimeField(blank=True, help_text='Zeitpunkt, zu dem die Belohnung eingelöst wurde.', null=True, verbose_name='Eingelöst am')),
                ('group', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='milestone_achievements', to='api.group', verbose_name='Gruppe')),
            ],
            options={
                'verbose_name': 'Reisen - erreichte Meilensteine',
                'verbose_name_plural': 'Reisen - erreichte Meilensteine',
                'ordering': ['-reached_at'],
            },
        ),
        migrations.CreateModel(
            name='GroupTravelStatus',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('current_travel_distance', models.DecimalField(decimal_places=5, default=Decimal('0.00000'), max_digits=15, verbose_name='Aktuelle Reisen-Distanz (km)')),
                ('start_km_offset', models.DecimalField(decimal_places=5, default=Decimal('0.00000'), max_digits=15, verbose_name='Start-Offset (km)')),
                ('goal_reached_at', models.DateTimeField(blank=True, help_text='Zeitpunkt, zu dem die Gruppe das Ziel erreicht hat. Wird für die Sortierung am Ziel verwendet.', null=True, verbose_name='Ziel erreicht am')),
                ('group', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='travel_status', to='api.group', verbose_name='Gruppe')),
            ],
            options={
                'verbose_name': 'Travels - Status',
                'verbose_name_plural': 'Travels - Status',
            },
        ),
        migrations.CreateModel(
            name='HourlyMetric',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('timestamp', models.DateTimeField(db_index=True, verbose_name='Zeitpunkt')),
                ('distance_km', models.DecimalField(decimal_places=5, max_digits=15, verbose_name='Intervall-Distanz (km)')),
                ('cyclist', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='metrics', to='api.cyclist', verbose_name='Radler')),
            ],
            options={
                'verbose_name': 'Hourly Metric',
                'verbose_name_plural': 'Hourly Metrics',
            },
        ),
    ]
