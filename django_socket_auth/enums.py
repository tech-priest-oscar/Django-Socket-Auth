"""
Named constants used across the package.

The string enums subclass ``str`` and the close codes subclass ``int``, so
members compare equal to the plain values (``MessageType.DISCONNECT ==
"websocket.disconnect"``) and can be used anywhere those values are expected.
"""

from enum import Enum, IntEnum


class StrEnum(str, Enum):
    """``enum.StrEnum`` for Python 3.10, which doesn't have it."""

    def __str__(self):
        return self.value


class CloseCode(IntEnum):
    """
    Websocket close codes sent by authenticated consumers.

    4000-4999 are reserved for application use by the websocket spec.
    """

    # Mirrors HTTP 401. Used for a missing, invalid or expired token, so a
    # client handles every case the same way: refresh the token and reconnect.
    UNAUTHENTICATED = 4001


class MessageType(StrEnum):
    """ASGI websocket message types."""

    # Received by the consumer
    CONNECT = "websocket.connect"
    RECEIVE = "websocket.receive"
    DISCONNECT = "websocket.disconnect"
    # Sent by the consumer
    CLOSE = "websocket.close"


class ScopeKey(StrEnum):
    """Keys this package reads from or writes to the connection ``scope``."""

    USER = "user"
    # Unix timestamp (seconds) at which the connection's token expires.
    TOKEN_EXPIRES_AT = "token_expires_at"
