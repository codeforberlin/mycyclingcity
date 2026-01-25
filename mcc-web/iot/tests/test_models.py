# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    test_models.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

"""
Unit tests for IoT models.

Tests cover:
- Device model
- DeviceConfiguration model methods
- DeviceConfigurationReport model
- DeviceConfigurationDiff model
- FirmwareImage model
- DeviceManagementSettings singleton
- DeviceHealth model methods
- ConfigTemplate model
- DeviceAuditLog model
- WebhookConfiguration model
"""

import pytest
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal

from iot.models import (
    Device, DeviceConfiguration, DeviceConfigurationReport,
    DeviceConfigurationDiff, FirmwareImage, DeviceManagementSettings,
    DeviceHealth, ConfigTemplate, DeviceAuditLog, WebhookConfiguration
)
from api.tests.conftest import GroupFactory


@pytest.mark.unit
@pytest.mark.django_db
class TestDevice:
    """Tests for Device model."""
    
    def test_create_device(self):
        """Test creating a device."""
        device = Device.objects.create(
            name="test-device-01",
            display_name="Test Device",
        )
        
        assert device.name == "test-device-01"
        assert device.display_name == "Test Device"
        assert device.distance_total == Decimal('0.00000')
        assert device.is_visible is True
        assert device.is_km_collection_enabled is True
    
    def test_device_str_representation(self):
        """Test string representation of device."""
        device = Device.objects.create(
            name="test-device-01",
            display_name="Test Device",
        )
        
        assert str(device) == "Test Device"
        
        # Without display_name, should use name
        device2 = Device.objects.create(name="test-device-02")
        assert str(device2) == "test-device-02"
    
    def test_device_unique_name(self):
        """Test that device name must be unique."""
        Device.objects.create(name="unique-device")
        
        with pytest.raises(Exception):  # IntegrityError
            Device.objects.create(name="unique-device")
    
    def test_device_with_group(self):
        """Test device with assigned group."""
        group = GroupFactory()
        device = Device.objects.create(
            name="test-device-01",
            group=group,
        )
        
        assert device.group == group


@pytest.mark.unit
@pytest.mark.django_db
class TestDeviceConfiguration:
    """Tests for DeviceConfiguration model."""
    
    def test_create_configuration(self):
        """Test creating a device configuration."""
        device = Device.objects.create(name="test-device-01")
        config = DeviceConfiguration.objects.create(device=device)
        
        assert config.device == device
        assert config.send_interval_seconds == 60
        assert config.wheel_size == 26
        assert config.debug_mode is False
    
    def test_configuration_one_to_one_relationship(self):
        """Test that device has one configuration."""
        device = Device.objects.create(name="test-device-01")
        config1 = DeviceConfiguration.objects.create(device=device)
        
        # Creating another config for same device should fail
        with pytest.raises(Exception):  # IntegrityError
            DeviceConfiguration.objects.create(device=device)
    
    def test_generate_api_key(self):
        """Test generating a new API key."""
        device = Device.objects.create(name="test-device-01")
        config = DeviceConfiguration.objects.create(device=device)
        
        api_key = config.generate_api_key()
        
        assert len(api_key) == 32
        assert config.device_specific_api_key == api_key
        assert config.api_key_last_rotated is not None
        assert config.previous_api_key is None  # First key, no previous
    
    def test_generate_api_key_stores_previous(self):
        """Test that generating new key stores previous key."""
        device = Device.objects.create(name="test-device-01")
        config = DeviceConfiguration.objects.create(device=device)
        
        # Generate first key
        first_key = config.generate_api_key()
        config.refresh_from_db()
        
        # Generate second key
        second_key = config.generate_api_key()
        config.refresh_from_db()
        
        assert config.device_specific_api_key == second_key
        assert config.previous_api_key == first_key
    
    def test_generate_api_key_ensures_uniqueness(self):
        """Test that generated API keys are unique."""
        device1 = Device.objects.create(name="test-device-01")
        device2 = Device.objects.create(name="test-device-02")
        config1 = DeviceConfiguration.objects.create(device=device1)
        config2 = DeviceConfiguration.objects.create(device=device2)
        
        key1 = config1.generate_api_key()
        key2 = config2.generate_api_key()
        
        assert key1 != key2
    
    def test_rotate_api_key_if_needed_disabled(self):
        """Test rotation when rotation is disabled."""
        device = Device.objects.create(name="test-device-01")
        config = DeviceConfiguration.objects.create(device=device)
        config.api_key_rotation_enabled = False
        
        result = config.rotate_api_key_if_needed()
        
        assert result is False
    
    def test_rotate_api_key_if_needed_first_rotation(self):
        """Test first rotation when no previous rotation."""
        device = Device.objects.create(name="test-device-01")
        config = DeviceConfiguration.objects.create(device=device)
        config.api_key_rotation_enabled = True
        config.api_key_last_rotated = None
        
        result = config.rotate_api_key_if_needed()
        
        assert result is True
        assert config.device_specific_api_key is not None
    
    def test_rotate_api_key_if_needed_interval_passed(self):
        """Test rotation when interval has passed."""
        device = Device.objects.create(name="test-device-01")
        config = DeviceConfiguration.objects.create(device=device)
        config.api_key_rotation_enabled = True
        config.api_key_rotation_interval_days = 1
        config.api_key_last_rotated = timezone.now() - timedelta(days=2)
        old_key = config.device_specific_api_key = "old-key"
        config.save()
        
        result = config.rotate_api_key_if_needed()
        
        assert result is True
        config.refresh_from_db()
        assert config.device_specific_api_key != old_key
        assert config.previous_api_key == old_key
    
    def test_rotate_api_key_if_needed_interval_not_passed(self):
        """Test rotation when interval has not passed."""
        device = Device.objects.create(name="test-device-01")
        config = DeviceConfiguration.objects.create(device=device)
        config.api_key_rotation_enabled = True
        config.api_key_rotation_interval_days = 90
        config.api_key_last_rotated = timezone.now() - timedelta(days=30)
        config.save()
        
        result = config.rotate_api_key_if_needed()
        
        assert result is False
    
    def test_to_dict(self):
        """Test converting configuration to dictionary."""
        device = Device.objects.create(name="test-device-01")
        config = DeviceConfiguration.objects.create(
            device=device,
            default_id_tag="test-tag",
            send_interval_seconds=120,
            server_url="https://example.com",
            debug_mode=True,
        )
        
        config_dict = config.to_dict()
        
        assert config_dict['default_id_tag'] == "test-tag"
        assert config_dict['send_interval_seconds'] == 120
        assert config_dict['server_url'] == "https://example.com"
        assert config_dict['debug_mode'] is True
        assert 'device_name' not in config_dict  # Should not be included


@pytest.mark.unit
@pytest.mark.django_db
class TestDeviceConfigurationReport:
    """Tests for DeviceConfigurationReport model."""
    
    def test_create_report(self):
        """Test creating a configuration report."""
        device = Device.objects.create(name="test-device-01")
        report = DeviceConfigurationReport.objects.create(
            device=device,
            reported_config={"device_name": "test-device", "send_interval": 60},
            has_differences=False,
        )
        
        assert report.device == device
        assert report.reported_config["device_name"] == "test-device"
        assert report.has_differences is False
    
    def test_report_str_representation(self):
        """Test string representation of report."""
        device = Device.objects.create(name="test-device-01")
        report = DeviceConfigurationReport.objects.create(
            device=device,
            reported_config={},
            has_differences=True,
        )
        
        assert "⚠️ Unterschiede" in str(report)
        assert device.name in str(report)


@pytest.mark.unit
@pytest.mark.django_db
class TestDeviceConfigurationDiff:
    """Tests for DeviceConfigurationDiff model."""
    
    def test_create_diff(self):
        """Test creating a configuration difference."""
        device = Device.objects.create(name="test-device-01")
        report = DeviceConfigurationReport.objects.create(
            device=device,
            reported_config={},
        )
        
        diff = DeviceConfigurationDiff.objects.create(
            device=device,
            report=report,
            field_name="send_interval_seconds",
            server_value="120",
            device_value="60",
        )
        
        assert diff.device == device
        assert diff.report == report
        assert diff.field_name == "send_interval_seconds"
        assert diff.server_value == "120"
        assert diff.device_value == "60"
        assert diff.is_resolved is False


@pytest.mark.unit
@pytest.mark.django_db
class TestFirmwareImage:
    """Tests for FirmwareImage model."""
    
    def test_create_firmware_image(self):
        """Test creating a firmware image."""
        firmware = FirmwareImage.objects.create(
            name="Test Firmware",
            version="1.0.0",
            description="Test description",
            is_active=True,
            is_stable=True,
        )
        
        assert firmware.name == "Test Firmware"
        assert firmware.version == "1.0.0"
        assert firmware.is_active is True
        assert firmware.is_stable is True
    
    def test_firmware_str_representation(self):
        """Test string representation of firmware."""
        firmware = FirmwareImage.objects.create(
            name="Test Firmware",
            version="1.0.0",
            is_stable=True,
        )
        
        assert "[STABIL]" in str(firmware)
        assert "1.0.0" in str(firmware)
    
    def test_firmware_unique_version(self):
        """Test that firmware version must be unique."""
        FirmwareImage.objects.create(name="Firmware 1", version="1.0.0")
        
        with pytest.raises(Exception):  # IntegrityError
            FirmwareImage.objects.create(name="Firmware 2", version="1.0.0")


@pytest.mark.unit
@pytest.mark.django_db
class TestDeviceManagementSettings:
    """Tests for DeviceManagementSettings singleton."""
    
    def test_get_settings_creates_singleton(self):
        """Test that get_settings creates a singleton instance."""
        # Clear any existing settings
        DeviceManagementSettings.objects.all().delete()
        
        settings1 = DeviceManagementSettings.get_settings()
        assert settings1.pk == 1
        
        settings2 = DeviceManagementSettings.get_settings()
        assert settings2.pk == settings1.pk
        
        assert DeviceManagementSettings.objects.count() == 1


@pytest.mark.unit
@pytest.mark.django_db
class TestDeviceHealth:
    """Tests for DeviceHealth model."""
    
    def test_create_health(self):
        """Test creating device health."""
        device = Device.objects.create(name="test-device-01")
        health = DeviceHealth.objects.create(
            device=device,
            status="online",
        )
        
        assert health.device == device
        assert health.status == "online"
    
    def test_update_heartbeat(self):
        """Test updating heartbeat."""
        device = Device.objects.create(name="test-device-01")
        health = DeviceHealth.objects.create(
            device=device,
            status="offline",
            consecutive_failures=5,
        )
        
        health.update_heartbeat()
        health.refresh_from_db()
        
        assert health.last_heartbeat is not None
        assert health.consecutive_failures == 0
        assert health.status == "online"
        assert health.last_error_message is None
    
    def test_record_failure(self):
        """Test recording a failure."""
        device = Device.objects.create(name="test-device-01")
        health = DeviceHealth.objects.create(
            device=device,
            status="online",
            consecutive_failures=0,
        )
        
        health.record_failure("Connection timeout")
        health.refresh_from_db()
        
        assert health.consecutive_failures == 1
        assert health.last_error_message == "Connection timeout"
    
    def test_record_failure_updates_status(self):
        """Test that recording failures updates status."""
        device = Device.objects.create(name="test-device-01")
        health = DeviceHealth.objects.create(
            device=device,
            status="online",
            consecutive_failures=0,
        )
        
        # 3 failures -> warning
        for _ in range(3):
            health.record_failure("Error")
        health.refresh_from_db()
        assert health.status == "warning"
        
        # 5 failures -> error
        for _ in range(2):
            health.record_failure("Error")
        health.refresh_from_db()
        assert health.status == "error"
    
    def test_is_offline_no_heartbeat(self):
        """Test is_offline when no heartbeat exists."""
        device = Device.objects.create(name="test-device-01")
        health = DeviceHealth.objects.create(device=device)
        
        assert health.is_offline() is True
    
    def test_is_offline_threshold_exceeded(self):
        """Test is_offline when threshold exceeded."""
        device = Device.objects.create(name="test-device-01")
        health = DeviceHealth.objects.create(
            device=device,
            offline_threshold_seconds=60,
            last_heartbeat=timezone.now() - timedelta(seconds=120),
        )
        
        assert health.is_offline() is True
    
    def test_is_offline_within_threshold(self):
        """Test is_offline when within threshold."""
        device = Device.objects.create(name="test-device-01")
        health = DeviceHealth.objects.create(
            device=device,
            offline_threshold_seconds=60,
            last_heartbeat=timezone.now() - timedelta(seconds=30),
        )
        
        assert health.is_offline() is False
    
    def test_update_status(self):
        """Test updating status based on heartbeat and failures."""
        device = Device.objects.create(name="test-device-01")
        health = DeviceHealth.objects.create(
            device=device,
            offline_threshold_seconds=60,
            last_heartbeat=timezone.now() - timedelta(seconds=120),
            consecutive_failures=5,
        )
        
        health.update_status()
        health.refresh_from_db()
        
        assert health.status == "offline"  # Offline takes precedence


@pytest.mark.unit
@pytest.mark.django_db
class TestConfigTemplate:
    """Tests for ConfigTemplate model."""
    
    def test_create_template(self):
        """Test creating a configuration template."""
        template = ConfigTemplate.objects.create(
            name="Test Template",
            description="Test description",
            template_config={"send_interval_seconds": 120, "debug_mode": True},
            is_active=True,
        )
        
        assert template.name == "Test Template"
        assert template.template_config["send_interval_seconds"] == 120
    
    def test_apply_to_device(self):
        """Test applying template to device."""
        device = Device.objects.create(name="test-device-01")
        template = ConfigTemplate.objects.create(
            name="Test Template",
            template_config={"send_interval_seconds": 120, "debug_mode": True},
        )
        
        config = template.apply_to_device(device)
        
        assert config.device == device
        assert config.send_interval_seconds == 120
        assert config.debug_mode is True


@pytest.mark.unit
@pytest.mark.django_db
class TestDeviceAuditLog:
    """Tests for DeviceAuditLog model."""
    
    def test_create_audit_log(self):
        """Test creating an audit log entry."""
        device = Device.objects.create(name="test-device-01")
        log = DeviceAuditLog.objects.create(
            device=device,
            action="api_key_generated",
            details={"key_length": 32},
        )
        
        assert log.device == device
        assert log.action == "api_key_generated"
        assert log.details["key_length"] == 32


@pytest.mark.unit
@pytest.mark.django_db
class TestWebhookConfiguration:
    """Tests for WebhookConfiguration model."""
    
    def test_create_webhook(self):
        """Test creating a webhook configuration."""
        webhook = WebhookConfiguration.objects.create(
            name="Test Webhook",
            url="https://example.com/webhook",
            events=["device_offline", "device_online"],
            secret_key="secret123",
            is_active=True,
        )
        
        assert webhook.name == "Test Webhook"
        assert webhook.url == "https://example.com/webhook"
        assert len(webhook.events) == 2
        assert webhook.secret_key == "secret123"
    
    def test_webhook_unique_name(self):
        """Test that webhook name must be unique."""
        WebhookConfiguration.objects.create(
            name="Unique Webhook",
            url="https://example.com/webhook",
        )
        
        with pytest.raises(Exception):  # IntegrityError
            WebhookConfiguration.objects.create(
                name="Unique Webhook",
                url="https://example.com/webhook2",
            )
