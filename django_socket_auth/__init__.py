"""
Pluggable authentication for Django Channels websockets. Uses
djangorestframework-simplejwt access tokens by default.

    from django_socket_auth.middleware import SocketAuthMiddleware
    from django_socket_auth.consumers import AuthenticatedWebsocketConsumer
    from django_socket_auth.backends import BaseBackend, TokenBackend
"""

__version__ = "0.2.0"
