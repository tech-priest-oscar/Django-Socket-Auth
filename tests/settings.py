"""Minimal Django settings used only to run the test suite."""

SECRET_KEY = "test-secret-key-not-for-production-use-0123456789"

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
]

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}

USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
