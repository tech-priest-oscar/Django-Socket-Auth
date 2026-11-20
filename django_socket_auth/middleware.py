"""ASGI middleware that authenticates websocket connections with SimpleJWT tokens."""

from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed, InvalidToken


class JWTAuthMiddleware(BaseMiddleware):
    """
    Populates ``scope["user"]`` with the user owning the access token sent on
    the websocket handshake, or ``AnonymousUser`` if it is missing or invalid.
    """

    async def __call__(self, scope, receive, send):
        scope = dict(scope)
        scope["user"] = await self.get_user(self.get_raw_token(scope))
        return await super().__call__(scope, receive, send)

    def get_raw_token(self, scope):
        """
        Pull the raw access token out of the connection scope.

        Checked in order:
          1. ``Authorization: Bearer <token>`` header
          2. ``token: <token>`` header
          3. ``?token=<token>`` query string (browsers cannot set websocket headers)
        """
        headers = {
            key.decode("latin1").lower(): value.decode("latin1")
            for key, value in scope.get("headers", [])
        }

        auth_header = headers.get("authorization", "")
        scheme, _, credentials = auth_header.partition(" ")
        if scheme.lower() == "bearer" and credentials:
            return credentials.strip()

        if headers.get("token"):
            return headers["token"].strip()

        query = parse_qs(scope.get("query_string", b"").decode("latin1"))
        if query.get("token"):
            return query["token"][0]

        return None

    @database_sync_to_async
    def get_user(self, raw_token):
        """Validate ``raw_token`` and return its user, or ``AnonymousUser``."""
        if not raw_token:
            return AnonymousUser()

        auth = JWTAuthentication()
        try:
            validated = auth.get_validated_token(raw_token)
            return auth.get_user(validated)
        except (InvalidToken, AuthenticationFailed):
            return AnonymousUser()
