import os

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "socket_auth.settings")

# Initialise Django (apps registry, settings) before importing anything that
# touches models, e.g. the websocket routes below.
django_asgi_app = get_asgi_application()

from accounts.urls import websocket_urls  # noqa: E402

application = ProtocolTypeRouter(
    {"http": django_asgi_app, "websocket": URLRouter(websocket_urls)}
)
