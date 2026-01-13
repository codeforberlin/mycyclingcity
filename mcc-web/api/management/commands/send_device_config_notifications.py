# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    send_device_config_notifications.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
"""
Management-Command zum Senden täglicher E-Mail-Benachrichtigungen über Gerätekonfigurationsunterschiede.

Dieser Befehl sollte täglich über crontab ausgeführt werden, um Administratoren über Geräte
mit Konfigurationsunterschieden zu benachrichtigen.

Verwendung:
    python manage.py send_device_config_notifications
    python manage.py send_device_config_notifications --force
"""

from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.utils import timezone
from django.conf import settings
from django.template.loader import render_to_string
from iot.models import (
    DeviceManagementSettings, DeviceConfigurationDiff, Device
)
from datetime import timedelta


class Command(BaseCommand):
    help = 'Sende tägliche E-Mail-Benachrichtigungen über Gerätekonfigurationsunterschiede'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Erzwinge das Senden, auch wenn Benachrichtigungen deaktiviert sind',
        )

    def handle(self, *args, **options):
        force = options.get('force', False)
        
        # Get settings
        try:
            mgmt_settings = DeviceManagementSettings.get_settings()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Fehler beim Laden der Einstellungen: {e}'))
            return
        
        # Check if notifications are enabled
        if not mgmt_settings.email_notifications_enabled and not force:
            self.stdout.write(self.style.WARNING('E-Mail-Benachrichtigungen sind deaktiviert. Verwenden Sie --force, um trotzdem zu senden.'))
            return
        
        # Check if email address is configured
        if not mgmt_settings.notification_email:
            self.stdout.write(self.style.ERROR('Keine Benachrichtigungs-E-Mail-Adresse konfiguriert.'))
            return
        
        # Get unresolved differences from the last 24 hours
        yesterday = timezone.now() - timedelta(days=1)
        unresolved_diffs = DeviceConfigurationDiff.objects.filter(
            is_resolved=False,
            created_at__gte=yesterday
        ).select_related('device', 'report').order_by('device', 'created_at')
        
        if not unresolved_diffs.exists():
            self.stdout.write(self.style.SUCCESS('Keine ungelösten Konfigurationsunterschiede gefunden.'))
            # Update last_notification_sent even if no differences
            mgmt_settings.last_notification_sent = timezone.now()
            mgmt_settings.save(update_fields=['last_notification_sent'])
            return
        
        # Group differences by device
        devices_with_diffs = {}
        for diff in unresolved_diffs:
            device_name = diff.device.display_name or diff.device.name
            if device_name not in devices_with_diffs:
                devices_with_diffs[device_name] = {
                    'device': diff.device,
                    'diffs': []
                }
            devices_with_diffs[device_name]['diffs'].append(diff)
        
        # Prepare email content
        subject = f'Gerätekonfigurationsunterschiede-Bericht - {timezone.now().strftime("%Y-%m-%d")}'
        
        # Create email body
        context = {
            'devices_with_diffs': devices_with_diffs,
            'total_devices': len(devices_with_diffs),
            'total_differences': unresolved_diffs.count(),
            'report_date': timezone.now().strftime('%Y-%m-%d %H:%M:%S UTC'),
        }
        
        # Try to render HTML template, fallback to plain text
        try:
            html_message = render_to_string('admin/api/device_config_notification_email.html', context)
            message = None  # Django will use html_message if message is None
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'HTML-Template konnte nicht gerendert werden: {e}. Verwende Klartext.'))
            # Plain text fallback
            message = self._generate_plain_text_message(context)
            html_message = None
        
        # Send email
        try:
            from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@mycyclingcity.net')
            
            send_mail(
                subject=subject,
                message=message,
                from_email=from_email,
                recipient_list=[mgmt_settings.notification_email],
                html_message=html_message,
                fail_silently=False,
            )
            
            # Update last_notification_sent
            mgmt_settings.last_notification_sent = timezone.now()
            mgmt_settings.save(update_fields=['last_notification_sent'])
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'Benachrichtigungs-E-Mail erfolgreich an {mgmt_settings.notification_email} gesendet. '
                    f'{len(devices_with_diffs)} Gerät(e) mit {unresolved_diffs.count()} Unterschied(en) gemeldet.'
                )
            )
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Fehler beim Senden der E-Mail: {e}'))
            raise
    
    def _generate_plain_text_message(self, context: dict) -> str:
        """Generate plain text email message."""
        lines = [
            f"Gerätekonfigurationsunterschiede-Bericht",
            f"Berichtsdatum: {context['report_date']}",
            "",
            f"Gesamt Geräte mit Unterschieden: {context['total_devices']}",
            f"Gesamt Unterschiede: {context['total_differences']}",
            "",
            "=" * 60,
            "",
        ]
        
        for device_name, device_data in context['devices_with_diffs'].items():
            lines.append(f"Gerät: {device_name}")
            lines.append("-" * 60)
            for diff in device_data['diffs']:
                lines.append(f"  Feld: {diff.field_name}")
                lines.append(f"    Server-Wert: {diff.server_value}")
                lines.append(f"    Geräte-Wert: {diff.device_value}")
                lines.append("")
            lines.append("")
        
        lines.append("=" * 60)
        lines.append("")
        lines.append("Bitte überprüfen und lösen Sie diese Unterschiede im Admin-GUI.")
        
        return "\n".join(lines)

