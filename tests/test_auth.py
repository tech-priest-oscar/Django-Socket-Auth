import asyncio
import time
from datetime import timedelta
from unittest import mock

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
from django_socket_auth.enums import CloseCode, MessageType, ScopeKey
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
        self.assertEqual(message["type"], MessageType.CLOSE)
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


# --- Token expiry ------------------------------------------------------------


class EchoConsumer(AuthenticatedJsonWebsocketConsumer):
    """Reports its token expiry on connect, then echoes messages and events."""

    instances = []

    async def authenticated_connect(self):
        type(self).instances.append(self)
        await self.accept()
        await self.send_json({"expires_at": self.token_expires_at})

    async def receive_json(self, content, **kwargs):
        await self.send_json({"echo": content})

    async def server_event(self, event):
        # Stands in for a channel-layer group message, e.g. "chat.message".
        await self.send_json({"event": event["text"]})


class ExpiringApiKeyBackend(ApiKeyBackend):
    """Like ApiKeyBackend, but the token expires ``lifetime`` seconds from now."""

    lifetime = 60.0

    def get_token_expiry(self, token):
        return time.time() + self.lifetime


class SetsExpiryThenFailsBackend(BaseBackend):
    def authenticate(self, scope):
        scope[ScopeKey.TOKEN_EXPIRES_AT] = time.time() - 100
        return None


def make_echo_app(backends):
    return SocketAuthMiddleware(
        URLRouter([path("ws/", EchoConsumer.as_asgi())]), auth_backends=backends
    )


class TokenExpiryTests(TransactionTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="alice", password="x")
        EchoConsumer.instances.clear()

    async def connect(self, app, path="/ws/?token=alice-api-key"):
        ws = WebsocketCommunicator(app, path)
        connected, _ = await ws.connect()
        self.assertTrue(connected)
        return ws, (await ws.receive_json_from())["expires_at"]

    async def assert_closed_for_expiry(self, ws, timeout=1):
        message = await ws.receive_output(timeout=timeout)
        self.assertEqual(message["type"], MessageType.CLOSE)
        self.assertEqual(message["code"], CloseCode.UNAUTHENTICATED)

    async def test_simplejwt_records_token_expiry(self):
        token = AccessToken.for_user(self.user)
        ws, expires_at = await self.connect(
            make_echo_app(["django_socket_auth.backends.SimpleJWTBackend"]),
            f"/ws/?token={token}",
        )
        self.assertEqual(expires_at, token["exp"])
        await ws.disconnect()

    async def test_timer_closes_idle_connection_at_expiry(self):
        backend = ExpiringApiKeyBackend()
        backend.lifetime = 0.3
        ws, _ = await self.connect(make_echo_app([backend]))
        self.assertTrue(await ws.receive_nothing(timeout=0.1))  # still open
        await self.assert_closed_for_expiry(ws, timeout=2)

    async def test_client_message_after_expiry_is_dropped(self):
        ws, expires_at = await self.connect(make_echo_app([ExpiringApiKeyBackend]))
        await ws.send_json_to({"before": "expiry"})
        self.assertEqual(await ws.receive_json_from(), {"echo": {"before": "expiry"}})

        # The timer won't fire for a minute; the per-message check must catch it.
        with mock.patch.object(EchoConsumer, "_now", return_value=expires_at + 1):
            await ws.send_json_to({"after": "expiry"})
            await self.assert_closed_for_expiry(ws)
            self.assertTrue(await ws.receive_nothing())  # no echo

    async def test_server_event_after_expiry_is_not_delivered(self):
        ws, expires_at = await self.connect(make_echo_app([ExpiringApiKeyBackend]))
        with mock.patch.object(EchoConsumer, "_now", return_value=expires_at + 1):
            await ws.send_input({"type": "server.event", "text": "secret"})
            await self.assert_closed_for_expiry(ws)
            self.assertTrue(await ws.receive_nothing())

    async def test_backend_without_expiry_never_times_out(self):
        ws, expires_at = await self.connect(make_echo_app([ApiKeyBackend]))
        self.assertIsNone(expires_at)
        self.assertIsNone(EchoConsumer.instances[0]._expiry_task)
        await ws.disconnect()

    async def test_failed_backend_cannot_leave_an_expiry_behind(self):
        app = make_echo_app([SetsExpiryThenFailsBackend, ApiKeyBackend])
        ws, expires_at = await self.connect(app)
        self.assertIsNone(expires_at)
        await ws.disconnect()

    async def test_timer_is_cancelled_when_connection_closes(self):
        ws, _ = await self.connect(make_echo_app([ExpiringApiKeyBackend]))
        task = EchoConsumer.instances[0]._expiry_task
        self.assertFalse(task.done())
        await ws.disconnect()
        await asyncio.sleep(0)
        self.assertTrue(task.cancelled())
