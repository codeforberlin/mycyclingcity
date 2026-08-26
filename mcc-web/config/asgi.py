import os

from django.core.asgi import get_asgi_application


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

django_asgi_app = get_asgi_application()

try:
    from channels.routing import ProtocolTypeRouter, URLRouter
    from django.conf import settings
    from minecraft.routing import websocket_urlpatterns as minecraft_ws
    from minecraft.ws_internal import build_http_application
    from luanti.routing import websocket_urlpatterns as luanti_ws

    ws_patterns = list(minecraft_ws) + list(luanti_ws)
    ws_enabled = settings.MCC_MINECRAFT_WS_ENABLED or settings.MCC_LUANTI_WS_ENABLED
    if ws_enabled:
        application = ProtocolTypeRouter(
            {
                "http": build_http_application(django_asgi_app),
                "websocket": URLRouter(ws_patterns),
            }
        )
    else:
        application = django_asgi_app
except Exception:
    application = django_asgi_app
