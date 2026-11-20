"""ASGI middleware that authenticates websocket connections."""

import inspect

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser

from django_socket_auth.utils import load_backends


class SocketAuthMiddleware(BaseMiddleware):
    """
    Sets ``scope["user"]`` to the first authenticated user returned by the
    configured backends, or ``AnonymousUser`` if none of them authenticate the
    connection. A backend returning ``None`` or ``AnonymousUser`` counts as a
    failed attempt, and the next backend is tried.

        SocketAuthMiddleware(inner)                          # SOCKET_AUTH_BACKENDS
        SocketAuthMiddleware(inner, auth_backends=[MyBackend])  # per-route override
    """

    def __init__(self, inner, auth_backends=None):
        super().__init__(inner)
        self.auth_backends = load_backends(auth_backends)

    async def __call__(self, scope, receive, send):
        scope = dict(scope)
        scope["user"] = await self.get_user(scope)
        return await super().__call__(scope, receive, send)

    async def get_user(self, scope):
        for backend in self.auth_backends:
            if inspect.iscoroutinefunction(backend.authenticate):
                user = await backend.authenticate(scope)
            else:
                user = await database_sync_to_async(backend.authenticate)(scope)
            if inspect.isawaitable(user):
                # e.g. a TokenBackend whose authenticate_token is async
                user = await user
            # None or AnonymousUser (anything not authenticated) means this
            # backend failed; try the next one.
            if getattr(user, "is_authenticated", False):
                return user
        return AnonymousUser()
