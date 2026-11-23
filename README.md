# django-socket-auth

[![PyPI version](https://img.shields.io/pypi/v/django-socket-auth.svg)](https://pypi.org/project/django-socket-auth/)
[![Python versions](https://img.shields.io/pypi/pyversions/django-socket-auth.svg)](https://pypi.org/project/django-socket-auth/)
[![License: MIT](https://img.shields.io/pypi/l/django-socket-auth.svg)](https://github.com/tech-priest-oscar/Django-Socket-Auth/blob/master/LICENSE)

Pluggable authentication for [Django Channels](https://channels.readthedocs.io/)
websocket consumers.

Out of the box it authenticates websocket connections with the same access
tokens your REST API already issues through
[djangorestframework-simplejwt](https://django-rest-framework-simplejwt.readthedocs.io/),
so clients log in once and use one token for both HTTP and websockets. You can
also plug in your own authentication: return a user and it goes into
`scope["user"]`.

- Works with the default Django user model or any custom one
- Bring your own auth with a small backend class (sync or async)
- Accepts the token in a header **or** the query string (for browsers)
- Respects your existing `SIMPLE_JWT` settings
- No models, no migrations, nothing to add to `INSTALLED_APPS`

## Requirements

- Python 3.10+
- Django 4.2+
- Channels 4.0+
- djangorestframework-simplejwt 5.3+

## Installation

```bash
pip install django-socket-auth
```

To try the latest unreleased code from GitHub instead:

```bash
pip install git+https://github.com/tech-priest-oscar/Django-Socket-Auth.git
```

Your project needs simplejwt set up to issue tokens. If it isn't already, add
its views to your `urls.py`:

```python
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [
    path("api/token/", TokenObtainPairView.as_view()),
    path("api/token/refresh/", TokenRefreshView.as_view()),
]
```

## Quick start

### 1. Wrap your websocket routes with the middleware

```python
# asgi.py
import os

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "myproject.settings")
django_asgi_app = get_asgi_application()

# Import anything that touches models *after* get_asgi_application()
from django_socket_auth.middleware import SocketAuthMiddleware
from myapp.routing import websocket_urlpatterns

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": SocketAuthMiddleware(URLRouter(websocket_urlpatterns)),
})
```

### 2. Subclass an authenticated consumer

```python
# myapp/consumers.py
from django_socket_auth.consumers import AuthenticatedJsonWebsocketConsumer


class ChatConsumer(AuthenticatedJsonWebsocketConsumer):
    async def authenticated_connect(self):
        # Only called for authenticated users. self.user is already set.
        await self.accept()
        await self.send_json({"hello": self.user.get_username()})

    async def receive_json(self, content):
        ...
```

Override `authenticated_connect()` instead of `connect()`. The default
implementation just calls `self.accept()`.

### 3. Connect from a client

```js
// Browsers can't set headers on websockets, so pass the token in the URL.
const socket = new WebSocket(`wss://example.com/ws/chat/?token=${accessToken}`);

socket.addEventListener("close", (event) => {
  if (event.code === 4001) {
    // Not authenticated: refresh the access token and reconnect.
  }
});
```

From a non-browser client, prefer a header:

```python
import websockets

async with websockets.connect(
    "wss://example.com/ws/chat/",
    additional_headers={"Authorization": f"Bearer {access_token}"},
) as ws:
    ...
```

## How it works

### Middleware

`SocketAuthMiddleware` asks each configured backend, in order, to authenticate
the connection. The first authenticated user returned is put in
`scope["user"]`. A backend that returns `None` or `AnonymousUser` has failed,
and the next backend is tried. If every backend fails, `scope["user"]` is set
to `AnonymousUser`.

The default backend, `SimpleJWTBackend`, reads the access token from the
handshake, in this order:

1. `Authorization: Bearer <access>` header
2. `?token=<access>` query string

It then validates the token with simplejwt. If the token is missing,
malformed, expired, the wrong type (for example a refresh token), or belongs to
an inactive or deleted user, it returns no user.

The middleware never rejects a connection by itself. That is up to the
consumer, so you can still serve anonymous users on some routes if you want.

### Consumers

| Class | Use it for |
|---|---|
| `AuthenticatedWebsocketConsumer` | Text or bytes messages (`AsyncWebsocketConsumer`) |
| `AuthenticatedJsonWebsocketConsumer` | JSON messages (`AsyncJsonWebsocketConsumer`) |
| `SocketAuthConsumerMixin` | Adding the check to your own consumer base class |

Unauthenticated connections are accepted and then immediately closed with
code **4001**, so the client can tell an auth failure apart from other errors.
To use a different code, set `unauthenticated_close_code` on your consumer:

```python
class ChatConsumer(AuthenticatedJsonWebsocketConsumer):
    unauthenticated_close_code = 4003
```

To use the mixin with your own base class, put it first:

```python
from channels.generic.websocket import AsyncWebsocketConsumer
from django_socket_auth.consumers import SocketAuthConsumerMixin


class MyBaseConsumer(SocketAuthConsumerMixin, AsyncWebsocketConsumer):
    ...
```

## Custom authentication

A backend is a class with an `authenticate(scope)` method. Return a user to
authenticate the connection, or `None` to let the next backend try.

`authenticate` can be a normal method or an `async def`. Normal methods run in
a worker thread, so you can use the Django ORM directly.

### Backend interface

These are the methods the package calls. Subclassing `BaseBackend` or
`TokenBackend` is optional: any class with an `authenticate(scope)` method
works.

**`BaseBackend`**: implement your own authentication from scratch.

| Method | Required | Receives | Must return |
|---|---|---|---|
| `authenticate(self, scope)` | Yes | The ASGI connection [`scope`](https://asgi.readthedocs.io/en/latest/specs/www.html#websocket-connection-scope) dict | A user object, or `None` |

**`TokenBackend`**: the package finds the token; you check it.

| Method | Required | Receives | Must return |
|---|---|---|---|
| `authenticate_token(self, token)` | Yes | The raw token string (never empty) | A user object, or `None` |
| `get_raw_token(self, scope)` | No (override to read the token from elsewhere) | The ASGI connection `scope` dict | The token string, or `None` |

Do not override `authenticate` on a `TokenBackend`. It is what calls
`get_raw_token` and then `authenticate_token`.

Each method can be a normal `def` or an `async def`.

#### Rules for every backend

- **Return `None` (or `AnonymousUser()`) when you can't authenticate the
  connection.** Both count as a failed attempt, and the next backend is tried.
- **Don't raise for a bad or missing credential.** Return `None` instead. An
  exception raised from a backend is not caught, so the connection fails with a
  server error instead of being closed with `4001`.
- **Don't store per-connection data on `self`.** One instance of each backend
  is created when the middleware is built and shared by every connection,
  including connections handled at the same time.
- **The user you return is put into `scope["user"]` as is.** The consumers
  check `user.is_authenticated`, so return a real user model instance (or any
  object with `is_authenticated = True`).

#### Full sample

```python
# myapp/socket_auth.py
from django_socket_auth.backends import BaseBackend, TokenBackend

from myapp.models import ApiKey


class MyBackend(BaseBackend):
    """Your own authentication, from scratch."""

    def authenticate(self, scope):
        """
        scope["headers"]      -> list of (name, value) byte pairs, names lower-case
        scope["query_string"] -> raw query string bytes, e.g. b"token=abc"
        scope["path"]         -> e.g. "/ws/chat/"
        scope["client"]       -> (ip, port)

        Return a user to authenticate the connection, or None to let the next
        backend try.
        """
        headers = dict(scope["headers"])
        api_key = headers.get(b"x-api-key", b"").decode("latin1")
        if not api_key:
            return None
        key = ApiKey.objects.select_related("user").filter(key=api_key).first()
        return key.user if key else None


class MyTokenBackend(TokenBackend):
    """The token comes from `Authorization: Bearer ...` or `?token=...`."""

    def authenticate_token(self, token):
        """`token` is the raw token string. Return its user, or None."""
        key = ApiKey.objects.select_related("user").filter(key=token).first()
        return key.user if key else None

    # Optional: only if the token lives somewhere else.
    # def get_raw_token(self, scope):
    #     return dict(scope["headers"]).get(b"x-api-key", b"").decode() or None


class MyAsyncTokenBackend(TokenBackend):
    """Same as above, written with `async def`."""

    async def authenticate_token(self, token):
        key = await ApiKey.objects.select_related("user").filter(key=token).afirst()
        return key.user if key else None
```

Then turn it on (see [Turning backends on](#turning-backends-on)):

```python
SOCKET_AUTH_BACKENDS = ["myapp.socket_auth.MyTokenBackend"]
```

### Use your own auth: return a user

Subclass `BaseBackend` when you already have a way to work out the user, for
example from a session, a signed cookie or another service:

```python
from django_socket_auth.backends import BaseBackend

from myapp.auth import user_from_cookie


class MyCookieBackend(BaseBackend):
    def authenticate(self, scope):
        headers = dict(scope["headers"])
        return user_from_cookie(headers.get(b"cookie", b""))  # user or None
```

### Reuse the token handling: check the token yourself

Subclass `TokenBackend` when clients send a token, but it isn't a simplejwt
token (for example an API key or a token from another provider). It reads
the token from the header or query string for you; you only turn it into a
user:

```python
from django_socket_auth.backends import TokenBackend

from myapp.models import ApiKey


class ApiKeyBackend(TokenBackend):
    def authenticate_token(self, token):
        key = ApiKey.objects.select_related("user").filter(key=token).first()
        return key.user if key else None
```

`authenticate_token` can also be `async def`. To read the token from somewhere
else, override `get_raw_token(scope)` as well.

### Turning backends on

For the whole project, in `settings.py`:

```python
SOCKET_AUTH_BACKENDS = [
    "myapp.socket_auth.ApiKeyBackend",
    "django_socket_auth.backends.SimpleJWTBackend",  # keep JWT working too
]
```

Or for one set of routes, when building the middleware:

```python
SocketAuthMiddleware(URLRouter(websocket_urlpatterns), auth_backends=[ApiKeyBackend])
```

`auth_backends` takes dotted paths, classes or instances. Passing it overrides
`SOCKET_AUTH_BACKENDS` for that middleware.

## Configuration

| Setting | Default | |
|---|---|---|
| `SOCKET_AUTH_BACKENDS` | `["django_socket_auth.backends.SimpleJWTBackend"]` | Backends to try, in order |

`SimpleJWTBackend` validates tokens with your project's
[`SIMPLE_JWT` settings](https://django-rest-framework-simplejwt.readthedocs.io/en/latest/settings.html)
(signing key, algorithm, token lifetimes, user ID claim, and so on).

## Security notes

- **Query-string tokens can end up in logs.** Proxies and servers often log
  full URLs. Keep access tokens short-lived, or use a header where the client
  supports it.
- **Use `wss://` in production** so tokens are not sent in plain text.
- **The user is checked once, at connect time.** A connection stays open after
  its token expires. Close long-lived connections yourself if that matters.

## Development

```bash
python -m venv venv
venv/bin/pip install -r requirements.txt
make pre-commit-install

make test         # run the test suite
make pre-commit   # format and lint everything
```
