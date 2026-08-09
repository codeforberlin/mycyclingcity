# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    models.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

"""Models for dynamo display settings and battery charge targets."""

from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from dynamo.physics import (
    DEFAULT_CHARGER_EFFICIENCY,
    DEFAULT_POWER_CAP_W,
    DEFAULT_POWER_CURVE,
    CHARGER_PROFILE_KEYS,
)


def _default_power_curve():
    return [{'speed_kmh': v, 'power_w': p} for v, p in DEFAULT_POWER_CURVE]


def _default_appliance_equivalents():
    return [
        {'key': 'led_lamp', 'label': 'LED-Lampe', 'watts': 10},
        {'key': 'radio', 'label': 'Radio', 'watts': 15},
        {'key': 'console', 'label': 'Spielkonsole', 'watts': 50},
        {'key': 'fan', 'label': 'Ventilator', 'watts': 40},
    ]


def _default_charger_efficiency_profiles():
    """Admin-editable η(v) curves for generic charger classes (no brand names)."""
    profiles = {}
    for key in CHARGER_PROFILE_KEYS:
        profiles[key] = [
            {'speed_kmh': v, 'efficiency': e}
            for v, e in DEFAULT_CHARGER_EFFICIENCY[key]
        ]
    return profiles


class DynamoDisplaySettings(models.Model):
    """Singleton settings for the public dynamo energy GUI."""

    update_interval_seconds = models.IntegerField(
        default=5,
        validators=[MinValueValidator(2), MaxValueValidator(120)],
        verbose_name=_("Aktualisierungsintervall (Sekunden)"),
        help_text=_("Polling-Intervall für die Dynamo-Live-Anzeige."),
    )
    power_cap_w = models.FloatField(
        default=DEFAULT_POWER_CAP_W,
        validators=[MinValueValidator(0.1), MaxValueValidator(50.0)],
        verbose_name=_("Leistungs-Cap (Watt)"),
        help_text=_("Maximale Nabendynamo-Leistung in der pädagogischen Kennlinie."),
    )
    power_curve = models.JSONField(
        default=_default_power_curve,
        verbose_name=_("Leistungs-Kennlinie"),
        help_text=_(
            "Liste von Punkten {speed_kmh, power_w} für die virtuelle Dynamo-Kennlinie."
        ),
    )
    high_power_threshold_w = models.FloatField(
        default=4.0,
        validators=[MinValueValidator(0.1), MaxValueValidator(50.0)],
        verbose_name=_("High-Power-Schwelle (Watt)"),
        help_text=_("Ab dieser Momentanleistung wird ein Tempo-Blitz angezeigt."),
    )
    assumed_speed_kmh_for_estimates = models.FloatField(
        default=12.0,
        validators=[MinValueValidator(1.0), MaxValueValidator(40.0)],
        verbose_name=_("Annahme-Geschwindigkeit für Schätzungen (km/h)"),
        help_text=_(
            "Wird genutzt, wenn Energie aus Distanz ohne Intervallgeschwindigkeit "
            "geschätzt werden muss (z. B. Alt-Daten)."
        ),
    )
    appliance_equivalents = models.JSONField(
        default=_default_appliance_equivalents,
        verbose_name=_("Geräte-Äquivalente"),
        help_text=_(
            "Liste {key, label, watts} für „Was könnte man betreiben?“."
        ),
    )
    show_cyclist_ride_stats = models.BooleanField(
        default=True,
        verbose_name=_("Velos und Kilometer bei aktiven Radlern"),
        help_text=_(
            "Zeigt Session-Velos und Session-Kilometer auf den Kacheln der aktiven Radler. "
            "Per URL überschreibbar: ?ride_stats=1 oder ?ride_stats=0."
        ),
    )
    enable_charger_compare = models.BooleanField(
        default=True,
        verbose_name=_("Ladegerät-Vergleich (Profi)"),
        help_text=_(
            "Erlaubt Umschalten auf generische Ladegerät-Klassen "
            "(Einfach / Standard / Optimiert). Gespeicherte Wh bleiben Dynamo-Rohwerte. "
            "URL: ?charger=direct|simple|standard|optimized"
        ),
    )
    charger_efficiency_profiles = models.JSONField(
        default=_default_charger_efficiency_profiles,
        verbose_name=_("Ladegerät-Wirkungsgrade"),
        help_text=_(
            "Generische η(v)-Kennlinien ohne Markennamen: "
            "{direct|simple|standard|optimized: [{speed_kmh, efficiency}, ...]}."
        ),
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Aktualisiert am"))

    class Meta:
        verbose_name = _("Dynamo-Anzeige")
        verbose_name_plural = _("Dynamo-Anzeige")
        permissions = [
            ('manage_dynamo_display', _('Kann Dynamo-Anzeige konfigurieren')),
        ]

    def __str__(self):
        return str(_("Dynamo-Anzeige-Einstellungen"))

    @classmethod
    def get_settings(cls):
        """Get or create the singleton settings instance."""
        settings_obj, _ = cls.objects.get_or_create(pk=1)
        return settings_obj


class DynamoBatteryTarget(models.Model):
    """Battery capacity target shown as a charge bar on the dynamo GUI."""

    name = models.CharField(max_length=100, verbose_name=_("Name"))
    capacity_wh = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0.01)],
        verbose_name=_("Kapazität (Wh)"),
    )
    icon_key = models.CharField(
        max_length=50,
        default='battery',
        verbose_name=_("Icon-Schlüssel"),
        help_text=_("CSS/Template-Schlüssel, z. B. phone, tablet, notebook, ebike, house."),
    )
    sort_order = models.PositiveIntegerField(default=0, verbose_name=_("Sortierung"))
    is_active = models.BooleanField(default=True, verbose_name=_("Aktiv"))
    use_daily_energy = models.BooleanField(
        default=True,
        verbose_name=_("Tagesenergie verwenden"),
        help_text=_(
            "Wenn aktiv: Füllstand aus heutiger Gruppen-Energie. "
            "Sonst aus Session-Summe der aktiven Radler."
        ),
    )

    class Meta:
        verbose_name = _("Dynamo-Akku-Ziel")
        verbose_name_plural = _("Dynamo-Akku-Ziele")
        ordering = ['sort_order', 'capacity_wh', 'name']
        permissions = [
            ('manage_dynamo_batteries', _('Kann Dynamo-Akku-Ziele verwalten')),
        ]

    def __str__(self):
        return f"{self.name} ({self.capacity_wh} Wh)"
