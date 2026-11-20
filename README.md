# django-socket-auth

JWT authentication for [Django Channels](https://channels.readthedocs.io/)
websocket consumers.

It authenticates websocket connections with the same access tokens your REST
API already issues through
[djangorestframework-simplejwt](https://django-rest-framework-simplejwt.readthedocs.io/),
so clients log in once and use one token for both HTTP and websockets.

- Works with the default Django user model or any custom one
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
from django_socket_auth.middleware import JWTAuthMiddleware
from myapp.routing import websocket_urlpatterns

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": JWTAuthMiddleware(URLRouter(websocket_urlpatterns)),
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

`JWTAuthMiddleware` reads the access token from the handshake, in this order:

1. `Authorization: Bearer <access>` header
2. `token: <access>` header
3. `?token=<access>` query string

It then validates the token with simplejwt and sets `scope["user"]` to the
token's user. If the token is missing, malformed, expired, the wrong type (for
example a refresh token), or belongs to an inactive or deleted user,
`scope["user"]` is set to `AnonymousUser` instead.

The middleware never rejects a connection by itself. That is up to the
consumer, so you can still serve anonymous users on some routes if you want.

### Consumers

| Class | Use it for |
|---|---|
| `AuthenticatedWebsocketConsumer` | Text or bytes messages (`AsyncWebsocketConsumer`) |
| `AuthenticatedJsonWebsocketConsumer` | JSON messages (`AsyncJsonWebsocketConsumer`) |
| `JWTAuthConsumerMixin` | Adding the check to your own consumer base class |

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
from django_socket_auth.consumers import JWTAuthConsumerMixin


class MyBaseConsumer(JWTAuthConsumerMixin, AsyncWebsocketConsumer):
    ...
```

### Customising the middleware

`JWTAuthMiddleware` has two methods you can override in a subclass:

| Method | Description |
|---|---|
| `get_raw_token(scope)` | Returns the raw token string from the scope, or `None` |
| `await get_user(raw_token)` | Returns the token's user, or `AnonymousUser` |

For example, to read the token only from a cookie:

```python
from http.cookies import SimpleCookie

from django_socket_auth.middleware import JWTAuthMiddleware


class CookieJWTAuthMiddleware(JWTAuthMiddleware):
    def get_raw_token(self, scope):
        headers = dict(scope.get("headers", []))
        cookie = SimpleCookie(headers.get(b"cookie", b"").decode("latin1"))
        return cookie["access"].value if "access" in cookie else None
```

## Configuration

There are no settings of its own. Token validation uses your project's
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
