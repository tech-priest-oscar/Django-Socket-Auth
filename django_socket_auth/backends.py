"""
Authentication backends for ``SocketAuthMiddleware``.

A backend is any object with an ``authenticate(scope)`` method that returns a
user, or ``None`` to let the next backend try. It may be a normal method (run
in a worker thread, so the Django ORM is safe to use) or an ``async def``.
"""

from urllib.parse import parse_qs

from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed, InvalidToken


class BaseBackend:
    """Implement ``authenticate(scope)``; return a user or ``None``."""

    def authenticate(self, scope):
        raise NotImplementedError


class TokenBackend(BaseBackend):
    """
    Reads a token from the handshake and hands it to
    :meth:`authenticate_token`, which subclasses implement.

    The token is looked for in, in order:
      1. ``Authorization: Bearer <token>`` header
      2. ``?token=<token>`` query string (browsers cannot set websocket headers)
    """

    def authenticate(self, scope):
        token = self.get_raw_token(scope)
        return self.authenticate_token(token) if token else None

    def authenticate_token(self, token):
        """Return the user ``token`` belongs to, or ``None`` if it is invalid."""
        raise NotImplementedError

    def get_raw_token(self, scope):
        headers = {
            key.decode("latin1").lower(): value.decode("latin1")
            for key, value in scope.get("headers", [])
        }

        scheme, _, credentials = headers.get("authorization", "").partition(" ")
        if scheme.lower() == "bearer" and credentials.strip():
            return credentials.strip()

        query = parse_qs(scope.get("query_string", b"").decode("latin1"))
        if query.get("token"):
            return query["token"][0]

        return None


class SimpleJWTBackend(TokenBackend):
    """Validates djangorestframework-simplejwt access tokens (the default)."""

    def authenticate_token(self, token):
        auth = JWTAuthentication()
        try:
            return auth.get_user(auth.get_validated_token(token))
        except (InvalidToken, AuthenticationFailed):
            return None
