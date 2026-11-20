from channels.generic.websocket import (
    AsyncJsonWebsocketConsumer,
    AsyncWebsocketConsumer,
)

# 4000-4999 are free for application use; 4001 mirrors HTTP 401.
UNAUTHENTICATED_CLOSE_CODE = 4001


class SocketAuthConsumerMixin:
    """
    Only lets authenticated users connect.

    Requires ``SocketAuthMiddleware`` (or any middleware that sets
    ``scope["user"]``). Unauthenticated connections are accepted and then
    immediately closed with ``unauthenticated_close_code`` so the client can
    tell an auth failure apart from other errors.

    Override :meth:`authenticated_connect` instead of ``connect``; ``self.user``
    is set by then. The default implementation just accepts the connection.
    """

    unauthenticated_close_code = UNAUTHENTICATED_CLOSE_CODE

    async def connect(self):
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.accept()
            await self.close(code=self.unauthenticated_close_code)
            return

        self.user = user
        await self.authenticated_connect()

    async def authenticated_connect(self):
        await self.accept()


class AuthenticatedWebsocketConsumer(SocketAuthConsumerMixin, AsyncWebsocketConsumer):
    pass


class AuthenticatedJsonWebsocketConsumer(
    SocketAuthConsumerMixin, AsyncJsonWebsocketConsumer
):
    pass
