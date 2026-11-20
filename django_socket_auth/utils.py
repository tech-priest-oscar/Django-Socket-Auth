import inspect
import logging

from django.conf import settings
from django.utils.module_loading import import_string

logger = logging.getLogger(__name__)

DEFAULT_BACKENDS = ["django_socket_auth.backends.SimpleJWTBackend"]


def load_backends(backends=None):
    """
    Build backend instances from ``backends`` or, if not given, from the
    ``SOCKET_AUTH_BACKENDS`` setting. Items may be dotted paths, classes or
    instances.
    """
    if backends is None:
        logger.info(
            "no backends provided for use by socket auth, "
            "defaulting to the default setup"
        )
        backends = getattr(settings, "SOCKET_AUTH_BACKENDS", DEFAULT_BACKENDS)

    loaded = []
    for backend in backends:
        if isinstance(backend, str):
            backend = import_string(backend)
        if inspect.isclass(backend):
            backend = backend()
        loaded.append(backend)
    return loaded
