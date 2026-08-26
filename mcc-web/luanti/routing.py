from django.urls import path

from luanti.consumers import LuantiEventConsumer

websocket_urlpatterns = [
    path("ws/luanti/events", LuantiEventConsumer.as_asgi()),
    path("ws/luanti/events/", LuantiEventConsumer.as_asgi()),
]
