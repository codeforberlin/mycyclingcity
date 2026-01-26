from django.apps import AppConfig
from django.db.models.signals import post_save
from django.utils.translation import gettext_lazy as _


class MinecraftAppConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "minecraft"
    verbose_name = _("Minecraft Management")
    
    def ready(self):
        """Connect signals when app is ready."""
        from .models import MinecraftOutboxEvent
        from .services.socket_notifier import notify_worker
        
        def on_outbox_event_created(sender, instance, created, **kwargs):
            """Signal handler: Notify worker when new event is created."""
            # Only notify for new pending events
            if created and instance.status == MinecraftOutboxEvent.STATUS_PENDING:
                notify_worker(event_id=instance.id)
        
        # Connect signal
        post_save.connect(on_outbox_event_created, sender=MinecraftOutboxEvent)
