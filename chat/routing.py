from django.urls import re_path

from chat.consumers import ChatConsumer

# Channel-layer group names only allow ASCII letters, digits, "-", "_" and ".",
# so the room name is restricted to those characters.
websocket_urlpatterns = [
    re_path(r"^ws/chat/(?P<room>[A-Za-z0-9_-]{1,50})/$", ChatConsumer.as_asgi()),
]
