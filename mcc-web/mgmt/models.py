# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    models.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
from django.db import models
from django.utils.translation import gettext_lazy as _


class LoggingConfig(models.Model):
    """
    Configuration for application logging levels.
    
    This is a singleton model - only one instance should exist.
    Controls which log levels are written to log files.
    """
    MIN_LOG_LEVEL_CHOICES = [
        ('DEBUG', 'DEBUG - Alle Logs (DEBUG, INFO, WARNING, ERROR, CRITICAL)'),
        ('INFO', 'INFO - Informative und kritische Logs (INFO, WARNING, ERROR, CRITICAL)'),
        ('WARNING', 'WARNING - Nur kritische Logs (WARNING, ERROR, CRITICAL)'),
        ('ERROR', 'ERROR - Nur Fehler (ERROR, CRITICAL)'),
        ('CRITICAL', 'CRITICAL - Nur kritische Fehler'),
    ]
    
    min_log_level = models.CharField(
        max_length=10,
        choices=MIN_LOG_LEVEL_CHOICES,
        default='INFO',
        verbose_name=_("Minimum Log Level"),
        help_text=_("Nur Logs mit diesem Level oder höher werden in die Log-Dateien geschrieben.")
    )
    
    enable_request_logging = models.BooleanField(
        default=False,
        verbose_name=_("Request Logs aktivieren"),
        help_text=_("Wenn aktiviert, werden alle HTTP-Requests in der Datenbank gespeichert (RequestLog). Deaktivieren Sie dies, um die Datenbank nicht zu überladen.")
    )
    
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Zuletzt aktualisiert")
    )
    updated_by = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("Aktualisiert von"),
        help_text=_("Benutzer, der diese Einstellung zuletzt geändert hat")
    )
    
    class Meta:
        verbose_name = _("Logging Configuration")
        verbose_name_plural = _("Logging Configuration")
    
    def __str__(self):
        return f"Logging Config: {self.get_min_log_level_display()}"
    
    @classmethod
    def get_config(cls):
        """Get or create the singleton configuration instance."""
        config, _ = cls.objects.get_or_create(pk=1, defaults={'min_log_level': 'INFO', 'enable_request_logging': False})
        return config
    
    def should_store_level(self, level: str) -> bool:
        """
        Check if a log level should be stored based on min_log_level.
        
        Args:
            level: Log level to check (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            
        Returns:
            True if the level should be stored, False otherwise
        """
        level_order = {
            'DEBUG': 0,
            'INFO': 1,
            'WARNING': 2,
            'ERROR': 3,
            'CRITICAL': 4,
        }
        
        min_level = level_order.get(self.min_log_level, 1)  # Default to INFO
        check_level = level_order.get(level, 99)  # Unknown levels default to storing
        
        return check_level >= min_level


class GunicornConfig(models.Model):
    """
    Configuration for Gunicorn server settings.
    
    This is a singleton model - only one instance should exist.
    Controls Gunicorn server settings like log level, workers, timeouts, etc.
    """
    LOG_LEVEL_CHOICES = [
        ('debug', _('DEBUG - Very detailed output')),
        ('info', _('INFO - Informative messages (default)')),
        ('warning', _('WARNING - Warnings only')),
        ('error', _('ERROR - Errors only')),
        ('critical', _('CRITICAL - Critical errors only')),
    ]
    
    WORKER_CLASS_CHOICES = [
        ('sync', _('sync - Synchronous workers (default)')),
        ('gthread', _('gthread - Threaded workers (recommended for I/O-intensive applications)')),
        ('gevent', _('gevent - Async workers (requires gevent)')),
        ('eventlet', _('eventlet - Async workers (requires eventlet)')),
    ]
    
    log_level = models.CharField(
        max_length=10,
        choices=LOG_LEVEL_CHOICES,
        default='info',
        verbose_name=_("Log Level"),
        help_text=_("Gunicorn log level. Changes require a server restart.")
    )
    
    workers = models.IntegerField(
        default=0,
        verbose_name=_("Worker Anzahl"),
        help_text=_("Anzahl der Worker-Prozesse (0 = automatisch: CPU * 2 + 1)")
    )
    
    threads = models.IntegerField(
        default=2,
        verbose_name=_("Threads pro Worker"),
        help_text=_("Anzahl der Threads pro Worker (nur bei worker_class='gthread' relevant)")
    )
    
    worker_class = models.CharField(
        max_length=20,
        choices=WORKER_CLASS_CHOICES,
        default='sync',
        verbose_name=_("Worker Klasse"),
        help_text=_("Worker-Klasse für Gunicorn")
    )
    
    timeout = models.IntegerField(
        default=30,
        verbose_name=_("Timeout (Sekunden)"),
        help_text=_("Worker-Timeout in Sekunden")
    )
    
    graceful_timeout = models.IntegerField(
        default=30,
        verbose_name=_("Graceful Timeout (Sekunden)"),
        help_text=_("Timeout für graceful shutdown")
    )
    
    keepalive = models.IntegerField(
        default=2,
        verbose_name=_("Keepalive (Sekunden)"),
        help_text=_("Keepalive-Timeout für Verbindungen")
    )
    
    max_requests = models.IntegerField(
        default=1000,
        verbose_name=_("Max Requests"),
        help_text=_("Anzahl Requests nach denen ein Worker neu gestartet wird (0 = deaktiviert)")
    )
    
    max_requests_jitter = models.IntegerField(
        default=50,
        verbose_name=_("Max Requests Jitter"),
        help_text=_("Zufällige Variation für max_requests")
    )
    
    preload_app = models.BooleanField(
        default=True,
        verbose_name=_("Preload App"),
        help_text=_("Lädt Anwendungscode vor dem Forken der Worker")
    )
    
    bind_address = models.CharField(
        max_length=100,
        default='127.0.0.1:8001',
        verbose_name=_("Bind Adresse"),
        help_text=_("Adresse und Port, an die Gunicorn gebunden wird (z.B. 127.0.0.1:8001)")
    )
    
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Zuletzt aktualisiert")
    )
    updated_by = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("Aktualisiert von"),
        help_text=_("Benutzer, der diese Einstellung zuletzt geändert hat")
    )
    
    class Meta:
        verbose_name = _("Gunicorn Configuration")
        verbose_name_plural = _("Gunicorn Configuration")
    
    def __str__(self):
        return f"Gunicorn Config: {self.get_log_level_display()}"
    
    @classmethod
    def get_config(cls):
        """Get or create the singleton configuration instance."""
        config, _ = cls.objects.get_or_create(
            pk=1,
            defaults={
                'log_level': 'info',
                'workers': 0,
                'threads': 2,
                'worker_class': 'gthread'
            }
        )
        return config
    
    def get_workers_count(self):
        """Get actual worker count (auto-calculated if 0)."""
        if self.workers > 0:
            return self.workers
        import multiprocessing
        return multiprocessing.cpu_count() * 2 + 1


class MaintenanceConfig(models.Model):
    """
    Configuration for maintenance mode settings.
    
    This is a singleton model - only one instance should exist.
    Controls maintenance mode behavior including IP whitelist.
    """
    ip_whitelist = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("IP Whitelist"),
        help_text=_("Eine IP-Adresse oder ein CIDR-Block pro Zeile. Beispiel:\n192.168.1.100\n10.0.0.0/8\n172.16.0.0/12\nDiese IPs können während der Wartung auf die Website zugreifen.")
    )
    
    allow_admin_during_maintenance = models.BooleanField(
        default=True,
        verbose_name=_("Admin-Zugriff während Wartung erlauben"),
        help_text=_("Wenn aktiviert, können Superuser auch ohne IP-Whitelist auf /admin/ zugreifen")
    )
    
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Zuletzt aktualisiert")
    )
    updated_by = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("Aktualisiert von"),
        help_text=_("Benutzer, der diese Einstellung zuletzt geändert hat")
    )
    
    class Meta:
        verbose_name = _("Maintenance Configuration")
        verbose_name_plural = _("Maintenance Configuration")
    
    def __str__(self):
        return "Maintenance Configuration"
    
    @classmethod
    def get_config(cls):
        """Get or create the singleton configuration instance."""
        config, _ = cls.objects.get_or_create(
            pk=1,
            defaults={
                'ip_whitelist': '',
                'allow_admin_during_maintenance': True
            }
        )
        return config
    
    def get_ip_list(self):
        """Get list of IP addresses/CIDR blocks from whitelist."""
        if not self.ip_whitelist:
            return []
        return [ip.strip() for ip in self.ip_whitelist.split('\n') if ip.strip()]


# Import performance models
from mgmt.models_performance import RequestLog, PerformanceMetric, AlertRule

