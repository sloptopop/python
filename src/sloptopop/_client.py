"""The client: runs ``sloptopop serve --stdio`` and talks JSON-RPC to it."""

from __future__ import annotations

import contextlib
import io
import subprocess
import threading
from dataclasses import dataclass
from typing import IO, TYPE_CHECKING, Self

from sloptopop import framing
from sloptopop._binary import find_binary
from sloptopop._errors import RpcError, SloptopopError, TransportError
from sloptopop._version import __version__

if TYPE_CHECKING:
    import os
    from pathlib import Path
    from types import TracebackType

    from sloptopop._json import JsonValue

PROTOCOL_VERSION = 1
"""Protocol version this client speaks."""

CLIENT_NAME = "sloptopop-python"
"""``clientName`` sent in ``initialize``."""

DEFAULT_EXIT_TIMEOUT = 10.0
"""Seconds the client waits for the process to exit before killing it."""


@dataclass(frozen=True, slots=True)
class ServerInfo:
    """The server's ``initialize`` result."""

    server_name: str
    server_version: str
    protocol_version: int


class Client:
    """A running ``sloptopop serve --stdio`` session.

    Creating the client starts the binary and sends ``initialize``;
    :meth:`close` (or leaving a ``with`` block) sends ``shutdown`` and
    ``exit`` and waits for the process. Any :class:`TransportError` is fatal:
    the process is killed and the client is closed. The binary's stderr is
    collected and quoted in :class:`TransportError` messages. A client is not
    safe to share between threads.
    """

    _stderr: bytes
    """Everything the binary wrote to stderr; set once the process has exited."""

    def __init__(
        self,
        binary: str | os.PathLike[str] | None = None,
        *,
        exit_timeout: float = DEFAULT_EXIT_TIMEOUT,
    ) -> None:
        """Start the binary (see :func:`find_binary`) and initialize the session.

        Raises:
            TransportError: the binary is missing, dies, or breaks the protocol.
            RpcError: the server refused ``initialize``.

        """
        self.binary: Path = find_binary(binary)
        self._exit_timeout = exit_timeout
        self._next_id = 1
        self._closed = False
        try:
            self._process = subprocess.Popen(  # noqa: S603 - the caller picks the binary
                [self.binary, "serve", "--stdio"],
                bufsize=0,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except OSError as e:
            msg = f"cannot start {self.binary}: {e}"
            raise TransportError(msg) from e
        # The three pipes exist because each was requested with PIPE; typeshed
        # can't express that, hence the per-line ignores.
        self._stdin: IO[bytes] = self._process.stdin  # type: ignore[assignment]  # PIPE above
        self._stdout = io.BufferedReader(self._process.stdout)  # type: ignore[type-var]  # PIPE above
        self._stderr_pipe: IO[bytes] = self._process.stderr  # type: ignore[assignment]  # PIPE above
        # Daemon, so a client that is never closed can't block interpreter exit.
        self._stderr_thread = threading.Thread(target=self._collect_stderr, daemon=True)
        self._stderr_thread.start()
        try:
            self.server_info: ServerInfo = self._initialize()
        except BaseException:
            self._abort()
            raise

    def __enter__(self) -> Self:
        """Return the client itself."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Close the client; if the block raised, a failing close stays quiet."""
        if exc is None:
            self.close()
            return
        with contextlib.suppress(SloptopopError):
            self.close()

    @property
    def closed(self) -> bool:
        """Whether the client is closed (explicitly or after a transport error)."""
        return self._closed

    @property
    def returncode(self) -> int | None:
        """The process's exit code, or ``None`` while it runs."""
        return self._process.poll()

    def request(self, method: str, params: JsonValue = None) -> JsonValue:
        """Send a request and return its result.

        ``params`` is left out of the message when it is ``None``.

        Raises:
            RpcError: the server answered with an error object.
            TransportError: the client is closed, or the process died or broke
                the protocol.

        """
        self._check_open()
        try:
            return self._request(method, params)
        except TransportError:
            self._abort()
            raise

    def notify(self, method: str, params: JsonValue = None) -> None:
        """Send a notification (no id, no reply).

        Raises:
            TransportError: the client is closed or the process died.

        """
        self._check_open()
        try:
            self._send(_message(method, params))
        except TransportError:
            self._abort()
            raise

    def close(self) -> None:
        """Send ``shutdown`` then ``exit`` and wait for the process; idempotent.

        The process is killed if it has not exited ``exit_timeout`` seconds
        after ``exit``. Pipes are closed whatever happens.

        Raises:
            TransportError: shutting down failed, or the process did not exit
                with code 0 in time.
            RpcError: the server refused ``shutdown``.

        """
        if self._closed:
            return
        try:
            self._request("shutdown", None)
            self._send(_message("exit", None))
        except BaseException:
            self._abort()
            raise
        self._stdin.close()
        try:
            code = self._process.wait(self._exit_timeout)
        except subprocess.TimeoutExpired:
            self._abort()
            msg = f"sloptopop did not exit within {self._exit_timeout} s of exit; killed it"
            raise TransportError(msg) from None
        self._abort()
        if code != 0:
            msg = self._with_stderr(f"sloptopop exited with code {code} after shutdown")
            raise TransportError(msg)

    def _check_open(self) -> None:
        if self._closed:
            msg = "the client is closed"
            raise TransportError(msg)

    def _initialize(self) -> ServerInfo:
        result = self._request(
            "initialize",
            {
                "clientName": CLIENT_NAME,
                "clientVersion": __version__,
                "protocolVersion": PROTOCOL_VERSION,
            },
        )
        match result:
            case {
                "serverName": str(name),
                "serverVersion": str(version),
                "protocolVersion": int(protocol),
            } if type(protocol) is int:
                pass
            case _:
                msg = f"invalid initialize result: {result!r}"
                raise TransportError(msg)
        if protocol != PROTOCOL_VERSION:
            msg = f"server speaks protocol {protocol}; this client speaks {PROTOCOL_VERSION}"
            raise TransportError(msg)
        return ServerInfo(name, version, protocol)

    def _request(self, method: str, params: JsonValue) -> JsonValue:
        request_id = self._next_id
        self._next_id += 1
        message = _message(method, params)
        message["id"] = request_id
        self._send(message)
        reply = self._receive()
        match reply:
            case {"id": int(reply_id)} if type(reply_id) is int and reply_id == request_id:
                pass
            case _:
                msg = f"expected the reply to request {request_id}, got {reply!r}"
                raise TransportError(msg)
        match reply:
            case {"error": {"code": int(code), "message": str(text), **rest}}:
                # `**rest` is typed dict[str, object]; it holds decoded JSON.
                data: JsonValue = rest.get("data")  # type: ignore[assignment]  # decoded JSON; `**rest` is typed dict[str, object]
                raise RpcError(code, text, data)
            case {"result": result}:
                return result
            case _:
                msg = f"invalid reply: {reply!r}"
                raise TransportError(msg)

    def _send(self, message: JsonValue) -> None:
        data = memoryview(framing.encode(message))
        try:
            while data:
                data = data[self._stdin.write(data) :]
        except OSError as e:
            raise TransportError(self._died(f"cannot write to sloptopop: {e}")) from e

    def _receive(self) -> JsonValue:
        body = framing.read_frame(self._stdout)
        if body is None:
            raise TransportError(self._died("sloptopop closed its stdout"))
        return framing.decode(body)

    def _died(self, what: str) -> str:
        try:
            code = self._process.wait(self._exit_timeout)
        except subprocess.TimeoutExpired:
            return f"{what} (process still running)"
        self._stderr_thread.join()
        return self._with_stderr(f"{what} (exit code {code})")

    def _with_stderr(self, what: str) -> str:
        text = self._stderr.decode(errors="replace").strip()
        return f"{what}; stderr: {text}" if text else what

    def _collect_stderr(self) -> None:
        self._stderr = self._stderr_pipe.read()

    def _abort(self) -> None:
        """Close the client: kill the process if it runs, reap it, close pipes."""
        self._closed = True
        if self._process.poll() is None:
            self._process.kill()
        self._process.wait()
        self._stderr_thread.join()
        self._stdin.close()
        self._stdout.close()
        self._stderr_pipe.close()


def _message(method: str, params: JsonValue) -> dict[str, JsonValue]:
    message: dict[str, JsonValue] = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        message["params"] = params
    return message
