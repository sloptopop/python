r"""LSP-style message framing: ``Content-Length: N\r\n\r\n`` then N bytes of JSON.

Same rules as the binary (see ``PROTOCOL.md``): header names are
case-insensitive, other headers are ignored, every header line ends with
``\r\n`` and is at most 1024 bytes, and bodies are at most 64 MiB.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Protocol

from sloptopop._errors import FramingError, TransportError

if TYPE_CHECKING:
    from sloptopop._json import JsonValue

MAX_CONTENT_LENGTH = 64 * 1024 * 1024
"""Largest body, in bytes, either side accepts."""

MAX_HEADER_LINE = 1024
r"""Longest header line, in bytes, including its ``\r\n``."""


class Reader(Protocol):
    """The part of a binary stream :func:`read_frame` needs."""

    def readline(self, size: int = -1, /) -> bytes:
        """Read up to ``size`` bytes, stopping after a newline."""
        ...

    def read(self, size: int = -1, /) -> bytes:
        """Read up to ``size`` bytes."""
        ...


def frame(body: bytes) -> bytes:
    """Return ``body`` framed with its ``Content-Length`` header.

    Raises:
        FramingError: ``body`` is larger than :data:`MAX_CONTENT_LENGTH`.

    """
    if len(body) > MAX_CONTENT_LENGTH:
        msg = f"body of {len(body)} bytes exceeds the {MAX_CONTENT_LENGTH}-byte limit"
        raise FramingError(msg)
    return b"Content-Length: %d\r\n\r\n%b" % (len(body), body)


_ENCODER = json.JSONEncoder(ensure_ascii=False, allow_nan=False, separators=(",", ":"))
r"""Compact, raw UTF-8 (no ``\u`` escapes), and NaN/Infinity rejected (not JSON)."""


def encode(message: JsonValue) -> bytes:
    """Serialise ``message`` as compact UTF-8 JSON and frame it.

    Raises:
        ValueError: ``message`` contains NaN or an infinity.

    """
    return frame(_ENCODER.encode(message).encode())


def decode(body: bytes) -> JsonValue:
    """Parse a frame body as UTF-8 JSON.

    Raises:
        TransportError: the body is not valid UTF-8 JSON.

    """
    try:
        value: JsonValue = json.loads(body.decode())
    except ValueError as e:
        msg = f"reply is not valid UTF-8 JSON: {e}"
        raise TransportError(msg) from e
    return value


def read_frame(reader: Reader) -> bytes | None:
    """Read one frame and return its body.

    Returns ``None`` on a clean end of stream (no byte of a new frame read).

    Raises:
        FramingError: the stream ends mid-frame or the headers are malformed.

    """
    first_line = reader.readline(MAX_HEADER_LINE)
    if not first_line:
        return None
    content_length = _read_headers(reader, first_line)
    if content_length is None:
        msg = "missing or invalid Content-Length header"
        raise FramingError(msg)
    if content_length > MAX_CONTENT_LENGTH:
        msg = f"Content-Length {content_length} exceeds the {MAX_CONTENT_LENGTH}-byte limit"
        raise FramingError(msg)
    body = _read_exact(reader, content_length)
    if len(body) < content_length:
        msg = f"stream ended after {len(body)} of {content_length} body bytes"
        raise FramingError(msg)
    return body


def _read_headers(reader: Reader, line: bytes) -> int | None:
    """Parse header lines from ``line`` on; return the last valid Content-Length."""
    content_length: int | None = None
    while line != b"\r\n":
        if not line:
            msg = "stream ended inside the headers"
            raise FramingError(msg)
        name, colon, value = line.partition(b":")
        if not line.endswith(b"\r\n") or not colon:
            msg = f"invalid header line: {line!r}"
            raise FramingError(msg)
        if name.strip().lower() == b"content-length":
            digits = value.strip()
            content_length = int(digits) if digits.isdigit() else None
        line = reader.readline(MAX_HEADER_LINE)
    return content_length


def _read_exact(reader: Reader, size: int) -> bytes:
    """Read ``size`` bytes, or fewer only if the stream ends."""
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = reader.read(remaining)
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)
