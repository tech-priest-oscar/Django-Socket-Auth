"""
Settings for the django-socket-auth example project.

This is a local demo only: DEBUG is on and the secret key is public.
"""

from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = "django-insecure-example-only-do-not-use-in-production"
DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "rest_framework",
    "chat",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
]

ROOT_URLCONF = "sample_project.urls"
ASGI_APPLICATION = "sample_project.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": ["django.template.context_processors.request"]
        },
    },
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# Messages between connected clients go through the channel layer. The
# in-memory layer only works within one server process, which is fine for a
# demo; use channels_redis in production.
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

# django-socket-auth reads the same SIMPLE_JWT settings as your REST API.
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
}

# This is the default, shown here so you can see where to plug in your own.
SOCKET_AUTH_BACKENDS = ["django_socket_auth.backends.SimpleJWTBackend"]

USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
