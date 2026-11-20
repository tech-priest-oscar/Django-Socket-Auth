from datetime import timedelta

from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase
from django.urls import path
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from django_socket_auth.consumers import (
    UNAUTHENTICATED_CLOSE_CODE,
    AuthenticatedJsonWebsocketConsumer,
)
from django_socket_auth.middleware import JWTAuthMiddleware


class WhoAmIConsumer(AuthenticatedJsonWebsocketConsumer):
    async def authenticated_connect(self):
        await self.accept()
        await self.send_json({"user": self.user.get_username()})


application = JWTAuthMiddleware(URLRouter([path("ws/", WhoAmIConsumer.as_asgi())]))


class JWTSocketAuthTests(TransactionTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="alice", password="s3cret-pass"
        )
        self.access = str(AccessToken.for_user(self.user))

    async def connect(self, path="/ws/", headers=None):
        ws = WebsocketCommunicator(application, path, headers=headers or [])
        connected, _ = await ws.connect()
        self.assertTrue(connected)
        return ws

    async def assert_accepted(self, ws):
        self.assertEqual(await ws.receive_json_from(), {"user": "alice"})
        await ws.disconnect()

    async def assert_rejected(self, ws):
        message = await ws.receive_output()
        self.assertEqual(message["type"], "websocket.close")
        self.assertEqual(message["code"], UNAUTHENTICATED_CLOSE_CODE)

    async def test_bearer_header(self):
        headers = [(b"authorization", f"Bearer {self.access}".encode())]
        await self.assert_accepted(await self.connect(headers=headers))

    async def test_token_header(self):
        headers = [(b"token", self.access.encode())]
        await self.assert_accepted(await self.connect(headers=headers))

    async def test_query_string(self):
        await self.assert_accepted(await self.connect(f"/ws/?token={self.access}"))

    async def test_missing_token(self):
        await self.assert_rejected(await self.connect())

    async def test_malformed_token(self):
        await self.assert_rejected(await self.connect("/ws/?token=not-a-jwt"))

    async def test_expired_token(self):
        token = AccessToken.for_user(self.user)
        token.set_exp(lifetime=-timedelta(seconds=1))
        await self.assert_rejected(await self.connect(f"/ws/?token={token}"))

    async def test_refresh_token_is_not_accepted(self):
        refresh = str(RefreshToken.for_user(self.user))
        await self.assert_rejected(await self.connect(f"/ws/?token={refresh}"))

    async def test_inactive_user(self):
        self.user.is_active = False
        await self.user.asave()
        await self.assert_rejected(await self.connect(f"/ws/?token={self.access}"))
