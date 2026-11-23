import asyncio
import time

from channels.generic.websocket import (
    AsyncJsonWebsocketConsumer,
    AsyncWebsocketConsumer,
)

from django_socket_auth.enums import CloseCode, MessageType, ScopeKey

# Kept for backwards compatibility; prefer CloseCode.UNAUTHENTICATED.
UNAUTHENTICATED_CLOSE_CODE = CloseCode.UNAUTHENTICATED


class SocketAuthConsumerMixin:
    """
    Only lets authenticated users connect, and disconnects them when their
    token expires.

    Requires ``SocketAuthMiddleware`` (or any middleware that sets
    ``scope["user"]``). Unauthenticated connections are accepted and then
    immediately closed with ``unauthenticated_close_code`` so the client can
    tell an auth failure apart from other errors.

    Override :meth:`authenticated_connect` instead of ``connect``; ``self.user``
    is set by then. The default implementation just accepts the connection.

    If the backend recorded when the token expires
    (``scope["token_expires_at"]``), two checks enforce it:

    * Every incoming message, from the client or from the channel layer, is
      checked first. Once the token has expired the message is dropped and the
      connection is closed, so nothing is processed or delivered after expiry.
    * A timer closes idle connections when the token expires. It is cleanup
      only; the per-message check is what guarantees no data gets through.

    Both close with ``token_expired_close_code``.
    """

    unauthenticated_close_code = CloseCode.UNAUTHENTICATED
    token_expired_close_code = CloseCode.UNAUTHENTICATED

    _expiry_task = None
    _closed_for_expiry = False

    async def __call__(self, scope, receive, send):
        # The timer must never outlive the connection, however the consumer
        # stops: a normal disconnect, an exception or cancellation.
        try:
            return await super().__call__(scope, receive, send)
        finally:
            self._cancel_expiry_timer()

    async def connect(self):
        user = self.scope.get(ScopeKey.USER)
        if user is None or not user.is_authenticated or self.token_has_expired():
            await self.accept()
            await self.close(code=self.unauthenticated_close_code)
            return

        self.user = user
        await self.authenticated_connect()
        self._start_expiry_timer()

    async def authenticated_connect(self):
        await self.accept()

    @property
    def token_expires_at(self):
        """Unix timestamp the token expires at, or ``None`` if unknown."""
        return self.scope.get(ScopeKey.TOKEN_EXPIRES_AT)

    def token_has_expired(self):
        expires_at = self.token_expires_at
        return expires_at is not None and self._now() >= expires_at

    async def dispatch(self, message):
        if (
            message["type"] not in (MessageType.CONNECT, MessageType.DISCONNECT)
            and self.token_has_expired()
        ):
            await self.close_for_expired_token()
            return  # drop the message: never process or deliver it
        await super().dispatch(message)

    async def close_for_expired_token(self):
        if self._closed_for_expiry:
            return
        self._closed_for_expiry = True
        self._cancel_expiry_timer()
        await self.close(code=self.token_expired_close_code)

    def _start_expiry_timer(self):
        if self.token_expires_at is not None:
            self._expiry_task = asyncio.ensure_future(self._close_when_token_expires())

    async def _close_when_token_expires(self):
        await asyncio.sleep(max(0.0, self.token_expires_at - self._now()))
        await self.close_for_expired_token()

    def _cancel_expiry_timer(self):
        task = self._expiry_task
        # Don't cancel the timer from inside itself: it is about to close.
        if task is not None and task is not asyncio.current_task():
            task.cancel()

    @staticmethod
    def _now():
        return time.time()


class AuthenticatedWebsocketConsumer(SocketAuthConsumerMixin, AsyncWebsocketConsumer):
    pass


class AuthenticatedJsonWebsocketConsumer(
    SocketAuthConsumerMixin, AsyncJsonWebsocketConsumer
):
    pass
