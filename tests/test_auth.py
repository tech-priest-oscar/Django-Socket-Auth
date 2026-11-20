from datetime import timedelta

from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TransactionTestCase
from django.urls import path
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from django_socket_auth.backends import BaseBackend, TokenBackend
from django_socket_auth.consumers import (
    UNAUTHENTICATED_CLOSE_CODE,
    AuthenticatedJsonWebsocketConsumer,
)
from django_socket_auth.middleware import SocketAuthMiddleware


class WhoAmIConsumer(AuthenticatedJsonWebsocketConsumer):
    async def authenticated_connect(self):
        await self.accept()
        await self.send_json({"user": self.user.get_username()})


application = SocketAuthMiddleware(URLRouter([path("ws/", WhoAmIConsumer.as_asgi())]))


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


# --- Custom backends -------------------------------------------------------


class HeaderUsernameBackend(BaseBackend):
    """Sync backend: trusts an ``x-username`` header (test only!)."""

    def authenticate(self, scope):
        headers = dict(scope["headers"])
        username = headers.get(b"x-username", b"").decode()
        return get_user_model().objects.filter(username=username).first()


class AsyncHeaderUsernameBackend(BaseBackend):
    async def authenticate(self, scope):
        username = dict(scope["headers"]).get(b"x-username", b"").decode()
        return await get_user_model().objects.filter(username=username).afirst()


class ApiKeyBackend(TokenBackend):
    """Reuses the token extraction; only maps the token to a user."""

    def authenticate_token(self, token):
        if token == "alice-api-key":
            return get_user_model().objects.get(username="alice")
        return None


class AsyncApiKeyBackend(TokenBackend):
    async def authenticate_token(self, token):
        if token == "alice-api-key":
            return await get_user_model().objects.aget(username="alice")
        return None


class NeverBackend(BaseBackend):
    def authenticate(self, scope):
        return None


class AnonymousBackend(BaseBackend):
    def authenticate(self, scope):
        return AnonymousUser()


def make_app(backends=None):
    return SocketAuthMiddleware(
        URLRouter([path("ws/", WhoAmIConsumer.as_asgi())]), auth_backends=backends
    )


class CustomBackendTests(TransactionTestCase):
    def setUp(self):
        get_user_model().objects.create_user(username="alice", password="x")

    async def connect(self, app, path="/ws/", headers=None):
        ws = WebsocketCommunicator(app, path, headers=headers or [])
        connected, _ = await ws.connect()
        self.assertTrue(connected)
        return ws

    async def assert_alice(self, ws):
        self.assertEqual(await ws.receive_json_from(), {"user": "alice"})
        await ws.disconnect()

    async def assert_rejected(self, ws):
        message = await ws.receive_output()
        self.assertEqual(message["code"], UNAUTHENTICATED_CLOSE_CODE)

    async def test_sync_and_async_backends(self):
        for backend in (HeaderUsernameBackend, AsyncHeaderUsernameBackend):
            app = make_app([backend])
            await self.assert_alice(
                await self.connect(app, headers=[(b"x-username", b"alice")])
            )
            await self.assert_rejected(
                await self.connect(app, headers=[(b"x-username", b"bob")])
            )

    async def test_token_backend_subclasses(self):
        for backend in (ApiKeyBackend, AsyncApiKeyBackend):
            app = make_app([backend()])
            await self.assert_alice(await self.connect(app, "/ws/?token=alice-api-key"))
            await self.assert_rejected(await self.connect(app, "/ws/?token=wrong"))
            await self.assert_rejected(await self.connect(app))

    async def test_backends_are_tried_in_order(self):
        app = make_app([NeverBackend, "tests.test_auth.ApiKeyBackend"])
        await self.assert_alice(await self.connect(app, "/ws/?token=alice-api-key"))

    async def test_anonymous_user_counts_as_failure(self):
        app = make_app([AnonymousBackend, ApiKeyBackend])
        await self.assert_alice(await self.connect(app, "/ws/?token=alice-api-key"))
        await self.assert_rejected(await self.connect(app))

    async def test_backends_from_settings(self):
        with self.settings(SOCKET_AUTH_BACKENDS=["tests.test_auth.ApiKeyBackend"]):
            app = make_app()
        await self.assert_alice(await self.connect(app, "/ws/?token=alice-api-key"))

    async def test_default_backend_is_simplejwt(self):
        user = await get_user_model().objects.aget(username="alice")
        token = str(AccessToken.for_user(user))
        await self.assert_alice(await self.connect(make_app(), f"/ws/?token={token}"))
