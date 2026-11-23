"""
Authentication backends for ``SocketAuthMiddleware``.

A backend is any object with an ``authenticate(scope)`` method that returns a
user, or ``None`` to let the next backend try. It may be a normal method (run
in a worker thread, so the Django ORM is safe to use) or an ``async def``.

A backend that knows when the user's credentials expire can record it as a
Unix timestamp in ``scope[ScopeKey.TOKEN_EXPIRES_AT]``. Authenticated
consumers then close the connection once that time passes.
"""

import inspect
from urllib.parse import parse_qs

from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed, InvalidToken

from django_socket_auth.enums import ScopeKey


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

    Override :meth:`get_token_expiry` to have connections closed when the
    token expires.
    """

    def authenticate(self, scope):
        token = self.get_raw_token(scope)
        if not token:
            return None

        user = self.authenticate_token(token)
        if inspect.isawaitable(user):
            # authenticate_token is async; the middleware awaits this.
            return self._finish_async(user, token, scope)
        return self._record_expiry(user, token, scope)

    def authenticate_token(self, token):
        """Return the user ``token`` belongs to, or ``None`` if it is invalid."""
        raise NotImplementedError

    def get_token_expiry(self, token):
        """
        Return when ``token`` expires as a Unix timestamp, or ``None`` if it
        doesn't expire. Only called after the token authenticated a user.
        """
        return None

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

    async def _finish_async(self, user, token, scope):
        return self._record_expiry(await user, token, scope)

    def _record_expiry(self, user, token, scope):
        if getattr(user, "is_authenticated", False):
            expires_at = self.get_token_expiry(token)
            if expires_at is not None:
                scope[ScopeKey.TOKEN_EXPIRES_AT] = float(expires_at)
        return user


class SimpleJWTBackend(TokenBackend):
    """Validates djangorestframework-simplejwt access tokens (the default)."""

    def authenticate_token(self, token):
        auth = JWTAuthentication()
        try:
            return auth.get_user(auth.get_validated_token(token))
        except (InvalidToken, AuthenticationFailed):
            return None

    def get_token_expiry(self, token):
        try:
            validated = JWTAuthentication().get_validated_token(token)
        except InvalidToken:
            return None
        return validated.get("exp")
