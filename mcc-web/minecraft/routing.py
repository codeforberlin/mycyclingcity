from django.urls import path

from minecraft.consumers import MinecraftEventConsumer


websocket_urlpatterns = [
    path("ws/minecraft/events", MinecraftEventConsumer.as_asgi()),
]
