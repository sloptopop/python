"""Exceptions raised by the sloptopop client."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sloptopop._json import JsonValue


class SloptopopError(Exception):
    """Base class of every error raised by this package."""


class TransportError(SloptopopError):
    """The binary could not be talked to.

    Raised when the binary is not found, the process dies, the stream breaks
    the framing rules, or a reply does not answer the request that was sent.
    """


class FramingError(TransportError):
    """Bytes on the stream do not follow the ``Content-Length`` framing rules."""


class RpcError(SloptopopError):
    """The server answered a request with a JSON-RPC error object."""

    code: int
    message: str
    data: JsonValue

    def __init__(self, code: int, message: str, data: JsonValue = None) -> None:
        """Store the error object's fields."""
        super().__init__(f"{message} (code {code})")
        self.code = code
        self.message = message
        self.data = data
