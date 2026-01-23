# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    models.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
from django.db import models
from django.utils.translation import gettext_lazy as _


class ApplicationLog(models.Model):
    """
    Database model for storing critical application logs (WARNING, ERROR, CRITICAL).
    
    This model is used by the DatabaseLogHandler to store log entries in the database
    for easy viewing and filtering in the Django Admin interface.
    """
    LEVEL_CHOICES = [
        ('DEBUG', 'DEBUG'),
        ('INFO', 'INFO'),
        ('WARNING', 'WARNING'),
        ('ERROR', 'ERROR'),
        ('CRITICAL', 'CRITICAL'),
    ]
    
    level = models.CharField(
        max_length=10,
        choices=LEVEL_CHOICES,
        db_index=True,
        verbose_name=_("Level")
    )
    logger_name = models.CharField(
        max_length=100,
        db_index=True,
        verbose_name=_("Logger Name"),
        help_text=_("Name of the logger that generated this log entry")
    )
    message = models.TextField(
        verbose_name=_("Message"),
        help_text=_("The log message")
    )
    module = models.CharField(
        max_length=200,
        blank=True,
        verbose_name=_("Module"),
        help_text=_("Module where the log was generated")
    )
    timestamp = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name=_("Timestamp")
    )
    exception_info = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("Exception Info"),
        help_text=_("Exception traceback if available")
    )
    extra_data = models.JSONField(
        blank=True,
        null=True,
        verbose_name=_("Extra Data"),
        help_text=_("Additional context data as JSON")
    )
    
    class Meta:
        verbose_name = _("Application Log")
        verbose_name_plural = _("Application Logs")
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['level', '-timestamp']),
            models.Index(fields=['logger_name', '-timestamp']),
            models.Index(fields=['-timestamp']),
        ]
    
    def __str__(self):
        return f"[{self.level}] {self.logger_name}: {self.message[:100]}"


class LoggingConfig(models.Model):
    """
    Configuration for application logging in the database.
    
    This is a singleton model - only one instance should exist.
    Controls which log levels are stored in the database for viewing in Admin GUI.
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
        default='WARNING',
        verbose_name=_("Minimum Log Level"),
        help_text=_("Nur Logs mit diesem Level oder höher werden in der Datenbank gespeichert und im Admin GUI angezeigt.")
    )
    
    enable_request_logging = models.BooleanField(
        default=False,
        verbose_name=_("Request Logs aktivieren"),
        help_text=_("Wenn aktiviert, werden alle HTTP-Requests in der Datenbank gespeichert. Deaktivieren Sie dies, um die Datenbank nicht zu überladen.")
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
        config, _ = cls.objects.get_or_create(pk=1, defaults={'min_log_level': 'WARNING', 'enable_request_logging': False})
        return config
    
    def should_store_level(self, level):
        """
        Check if a log level should be stored based on the configuration.
        
        Args:
            level: Log level string (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        
        Returns:
            bool: True if the level should be stored
        """
        level_order = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        try:
            min_level_index = level_order.index(self.min_log_level)
            log_level_index = level_order.index(level)
            return log_level_index >= min_level_index
        except ValueError:
            # Unknown level, default to storing it
            return True


class GunicornConfig(models.Model):
    """
    Configuration for Gunicorn server settings.
    
    This is a singleton model - only one instance should exist.
    Controls Gunicorn server settings like log level, workers, timeouts, etc.
    """
    LOG_LEVEL_CHOICES = [
        ('debug', 'DEBUG - Sehr detaillierte Ausgaben'),
        ('info', 'INFO - Informative Meldungen (Standard)'),
        ('warning', 'WARNING - Nur Warnungen'),
        ('error', 'ERROR - Nur Fehler'),
        ('critical', 'CRITICAL - Nur kritische Fehler'),
    ]
    
    WORKER_CLASS_CHOICES = [
        ('sync', 'sync - Synchronous workers (Standard)'),
        ('gevent', 'gevent - Async workers (benötigt gevent)'),
        ('eventlet', 'eventlet - Async workers (benötigt eventlet)'),
    ]
    
    log_level = models.CharField(
        max_length=10,
        choices=LOG_LEVEL_CHOICES,
        default='info',
        verbose_name=_("Log Level"),
        help_text=_("Gunicorn Log-Level. Änderungen erfordern einen Server-Neustart.")
    )
    
    workers = models.IntegerField(
        default=0,
        verbose_name=_("Worker Anzahl"),
        help_text=_("Anzahl der Worker-Prozesse (0 = automatisch: CPU * 2 + 1)")
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
        config, _ = cls.objects.get_or_create(pk=1, defaults={'log_level': 'info'})
        return config
    
    def get_workers_count(self):
        """Get actual worker count (auto-calculated if 0)."""
        if self.workers > 0:
            return self.workers
        import multiprocessing
        return multiprocessing.cpu_count() * 2 + 1


# Import performance models
from mgmt.models_performance import RequestLog, PerformanceMetric, AlertRule

