from __future__ import annotations

import subprocess
import sys
import threading
from typing import TYPE_CHECKING

import pytest

import sloptopop
from sloptopop import Client, FramingError, RpcError, ServerInfo, TransportError

if TYPE_CHECKING:
    from pathlib import Path

    from conftest import MakeFake

BIG = "x" * (1 << 20)  # larger than any pipe buffer, so writing it blocks


# --- against the real binary ------------------------------------------------


def test_lifecycle(binary: Path, server_version: str) -> None:
    with Client(binary) as client:
        assert client.binary == binary
        assert client.server_info == ServerInfo("sloptopop", server_version, 1)
        # Tuples, so mypy doesn't narrow the properties across the close.
        assert (client.closed, client.returncode) == (False, None)
    assert (client.closed, client.returncode) == (True, 0)


def test_binary_from_environment(binary: Path) -> None:
    with Client() as client:
        assert client.binary == binary


def test_unknown_method_is_rpc_error(binary: Path) -> None:
    with Client(binary) as client:
        with pytest.raises(RpcError) as caught:
            client.request("nope")
        assert caught.value.code == -32601
        assert caught.value.message == "method not found: nope"
        assert caught.value.data is None
        assert str(caught.value) == "method not found: nope (code -32601)"
        with pytest.raises(RpcError, match="method not found: other"):
            client.request("other", {"some": ["params"]})
        assert not client.closed


def test_notification_gets_no_reply(binary: Path) -> None:
    with Client(binary) as client:
        client.notify("$/progress", {"value": 1})
        with pytest.raises(RpcError, match="method not found"):
            client.request("nope")


def test_protocol_mismatch(binary: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sloptopop._client.PROTOCOL_VERSION", 99)
    with pytest.raises(RpcError) as caught:
        Client(binary)
    assert caught.value.code == -32001
    assert caught.value.data == {"supported": [1]}


def test_close_is_idempotent(binary: Path) -> None:
    client = Client(binary)
    client.close()
    client.close()
    assert client.returncode == 0
    with pytest.raises(TransportError, match=r"^the client is closed$"):
        client.request("nope")
    with pytest.raises(TransportError, match=r"^the client is closed$"):
        client.notify("nope")


def test_exception_in_with_block_still_closes(binary: Path) -> None:
    with pytest.raises(ValueError, match="inside"), Client(binary) as client:
        raise ValueError("inside")  # noqa: EM101 - the literal is the point of the test
    assert client.returncode == 0


# --- transport errors, provoked by fake binaries ----------------------------


def test_missing_binary(tmp_path: Path) -> None:
    with pytest.raises(TransportError, match="not found"):
        Client(tmp_path / "missing")


def test_binary_cannot_start(tmp_path: Path) -> None:
    path = tmp_path / "not-executable"
    path.write_text("")
    with pytest.raises(TransportError, match="cannot start"):
        Client(path)


def test_process_dies_with_stderr(make_fake: MakeFake) -> None:
    fake = make_fake("""
        sys.stderr.write("boom")
        sys.exit(3)
    """)
    with pytest.raises(TransportError, match=r"exit code 3\); stderr: boom$"):
        Client(fake)


def test_undecodable_stderr_is_replaced(make_fake: MakeFake) -> None:
    fake = make_fake("""
        sys.stderr.buffer.write(b"\\xffboom")
        sys.exit(3)
    """)
    with pytest.raises(TransportError, match=r"stderr: \ufffdboom$"):
        Client(fake)


def test_never_closed_client_does_not_block_exit() -> None:
    # The stderr reader is a daemon thread: without that, interpreter exit
    # would wait for it, and it for the binary, which waits for our stdin.
    done = subprocess.run(
        [sys.executable, "-c", "import sloptopop; c = sloptopop.Client(); print(c.server_info)"],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert done.returncode == 0
    assert done.stdout.startswith("ServerInfo(server_name='sloptopop'")


def test_client_threads_are_daemons(binary: Path) -> None:
    # In-process twin of the test above (mutation testing only sees this process).
    with Client(binary):
        others = [t for t in threading.enumerate() if t is not threading.main_thread()]
        assert others
        assert all(t.daemon for t in others)


def test_request_ids_count_up(make_fake: MakeFake) -> None:
    fake = make_fake("""
        initialize()
        for _ in range(2):
            request = recv()
            reply(request, result=request["id"])
        reply(recv(), result=None)
        recv()
    """)
    with Client(fake) as client:
        assert [client.request("a"), client.request("b")] == [2, 3]


def test_exit_notification_is_exact(make_fake: MakeFake) -> None:
    fake = make_fake("""
        initialize()
        reply(recv(), result=None)
        sys.exit(0 if recv() == {"jsonrpc": "2.0", "method": "exit"} else 7)
    """)
    client = Client(fake)
    client.close()
    assert client.returncode == 0


def test_process_dies_silently(make_fake: MakeFake) -> None:
    fake = make_fake("sys.exit(4)")
    with pytest.raises(TransportError, match=r"\(exit code 4\)$"):
        Client(fake)


def test_stdout_closed_but_process_running(make_fake: MakeFake) -> None:
    fake = make_fake("""
        os.close(1)
        time.sleep(60)
    """)
    with pytest.raises(TransportError, match=r"closed its stdout \(process still running\)"):
        Client(fake, exit_timeout=0.2)


def test_write_fails_after_process_exits(make_fake: MakeFake) -> None:
    fake = make_fake("initialize()")
    client = Client(fake)
    with pytest.raises(TransportError, match="cannot write to sloptopop"):
        client.request("anything", BIG)
    assert client.closed
    assert client.returncode == 0
    client.close()  # already closed by the failure: a no-op


def test_notify_fails_after_process_exits(make_fake: MakeFake) -> None:
    fake = make_fake("initialize()")
    client = Client(fake)
    with pytest.raises(TransportError, match="cannot write to sloptopop"):
        client.notify("anything", BIG)
    assert client.closed


def test_garbage_output_is_framing_error(make_fake: MakeFake) -> None:
    fake = make_fake("""
        recv()
        send_raw(b"garbage\\r\\n\\r\\n")
        time.sleep(60)
    """)
    with pytest.raises(FramingError, match="invalid header line"):
        Client(fake)


def test_invalid_json_reply(make_fake: MakeFake) -> None:
    fake = make_fake("""
        recv()
        send_raw(frame(b"{nope"))
    """)
    with pytest.raises(TransportError, match="not valid UTF-8 JSON"):
        Client(fake)


@pytest.mark.parametrize(
    "reply",
    [
        '{"jsonrpc": "2.0", "id": 99, "result": INIT}',
        '{"jsonrpc": "2.0", "id": True, "result": INIT}',
        '{"jsonrpc": "2.0", "result": INIT}',
        '[{"jsonrpc": "2.0", "id": 1, "result": INIT}]',
    ],
    ids=["other-id", "bool-id", "no-id", "not-an-object"],
)
def test_unexpected_reply_id(make_fake: MakeFake, reply: str) -> None:
    fake = make_fake(f"""
        recv()
        send({reply})
        time.sleep(60)
    """)
    with pytest.raises(TransportError, match="expected the reply to request 1"):
        Client(fake)


def test_reply_without_result_or_error(make_fake: MakeFake) -> None:
    fake = make_fake("""
        recv()
        send({"jsonrpc": "2.0", "id": 1})
    """)
    with pytest.raises(TransportError, match="invalid reply"):
        Client(fake)


@pytest.mark.parametrize(
    "result",
    [
        '"hello"',
        '{**INIT, "protocolVersion": True}',
        '{**INIT, "serverName": 5}',
    ],
    ids=["not-an-object", "bool-version", "name-not-string"],
)
def test_invalid_initialize_result(make_fake: MakeFake, result: str) -> None:
    fake = make_fake(f"reply(recv(), result={result})")
    with pytest.raises(TransportError, match="invalid initialize result"):
        Client(fake)


def test_server_speaks_other_protocol(make_fake: MakeFake) -> None:
    fake = make_fake('reply(recv(), result={**INIT, "protocolVersion": 2})')
    with pytest.raises(TransportError, match="server speaks protocol 2; this client speaks 1"):
        Client(fake)


def test_rpc_error_keeps_data(make_fake: MakeFake) -> None:
    fake = make_fake("""
        initialize()
        reply(recv(), error={"code": 7, "message": "seven", "data": [1, "a"]})
    """)
    client = Client(fake)
    with pytest.raises(RpcError) as caught:
        client.request("x")
    assert (caught.value.code, caught.value.message, caught.value.data) == (7, "seven", [1, "a"])
    assert not client.closed
    with pytest.raises(TransportError, match=r"\(exit code 0\)$"):
        client.close()  # the fake has exited: shutdown gets no reply
    assert client.closed


# --- close() failures -------------------------------------------------------


def test_close_when_shutdown_is_refused(make_fake: MakeFake) -> None:
    fake = make_fake("""
        initialize()
        reply(recv(), error={"code": -32600, "message": "no"})
        time.sleep(60)
    """)
    client = Client(fake)
    with pytest.raises(RpcError, match="no"):
        client.close()
    assert client.closed
    assert client.returncode is not None
    client.close()


def test_close_kills_process_that_ignores_exit(make_fake: MakeFake) -> None:
    fake = make_fake("""
        initialize()
        reply(recv(), result=None)
        time.sleep(60)
    """)
    client = Client(fake, exit_timeout=0.2)
    with pytest.raises(TransportError, match=r"did not exit within 0\.2 s"):
        client.close()
    assert client.closed
    assert client.returncode is not None
    assert client.returncode < 0


def test_close_reports_nonzero_exit(make_fake: MakeFake) -> None:
    fake = make_fake("""
        initialize()
        reply(recv(), result=None)
        recv()
        sys.stderr.write("bye\\n")
        sys.exit(5)
    """)
    client = Client(fake)
    with pytest.raises(TransportError, match=r"exited with code 5 after shutdown; stderr: bye$"):
        client.close()
    assert client.returncode == 5


def test_close_error_hidden_by_exception_in_with_block(make_fake: MakeFake) -> None:
    fake = make_fake("""
        initialize()
        reply(recv(), result=None)
        sys.exit(5)
    """)
    with pytest.raises(ValueError, match="inside"), Client(fake) as client:
        raise ValueError("inside")  # noqa: EM101 - the literal is the point of the test
    assert client.returncode == 5


def test_public_names() -> None:
    assert sloptopop.CLIENT_NAME == "sloptopop-python"
    assert sloptopop.PROTOCOL_VERSION == 1
    assert issubclass(FramingError, TransportError)
    assert issubclass(TransportError, sloptopop.SloptopopError)
    assert issubclass(RpcError, sloptopop.SloptopopError)
