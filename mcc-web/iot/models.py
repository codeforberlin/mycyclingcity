# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    models.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
from django.db import models
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal

class Device(models.Model):
    name = models.CharField(max_length=20, unique=True, verbose_name=_("Gerätename"))
    display_name = models.CharField(max_length=50, blank=True, null=True, verbose_name=_("Symbolischer Name (Anzeige)"))
    group = models.ForeignKey('api.Group', on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("Zugeordnete Gruppe"))
    distance_total = models.DecimalField(max_digits=15, decimal_places=5, default=Decimal('0.00000'), verbose_name=_("Laufleistung (km)"))
    gps_latitude = models.DecimalField(max_digits=8, decimal_places=6, null=True, blank=True, verbose_name=_("Breitengrad"))
    gps_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True, verbose_name=_("Längengrad"))
    last_active = models.DateTimeField(null=True, blank=True, verbose_name=_("Zuletzt aktiv"))

    last_reported_interval = models.DecimalField(max_digits=10, decimal_places=3, default=Decimal(0), verbose_name=_("Letztes Intervall (km)"))
    last_reported_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Letzter Bericht"))

    comments = models.TextField(blank=True, null=True, verbose_name=_("Interne Kommentare (Admin)"))

    class Meta:
        verbose_name = _("Device")
        verbose_name_plural = _("Devices")

    def __str__(self):
        return self.display_name if self.display_name else self.name

    is_visible = models.BooleanField(default=True, verbose_name=_("In Map/Game anzeigen"))
    is_km_collection_enabled = models.BooleanField(default=True, verbose_name=_("Kilometer-Erfassung aktiv"), help_text=_("Wenn deaktiviert, werden keine Kilometer für dieses Gerät erfasst"))


class DeviceConfiguration(models.Model):
    """Server-side configuration for ESP32 devices."""
    device = models.OneToOneField(
        Device,
        on_delete=models.CASCADE,
        related_name='configuration',
        verbose_name=_("Device")
    )
    
    # Authentication
    device_specific_api_key = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        unique=True,
        verbose_name=_("Geräte-API-Key"),
        help_text=_("Eindeutiger API-Key für dieses Gerät. Wenn nicht gesetzt, verwendet das Gerät den IoT Device Shared API Key (konfiguriert in Geräteverwaltungs-Einstellungen).")
    )
    
    api_key_rotation_enabled = models.BooleanField(
        default=False,
        verbose_name=_("API-Key-Rotation aktiviert"),
        help_text=_("API-Key automatisch im konfigurierten Intervall rotieren")
    )
    
    api_key_last_rotated = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("API-Key zuletzt rotiert"),
        help_text=_("Zeitstempel der letzten API-Key-Rotation")
    )
    
    api_key_rotation_interval_days = models.IntegerField(
        default=90,
        validators=[MinValueValidator(1)],
        verbose_name=_("API-Key-Rotations-Intervall (Tage)"),
        help_text=_("Anzahl der Tage zwischen automatischen API-Key-Rotationen")
    )
    
    # Grace period for API key rotation: old key remains valid until device authenticates with new key
    previous_api_key = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        verbose_name=_("Vorheriger API-Key"),
        help_text=_("Der vorherige API-Key bleibt gültig, bis das Gerät sich erfolgreich mit dem neuen Key authentifiziert hat. Wird automatisch gelöscht, sobald das Gerät den neuen Key verwendet.")
    )
    
    previous_api_key_expires_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Vorheriger API-Key läuft ab am (optional)"),
        help_text=_("Optional: Zeitpunkt für automatische Bereinigung abgelaufener Keys. Wenn nicht gesetzt, bleibt der Key gültig bis das Gerät den neuen Key verwendet.")
    )
    
    # Legacy: Apache Base64 Auth Key (deprecated, use device_specific_api_key instead)
    apache_base64_auth_key = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        verbose_name=_("Apache Base64 Auth Key (Veraltet)"),
        help_text=_("Base64-kodierter Authentifizierungsschlüssel für Apache Basic Auth (veraltet, verwenden Sie device_specific_api_key)")
    )
    
    # Device identification
    device_name = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name=_("Gerätename"),
        help_text=_("Name des Geräts, wie auf dem ESP32 konfiguriert")
    )
    
    default_id_tag = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name=_("Standard-ID-Tag"),
        help_text=_("Standard-ID-Tag-Name für dieses Gerät")
    )
    
    # Communication settings
    send_interval_seconds = models.IntegerField(
        default=60,
        validators=[MinValueValidator(1)],
        verbose_name=_("Sendeintervall (Sekunden)"),
        help_text=_("Intervall in Sekunden zwischen Datenübertragungen")
    )
    
    config_fetch_interval_seconds = models.IntegerField(
        default=3600,
        validators=[MinValueValidator(0)],
        verbose_name=_("Config-Abruf-Intervall (Sekunden)"),
        help_text=_("Intervall in Sekunden zum regelmäßigen Abrufen der Konfiguration vom Server. 0 = deaktiviert. Wird auch verwendet, wenn Deep Sleep deaktiviert ist.")
    )
    
    request_config_comparison = models.BooleanField(
        default=False,
        verbose_name=_("Konfigurationsvergleich anfordern"),
        help_text=_("Wenn aktiviert, wird beim nächsten Config-Report vom Gerät ein Vergleich durchgeführt und Unterschiede werden im Admin GUI angezeigt. Wird nach dem Vergleich automatisch zurückgesetzt.")
    )
    
    server_url = models.URLField(
        max_length=500,
        blank=True,
        null=True,
        verbose_name=_("Server-URL"),
        help_text=_("URL des Server-Endpunkts für Datenübertragung")
    )
    
    # WLAN settings (encrypted in database, but stored as plain text for device)
    wifi_ssid = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name=_("WLAN SSID"),
        help_text=_("WiFi-Netzwerkname (SSID)")
    )
    
    wifi_password = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name=_("WLAN-Passwort"),
        help_text=_("WiFi-Netzwerkpasswort")
    )
    
    # Config WLAN settings
    ap_password = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        verbose_name=_("Config-WLAN-Passwort"),
        help_text=_("Passwort für den Config-WLAN-Hotspot (MCC_XXXX). Minimum 8 Zeichen (WPA2-Anforderung).")
    )
    
    # Device behavior
    debug_mode = models.BooleanField(
        default=False,
        verbose_name=_("Debug-Modus"),
        help_text=_("Debug-Protokollierung auf dem Gerät aktivieren")
    )
    
    test_mode = models.BooleanField(
        default=False,
        verbose_name=_("Test-Modus"),
        help_text=_("Testdatenübertragungsmodus aktivieren")
    )
    
    test_distance_km = models.FloatField(
        default=0.01,
        validators=[MinValueValidator(0.001)],
        verbose_name=_("Test-Distanz (km)"),
        help_text=_("Simulierte Distanz in Kilometern für Testmodus. Standard: 0.01 km")
    )
    
    test_interval_seconds = models.IntegerField(
        default=5,
        validators=[MinValueValidator(1)],
        verbose_name=_("Test-Intervall (Sekunden)"),
        help_text=_("Sendeintervall in Sekunden für Testmodus. Standard: 5 Sekunden")
    )
    
    deep_sleep_seconds = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name=_("Deep-Sleep-Zeit (Sekunden)"),
        help_text=_("Zeit in Sekunden für Deep-Sleep-Modus (0 = deaktiviert)")
    )
    
    # Hardware configuration
    wheel_size = models.FloatField(
        default=2075.0,  # 26 Zoll Standard = 2075 mm
        verbose_name=_("Radumfang (mm)"),
        help_text=_("Radumfang in Millimeter für Distanzberechnung. Gültiger Bereich: 500-3000 mm. Standard-Tachowerte können aus Hersteller-Tabellen entnommen werden (z.B. Sigma)."),
        validators=[
            MinValueValidator(500.0, message=_("Radumfang muss mindestens 500 mm betragen")),
            MaxValueValidator(3000.0, message=_("Radumfang darf maximal 3000 mm betragen"))
        ]
    )
    
    # Firmware management
    assigned_firmware = models.ForeignKey(
        'iot.FirmwareImage',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_devices',
        verbose_name=_("Zugewiesene Firmware"),
        help_text=_("Firmware-Image, das diesem Gerät für OTA-Updates zugewiesen wurde")
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Erstellt am"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Aktualisiert am"))
    last_synced_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Zuletzt synchronisiert"),
        help_text=_("Zeitpunkt der letzten erfolgreichen Konfigurationssynchronisation")
    )
    
    class Meta:
        verbose_name = _("Device Configuration")
        verbose_name_plural = _("Device Configurations")
    
    def __str__(self):
        return f"{_('Configuration for')} {self.device.name}"
    
    def save(self, *args, **kwargs):
        """Override save to handle automatic API key assignment.
        
        Note: We do NOT set device_specific_api_key to the IoT Shared Key here because
        device_specific_api_key is unique=True and the Shared Key should be usable by multiple devices.
        Instead, we leave device_specific_api_key empty, and validate_device_api_key() will
        check the IoT Shared Key when device_specific_api_key is empty.
        
        This method is kept for potential future use (e.g., logging or other initialization).
        """
        super().save(*args, **kwargs)
    
    def generate_api_key(self) -> str:
        """Generate a new unique API key for this device.
        
        The old API key is stored in previous_api_key and remains valid until
        the device successfully authenticates with the new key. This allows
        devices that are inactive for extended periods to still fetch the new key.
        """
        import secrets
        import string
        
        # Store current key as previous key (if exists) for grace period
        # The previous key remains valid until device authenticates with new key
        old_key = self.device_specific_api_key
        if old_key:
            self.previous_api_key = old_key
            # Optional: Set expiration for cleanup (e.g., 1 year), but validation doesn't check it
            # The key is cleared when device uses new key, not when it expires
            # previous_api_key_expires_at can be used for periodic cleanup of orphaned keys
        
        # Generate a secure random API key
        alphabet = string.ascii_letters + string.digits
        api_key = ''.join(secrets.choice(alphabet) for _ in range(32))
        
        # Ensure uniqueness (check both current and previous keys)
        while (DeviceConfiguration.objects.filter(device_specific_api_key=api_key).exists() or
               DeviceConfiguration.objects.filter(previous_api_key=api_key).exists()):
            api_key = ''.join(secrets.choice(alphabet) for _ in range(32))
        
        self.device_specific_api_key = api_key
        self.api_key_last_rotated = timezone.now()
        self.save(update_fields=['device_specific_api_key', 'api_key_last_rotated', 'previous_api_key', 'previous_api_key_expires_at'])
        
        return api_key
    
    def rotate_api_key_if_needed(self) -> bool:
        """Rotate API key if rotation is enabled and interval has passed."""
        if not self.api_key_rotation_enabled:
            return False
        
        if not self.api_key_last_rotated:
            # First rotation
            self.generate_api_key()
            return True
        
        days_since_rotation = (timezone.now() - self.api_key_last_rotated).days
        if days_since_rotation >= self.api_key_rotation_interval_days:
            self.generate_api_key()
            return True
        
        return False
    
    def to_dict(self) -> dict:
        """Convert configuration to dictionary for JSON serialization."""
        return {
            # Note: device_name is NOT included - it's only configurable via device WebGUI
            # This ensures the device can always send data even if server config is missing
            'default_id_tag': self.default_id_tag or '',
            'send_interval_seconds': self.send_interval_seconds,
            'server_url': self.server_url or '',
            'wifi_ssid': self.wifi_ssid or '',
            'wifi_password': self.wifi_password or '',
            'ap_password': self.ap_password or '',
            'debug_mode': self.debug_mode,
            'test_mode': self.test_mode,
            'test_distance_km': self.test_distance_km,
            'test_interval_seconds': self.test_interval_seconds,
            'deep_sleep_seconds': self.deep_sleep_seconds,
            'wheel_size': self.wheel_size,
            'device_api_key': self.device_specific_api_key or '',
            'config_fetch_interval_seconds': self.config_fetch_interval_seconds,
        }
    
    def get_reported_device_name(self) -> str:
        """
        Gets the device_name from the most recent configuration report sent by the device.
        
        Returns the device_name as reported by the device, not from the database.
        Returns empty string if no report exists.
        """
        try:
            # Get the most recent configuration report
            latest_report = self.device.configuration_reports.order_by('-created_at').first()
            if latest_report and latest_report.reported_config:
                reported_config = latest_report.reported_config
                if isinstance(reported_config, dict):
                    # The reported_config contains the config dict directly
                    # Structure: {"device_name": "...", "default_id_tag": "...", ...}
                    device_name = reported_config.get('device_name', '')
                    if device_name:
                        return str(device_name)
        except Exception:
            pass
        return ''


class DeviceConfigurationReport(models.Model):
    """Configuration reports sent by devices on boot."""
    device = models.ForeignKey(
        Device,
        on_delete=models.CASCADE,
        related_name='configuration_reports',
        verbose_name=_("Gerät")
    )
    
    reported_config = models.JSONField(
        verbose_name=_("Gemeldete Konfiguration"),
        help_text=_("Vom Gerät gemeldete Konfigurationsdaten")
    )
    
    has_differences = models.BooleanField(
        default=False,
        verbose_name=_("Hat Unterschiede"),
        help_text=_("Ob dieser Bericht Konfigurationsunterschiede enthält")
    )
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Erstellt am"))
    
    class Meta:
        verbose_name = _("Device Configuration Report")
        verbose_name_plural = _("Device Configuration Reports")
        ordering = ['-created_at']
    
    def __str__(self):
        status = "⚠️ Unterschiede" if self.has_differences else "✓ OK"
        return f"{self.device.name} - {status} ({self.created_at.strftime('%Y-%m-%d %H:%M')})"


class DeviceConfigurationDiff(models.Model):
    """Stores differences between server and device configurations."""
    device = models.ForeignKey(
        Device,
        on_delete=models.CASCADE,
        related_name='configuration_diffs',
        verbose_name=_("Gerät")
    )
    
    report = models.ForeignKey(
        DeviceConfigurationReport,
        on_delete=models.CASCADE,
        related_name='diffs',
        verbose_name=_("Bericht")
    )
    
    field_name = models.CharField(
        max_length=100,
        verbose_name=_("Feldname"),
        help_text=_("Name des Konfigurationsfelds mit Unterschied")
    )
    
    server_value = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("Server-Wert"),
        help_text=_("Auf dem Server konfigurierter Wert")
    )
    
    device_value = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("Geräte-Wert"),
        help_text=_("Vom Gerät gemeldeter Wert")
    )
    
    is_resolved = models.BooleanField(
        default=False,
        verbose_name=_("Gelöst"),
        help_text=_("Ob dieser Unterschied behoben wurde")
    )
    
    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Gelöst am")
    )
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Erstellt am"))
    
    class Meta:
        verbose_name = _("Configuration Difference")
        verbose_name_plural = _("Configuration Differences")
        ordering = ['-created_at']
    
    def __str__(self):
        status = "✓" if self.is_resolved else "⚠"
        return f"{status} {self.device.name} - {self.field_name}"


class FirmwareImage(models.Model):
    """Firmware images for OTA updates."""
    name = models.CharField(
        max_length=200,
        verbose_name=_("Firmware-Name"),
        help_text=_("Lesbarer Name für diese Firmware-Version")
    )
    
    version = models.CharField(
        max_length=50,
        verbose_name=_("Version"),
        help_text=_("Versionskennung (z.B. '1.2.3' oder 'v2.0.1')")
        # Note: unique=True removed - use unique_together with environment instead
    )
    
    description = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("Beschreibung"),
        help_text=_("Beschreibung der Änderungen und Features in dieser Version")
    )
    
    firmware_file = models.FileField(
        upload_to='firmware/',
        verbose_name=_("Firmware-Datei"),
        help_text=_("Binäre Firmware-Datei (.bin) für ESP32")
    )
    
    file_size = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Dateigröße (Bytes)"),
        help_text=_("Größe der Firmware-Datei in Bytes")
    )
    
    checksum_md5 = models.CharField(
        max_length=32,
        blank=True,
        null=True,
        verbose_name=_("MD5-Prüfsumme"),
        help_text=_("MD5-Prüfsumme der Firmware-Datei zur Verifizierung")
    )
    
    checksum_sha256 = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        verbose_name=_("SHA256-Prüfsumme"),
        help_text=_("SHA256-Prüfsumme der Firmware-Datei zur Verifizierung")
    )
    
    environment = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name=_("Environment"),
        help_text=_("Hardware-Environment (z.B. heltec_wifi_lora_32_V3, wemos_d1_mini32)")
    )
    
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Aktiv"),
        help_text=_("Ob diese Firmware-Version aktiv und für Updates verfügbar ist")
    )
    
    is_stable = models.BooleanField(
        default=False,
        verbose_name=_("Stabile Version"),
        help_text=_("Ob dies eine stabile Release-Version ist")
    )
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Erstellt am"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Aktualisiert am"))
    
    class Meta:
        verbose_name = _("Firmware Image")
        verbose_name_plural = _("Firmware Images")
        ordering = ['-created_at']
        unique_together = [['version', 'environment']]
    
    def __str__(self):
        stable = " [STABIL]" if self.is_stable else ""
        return f"{self.name} ({self.version}){stable}"
    
    def save(self, *args, **kwargs):
        """Calculate file size, MD5 and SHA256 checksum on save."""
        if self.firmware_file:
            import hashlib
            self.file_size = self.firmware_file.size
            # Calculate MD5 and SHA256 (only if not already set)
            if not self.checksum_md5 or not self.checksum_sha256:
                self.firmware_file.seek(0)
                md5_hash = hashlib.md5()
                sha256_hash = hashlib.sha256()
                for chunk in self.firmware_file.chunks():
                    md5_hash.update(chunk)
                    sha256_hash.update(chunk)
                if not self.checksum_md5:
                    self.checksum_md5 = md5_hash.hexdigest()
                if not self.checksum_sha256:
                    self.checksum_sha256 = sha256_hash.hexdigest()
                self.firmware_file.seek(0)
        super().save(*args, **kwargs)


class DeviceManagementSettings(models.Model):
    """Global settings for device management."""
    email_notifications_enabled = models.BooleanField(
        default=True,
        verbose_name=_("Email Notifications Enabled"),
        help_text=_("Enable daily email notifications for configuration differences")
    )
    
    notification_email = models.EmailField(
        blank=True,
        null=True,
        verbose_name=_("Notification Email Address"),
        help_text=_("Email address to receive daily device status reports")
    )
    
    last_notification_sent = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Last Notification Sent"),
        help_text=_("Timestamp of the last notification email sent")
    )
    
    iot_device_shared_api_key = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        verbose_name=_("IoT Device Shared API Key"),
        help_text=_("Dedizierter API-Key für IoT-Geräte, der von mehreren Geräten gleichzeitig verwendet werden kann. Wird als Standard-Key verwendet, bevor individuelle Geräte-Keys zugewiesen werden. Gilt nur für IoT-Geräte-Endpoints, nicht für öffentliche API-Endpoints.")
    )
    
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Updated at"))
    
    class Meta:
        verbose_name = _("Geräteverwaltungs-Einstellungen")
        verbose_name_plural = _("Geräteverwaltungs-Einstellungen")
    
    def __str__(self):
        enabled = _("Enabled") if self.email_notifications_enabled else _("Disabled")
        return f"{_('Geräteverwaltungs-Einstellungen')} ({enabled})"
    
    @classmethod
    def get_settings(cls):
        """Get or create the singleton settings instance."""
        settings, _ = cls.objects.get_or_create(pk=1)
        return settings


class DeviceHealth(models.Model):
    """Health status tracking for devices."""
    device = models.OneToOneField(
        Device,
        on_delete=models.CASCADE,
        related_name='health',
        verbose_name=_("Gerät")
    )
    
    STATUS_CHOICES = [
        ('online', _('Online')),
        ('offline', _('Offline')),
        ('warning', _('Warnung')),
        ('error', _('Fehler')),
    ]
    
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='offline',
        verbose_name=_("Status")
    )
    
    last_heartbeat = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Letzter Heartbeat"),
        help_text=_("Zeitpunkt des letzten Heartbeat-Signals vom Gerät")
    )
    
    heartbeat_interval_seconds = models.IntegerField(
        default=300,
        validators=[MinValueValidator(10)],
        verbose_name=_("Erwartetes Heartbeat-Intervall (Sekunden)"),
        help_text=_("Erwartetes Intervall zwischen Heartbeats in Sekunden")
    )
    
    offline_threshold_seconds = models.IntegerField(
        default=600,
        validators=[MinValueValidator(60)],
        verbose_name=_("Offline-Schwellenwert (Sekunden)"),
        help_text=_("Gerät gilt als offline, wenn kein Heartbeat für diese Dauer empfangen wurde")
    )
    
    consecutive_failures = models.IntegerField(
        default=0,
        verbose_name=_("Aufeinanderfolgende Fehler"),
        help_text=_("Anzahl aufeinanderfolgender fehlgeschlagener Anfragen")
    )
    
    last_error_message = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("Letzte Fehlermeldung")
    )
    
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Aktualisiert am"))
    
    class Meta:
        verbose_name = _("Device Health")
        verbose_name_plural = _("Device Health Status")
    
    def __str__(self):
        return f"{self.device.name} - {self.get_status_display()}"
    
    def update_heartbeat(self):
        """Update heartbeat timestamp and reset failure count."""
        self.last_heartbeat = timezone.now()
        self.consecutive_failures = 0
        self.status = 'online'
        self.last_error_message = None
        self.save(update_fields=['last_heartbeat', 'consecutive_failures', 'status', 'last_error_message', 'updated_at'])
    
    def record_failure(self, error_message: str = None):
        """Record a failed request."""
        self.consecutive_failures += 1
        if error_message:
            self.last_error_message = error_message
        
        # Update status based on failures
        if self.consecutive_failures >= 5:
            self.status = 'error'
        elif self.consecutive_failures >= 3:
            self.status = 'warning'
        
        self.save(update_fields=['consecutive_failures', 'last_error_message', 'status', 'updated_at'])
    
    def is_offline(self) -> bool:
        """Check if device is considered offline."""
        if not self.last_heartbeat:
            return True
        
        seconds_since_heartbeat = (timezone.now() - self.last_heartbeat).total_seconds()
        return seconds_since_heartbeat > self.offline_threshold_seconds
    
    def update_status(self):
        """Update status based on last heartbeat."""
        if self.is_offline():
            self.status = 'offline'
        elif self.consecutive_failures >= 5:
            self.status = 'error'
        elif self.consecutive_failures >= 3:
            self.status = 'warning'
        else:
            self.status = 'online'
        
        self.save(update_fields=['status', 'updated_at'])


class ConfigTemplate(models.Model):
    """Predefined configuration templates for devices."""
    name = models.CharField(
        max_length=200,
        unique=True,
        verbose_name=_("Template-Name"),
        help_text=_("Lesbarer Name für dieses Template")
    )
    
    description = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("Beschreibung"),
        help_text=_("Beschreibung, wann dieses Template verwendet werden soll")
    )
    
    # Template configuration (stored as JSON)
    template_config = models.JSONField(
        verbose_name=_("Template-Konfiguration"),
        help_text=_("Konfigurationswerte für dieses Template")
    )
    
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Aktiv"),
        help_text=_("Ob dieses Template aktiv und verfügbar ist")
    )
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Erstellt am"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Aktualisiert am"))
    
    class Meta:
        verbose_name = _("Configuration Template")
        verbose_name_plural = _("Configuration Templates")
        ordering = ['name']
    
    def __str__(self):
        return self.name
    
    def apply_to_device(self, device: Device) -> DeviceConfiguration:
        """Apply this template to a device configuration."""
        # Note: DeviceConfiguration.save() will automatically assign IoT Shared API Key
        # if device_specific_api_key is not set
        config, created = DeviceConfiguration.objects.get_or_create(device=device)
        
        # Update configuration with template values
        for key, value in self.template_config.items():
            if hasattr(config, key):
                setattr(config, key, value)
        
        config.save()
        return config


class DeviceAuditLog(models.Model):
    """Audit log for device configuration changes and API key rotations."""
    device = models.ForeignKey(
        Device,
        on_delete=models.CASCADE,
        related_name='audit_logs',
        verbose_name=_("Gerät")
    )
    
    ACTION_CHOICES = [
        ('config_updated', _('Konfiguration aktualisiert')),
        ('api_key_generated', _('API-Key generiert')),
        ('api_key_rotated', _('API-Key rotiert')),
        ('firmware_assigned', _('Firmware zugewiesen')),
        ('firmware_updated', _('Firmware aktualisiert')),
        ('config_synced', _('Konfiguration synchronisiert')),
        ('heartbeat_received', _('Heartbeat empfangen')),
    ]
    
    action = models.CharField(
        max_length=50,
        choices=ACTION_CHOICES,
        verbose_name=_("Aktion")
    )
    
    user = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("Benutzer"),
        help_text=_("Benutzer, der die Aktion durchgeführt hat (null für Systemaktionen)")
    )
    
    details = models.JSONField(
        blank=True,
        null=True,
        verbose_name=_("Details"),
        help_text=_("Zusätzliche Details zur Aktion")
    )
    
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name=_("IP-Adresse"),
        help_text=_("IP-Adresse, von der die Aktion durchgeführt wurde")
    )
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Erstellt am"))
    
    class Meta:
        verbose_name = _("Device Audit Log")
        verbose_name_plural = _("Device Audit Logs")
        ordering = ['-created_at']
    
    def __str__(self):
        user_str = self.user.username if self.user else "System"
        return f"{self.device.name} - {self.get_action_display()} by {user_str}"


class WebhookConfiguration(models.Model):
    """Webhook configuration for external integrations."""
    name = models.CharField(
        max_length=200,
        unique=True,
        verbose_name=_("Webhook Name"),
        help_text=_("Human-readable name for this webhook")
    )
    
    url = models.URLField(
        max_length=500,
        verbose_name=_("Webhook URL"),
        help_text=_("URL to send webhook requests to")
    )
    
    EVENT_CHOICES = [
        ('device_offline', _('Device Offline')),
        ('device_online', _('Device Online')),
        ('config_difference', _('Configuration Difference')),
        ('firmware_update', _('Firmware Update')),
        ('api_key_rotated', _('API Key Rotated')),
        ('health_warning', _('Health Warning')),
    ]
    
    events = models.JSONField(
        default=list,
        verbose_name=_("Events"),
        help_text=_("List of events to trigger this webhook")
    )
    
    secret_key = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        verbose_name=_("Secret Key"),
        help_text=_("Secret key for webhook authentication (optional)")
    )
    
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Aktiv"),
        help_text=_("Whether this webhook is active")
    )
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Erstellt am"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Aktualisiert am"))
    
    class Meta:
        verbose_name = _("Webhook Configuration")
        verbose_name_plural = _("Webhook Configurations")
        ordering = ['name']
    
    def __str__(self):
        return self.name

