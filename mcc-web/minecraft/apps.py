from django.apps import AppConfig
from django.db import transaction
from django.db.models.signals import post_save
from django.utils.translation import gettext_lazy as _


class MinecraftAppConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "minecraft"
    verbose_name = _("Minecraft Management")
    
    def ready(self):
        """Connect signals when app is ready."""
        from api.models import Group, Cyclist
        from .models import MinecraftOutboxEvent
        from .services.socket_notifier import notify_worker
        from . import signals as minecraft_signals

        def on_outbox_event_created(sender, instance, created, **kwargs):
            """Notify worker after commit so the event is visible when woken."""
            if created and instance.status == MinecraftOutboxEvent.STATUS_PENDING:
                event_id = instance.id
                transaction.on_commit(lambda eid=event_id: notify_worker(event_id=eid))

        post_save.connect(on_outbox_event_created, sender=MinecraftOutboxEvent)
        post_save.connect(minecraft_signals.on_group_post_save, sender=Group)

        from django.db.models.signals import m2m_changed, pre_delete
        pre_delete.connect(minecraft_signals.on_group_pre_delete, sender=Group)
        post_save.connect(minecraft_signals.on_cyclist_post_save, sender=Cyclist)
        m2m_changed.connect(
            minecraft_signals.on_cyclist_groups_changed,
            sender=Cyclist.groups.through,
        )
