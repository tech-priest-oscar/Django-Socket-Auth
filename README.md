# django-socket-auth example: authenticated chat

A small, standalone Django Channels project that shows how to use
[django-socket-auth](https://pypi.org/project/django-socket-auth/) to
authenticate websocket connections with
[simplejwt](https://django-rest-framework-simplejwt.readthedocs.io/) access
tokens.

A single HTML page lets you:

1. Log in with a username and password and get a JWT back from `/api/token/`
2. Open a websocket to a chat room, passing the token in `?token=`
3. Send messages and see them arrive in every window connected to the same room

There is also a **Connect without token** button, which shows the server
rejecting the connection with close code `4001`.

## Run it

You need Python 3.10 or newer. Run every command from the project root (the
folder with `manage.py`).

### 1. Create and activate a virtual environment

```bash
python -m venv venv
```

Then activate it. The command depends on your shell:

| Shell | Command |
|---|---|
| Windows PowerShell | `.\venv\Scripts\Activate.ps1` |
| Windows Command Prompt | `venv\Scripts\activate.bat` |
| Git Bash on Windows | `source venv/Scripts/activate` |
| macOS / Linux | `source venv/bin/activate` |

Your prompt should now start with `(venv)`.

If PowerShell says "running scripts is disabled on this system", allow scripts
for your user once and try again:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

### 2. Install the dependencies

```bash
pip install -r requirements.txt
```

This installs `django-socket-auth` from PyPI, which pulls in Django, Channels,
Django REST framework and simplejwt. It also installs uvicorn to serve the app.

### 3. Set up the database and demo users

```bash
python manage.py migrate
python manage.py create_demo_users
```

This creates a local SQLite database (`db.sqlite3`) and two users:

| Username | Password |
|---|---|
| `alice` | `demo-pass-123` |
| `bob` | `demo-pass-123` |

Running `create_demo_users` again resets their passwords. You can also add
your own users with `python manage.py createsuperuser`.

### 4. Start the server

```bash
uvicorn sample_project.asgi:application --reload
```

`--reload` restarts the server when you edit a file. Stop it with `Ctrl+C`.

> Don't use `python manage.py runserver`. It only serves plain HTTP, so the
> page loads but the websocket can't connect. You need an ASGI server such
> as uvicorn (or daphne) for websockets.

### 5. Try it in the browser

1. Open http://127.0.0.1:8000.
2. Log in as `alice`. The page shows the start of the access token it got back.
3. Leave the room as `lobby` and click **Connect**. You should see
   *You joined "lobby" as alice.*
4. Type a message and click **Send**. It shows up in the message log.
5. Open a second tab or window at the same address, log in as `bob`, and
   connect to `lobby`. Messages sent from either one now appear in both. Each
   tab keeps its own token in memory, so the two logins don't interfere.
6. Click **Connect without token**. The server rejects the connection and the
   log shows close code `4001`.

### Troubleshooting

| Problem | Fix |
|---|---|
| `uvicorn: command not found` / not recognized | The venv isn't active. Activate it (step 1), or run `python -m uvicorn sample_project.asgi:application --reload`. |
| Login says "No active account found with the given credentials" | Run `python manage.py create_demo_users`, then check the username and password. |
| Connect starts failing with code `4001` after a while | The access token expired (15 minutes here). Log in again. |
| Websocket fails to connect at all | Check you started the server with uvicorn, not `runserver`. |
| `Error: [Errno 10048]` / address already in use | Something else is using port 8000. Add `--port 8001` and open http://127.0.0.1:8001. |
| `no such table: auth_user` | Run `python manage.py migrate`. |

## How the auth works

Two pieces from `django-socket-auth` work together, and you need both:

1. **`SocketAuthMiddleware`** in [sample_project/asgi.py](sample_project/asgi.py)
   wraps the websocket routes. On every connection it reads the token from
   `?token=` (or an `Authorization: Bearer` header) and validates it with
   simplejwt. It then sets `scope["user"]` to that user, or to `AnonymousUser`
   if the token is missing or invalid. It never rejects a connection itself.
2. **`AuthenticatedJsonWebsocketConsumer`**, the base class of `ChatConsumer`
   in [chat/consumers.py](chat/consumers.py), checks `scope["user"]`. If it
   isn't authenticated, the consumer closes the connection with code `4001`.
   Otherwise it sets `self.user` and calls `authenticated_connect()`.

Without the middleware nothing sets `scope["user"]`, so the consumer would
reject every connection, even ones with a valid token.

Browsers can't set headers on a websocket, so the page puts the token in the
URL: `ws://127.0.0.1:8000/ws/chat/lobby/?token=<access token>`.

## Where things are

| File | What it does |
|---|---|
| [sample_project/asgi.py](sample_project/asgi.py) | Wraps the websocket routes in `SocketAuthMiddleware` |
| [sample_project/urls.py](sample_project/urls.py) | The page, plus simplejwt's login (`/api/token/`) and refresh views |
| [sample_project/settings.py](sample_project/settings.py) | `SIMPLE_JWT`, `SOCKET_AUTH_BACKENDS` and an in-memory channel layer |
| [chat/consumers.py](chat/consumers.py) | `ChatConsumer`, built on `AuthenticatedJsonWebsocketConsumer` |
| [chat/routing.py](chat/routing.py) | The websocket URL: `ws/chat/<room>/` |
| [chat/templates/chat/index.html](chat/templates/chat/index.html) | The login and chat page (plain HTML and JavaScript) |
| [chat/management/commands/create_demo_users.py](chat/management/commands/create_demo_users.py) | Creates the demo users |

## Websocket protocol

Connect to `ws://<host>/ws/chat/<room>/?token=<access token>`. Room names may
contain letters, digits, `-` and `_`.

Send:

```json
{"message": "hello"}
```

Receive, once on connect:

```json
{"type": "welcome", "user": "alice", "room": "lobby"}
```

And for every message anyone sends to the room, including you:

```json
{"type": "message", "user": "alice", "message": "hello"}
```

If the token is missing, invalid or expired, the server closes the connection
with code `4001`. Access tokens last 15 minutes in this example; log in again
to get a new one.

## Not for production

This project is a demo. `DEBUG` is on, the secret key is public, and the
in-memory channel layer only works with a single server process. For a real
deployment use [channels_redis](https://github.com/django/channels_redis) and
your own settings.
