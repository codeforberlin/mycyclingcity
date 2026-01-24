import os

from django.core.asgi import get_asgi_application


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

django_asgi_app = get_asgi_application()

try:
    from channels.routing import ProtocolTypeRouter, URLRouter
    from django.conf import settings
    from minecraft.routing import websocket_urlpatterns

    if settings.MCC_MINECRAFT_WS_ENABLED:
        application = ProtocolTypeRouter(
            {
                "http": django_asgi_app,
                "websocket": URLRouter(websocket_urlpatterns),
            }
        )
    else:
        application = django_asgi_app
except Exception:
    application = django_asgi_app
