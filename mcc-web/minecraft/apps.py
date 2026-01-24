from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class MinecraftAppConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "minecraft"
    verbose_name = _("Minecraft Management")
