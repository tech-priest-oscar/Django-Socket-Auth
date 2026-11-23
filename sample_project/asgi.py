import os

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sample_project.settings")
django_asgi_app = get_asgi_application()

# Import anything that touches models *after* get_asgi_application().
from django_socket_auth.middleware import SocketAuthMiddleware  # noqa: E402

from chat.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        # Every websocket connection is authenticated here: scope["user"] is
        # set to the token's user, or AnonymousUser if the token is missing
        # or invalid.
        "websocket": SocketAuthMiddleware(URLRouter(websocket_urlpatterns)),
    }
)
