from __future__ import annotations

import io
from typing import TYPE_CHECKING

import pytest

from sloptopop import FramingError, TransportError
from sloptopop.framing import (
    MAX_CONTENT_LENGTH,
    MAX_HEADER_LINE,
    decode,
    encode,
    frame,
    read_frame,
)

if TYPE_CHECKING:
    from collections.abc import Buffer

    from sloptopop import JsonValue


def read(data: bytes) -> bytes | None:
    return read_frame(io.BytesIO(data))


def test_documented_limits() -> None:
    assert MAX_CONTENT_LENGTH == 67_108_864
    assert MAX_HEADER_LINE == 1024


def test_encode_is_compact_utf8() -> None:
    assert encode({"a": [1, "é"]}) == b'Content-Length: 14\r\n\r\n{"a":[1,"\xc3\xa9"]}'


@pytest.mark.parametrize("value", [float("nan"), float("inf")], ids=["nan", "inf"])
def test_encode_rejects_non_json_numbers(value: float) -> None:
    with pytest.raises(ValueError, match="not JSON compliant"):
        encode([value])


def test_body_at_limit_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sloptopop.framing.MAX_CONTENT_LENGTH", 4)
    assert read(b"Content-Length: 4\r\n\r\nabcd") == b"abcd"
    with pytest.raises(FramingError, match=r"^Content-Length 5 exceeds the 4-byte limit$"):
        read(b"Content-Length: 5\r\n\r\nabcde")


def test_frame_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sloptopop.framing.MAX_CONTENT_LENGTH", 4)
    assert frame(b"abcd") == b"Content-Length: 4\r\n\r\nabcd"
    with pytest.raises(FramingError, match="body of 5 bytes exceeds the 4-byte limit"):
        frame(b"abcde")


def test_round_trip() -> None:
    message: JsonValue = {"jsonrpc": "2.0", "id": "x", "result": {"n": None, "f": 1.5, "b": True}}
    assert decode(read(encode(message)) or b"") == message


def test_clean_end_of_stream() -> None:
    assert read(b"") is None


def test_consecutive_frames() -> None:
    stream = io.BytesIO(b"Content-Length: 1\r\n\r\naContent-Length: 0\r\n\r\n")
    assert read_frame(stream) == b"a"
    assert read_frame(stream) == b""
    assert read_frame(stream) is None


def test_header_names_are_case_insensitive_and_others_ignored() -> None:
    assert read(b"content-LENGTH:  2 \r\nContent-Type: x\r\n\r\n{}") == b"{}"


def test_last_content_length_wins() -> None:
    assert read(b"Content-Length: 9\r\nContent-Length: 1\r\n\r\nz") == b"z"


def test_header_line_at_limit_is_accepted() -> None:
    line = b"X-Pad: " + b"p" * (MAX_HEADER_LINE - 9) + b"\r\n"
    assert len(line) == MAX_HEADER_LINE
    assert read(line + b"Content-Length: 1\r\n\r\nq") == b"q"


@pytest.mark.parametrize(
    ("data", "error"),
    [
        (b"Content-Length: 2\r\n", "^stream ended inside the headers$"),
        (b"Content-Length: 2\n\n{}", "invalid header line"),
        (b"X-Pad: " + b"p" * MAX_HEADER_LINE + b"\r\n\r\n", "invalid header line"),
        (b"nonsense\r\n\r\n", "invalid header line"),
        (b"Content-Type: x\r\n\r\n", "^missing or invalid Content-Length header$"),
        (b"Content-Length: -1\r\n\r\n", "missing or invalid Content-Length"),
        (b"Content-Length: \xd9\xa3\r\n\r\n", "missing or invalid Content-Length"),
        (
            f"Content-Length: {MAX_CONTENT_LENGTH + 1}\r\n\r\n".encode(),
            f"Content-Length {MAX_CONTENT_LENGTH + 1} exceeds",
        ),
        (b"Content-Length: 5\r\n\r\nab", "stream ended after 2 of 5 body bytes"),
        (
            b"Content-Length: 1\r\nX-Pad: " + b"p" * MAX_HEADER_LINE + b"\r\n\r\nz",
            "invalid header line",
        ),
        (b"Content-Length: 1\r\nContent-Length:: 2\r\n\r\nz", "missing or invalid"),
    ],
    ids=[
        "eof-in-headers",
        "bare-newline",
        "line-too-long",
        "no-colon",
        "no-content-length",
        "negative-length",
        "non-ascii-digits",
        "too-large",
        "truncated-body",
        "later-line-too-long",
        "later-invalid-length",
    ],
)
def test_framing_errors(data: bytes, error: str) -> None:
    with pytest.raises(FramingError, match=error):
        read(data)


class Trickle(io.RawIOBase):
    """A stream that hands out one byte per read, like a slow pipe."""

    def __init__(self, data: bytes) -> None:
        """Serve ``data``."""
        self._data = io.BytesIO(data)

    def readable(self) -> bool:
        """Report the stream as readable."""
        return True

    def readinto(self, buffer: Buffer, /) -> int:
        """Copy at most one byte into ``buffer``."""
        chunk = self._data.read(1)
        memoryview(buffer)[: len(chunk)] = chunk
        return len(chunk)


def test_body_arriving_in_pieces() -> None:
    assert read_frame(Trickle(b"Content-Length: 3\r\n\r\nabc")) == b"abc"


@pytest.mark.parametrize("body", [b"\xff", b"{nope"], ids=["not-utf8", "not-json"])
def test_decode_errors(body: bytes) -> None:
    with pytest.raises(TransportError, match="not valid UTF-8 JSON"):
        decode(body)
