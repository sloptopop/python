from __future__ import annotations

import io
import subprocess
import sysconfig
from pathlib import Path
from typing import TYPE_CHECKING, NoReturn

import pytest

from sloptopop import _cli
from sloptopop.framing import decode, encode, read_frame

if TYPE_CHECKING:
    from sloptopop import JsonValue

SCRIPT = Path(sysconfig.get_path("scripts")) / "sloptopop"


class ExecCalledError(Exception):
    """Raised by the fake ``os.execv`` so the test process survives."""

    def __init__(self, path: Path, args: list[str]) -> None:
        """Record what would have been executed."""
        super().__init__(path, args)
        self.path = path
        self.argv = args


def fake_execv(path: Path, args: list[str]) -> NoReturn:
    raise ExecCalledError(path, args)


# --- the installed console script, end to end -------------------------------


def test_script_forwards_version(server_version: str) -> None:
    done = subprocess.run([SCRIPT, "--version"], capture_output=True, text=True, check=False)
    assert (done.returncode, done.stdout, done.stderr) == (
        0,
        f"sloptopop {server_version} (protocol 1)\n",
        "",
    )


def test_script_forwards_usage_error() -> None:
    done = subprocess.run([SCRIPT, "bogus"], capture_output=True, text=True, check=False)
    assert done.returncode == 2
    assert done.stdout == ""
    assert done.stderr.startswith("error: ")


def test_script_forwards_stdin_and_stdout() -> None:
    requests: list[JsonValue] = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"clientName": "t", "clientVersion": "0", "protocolVersion": 1},
        },
        {"jsonrpc": "2.0", "id": 2, "method": "shutdown"},
        {"jsonrpc": "2.0", "method": "exit"},
    ]
    done = subprocess.run(
        [SCRIPT, "serve", "--stdio"],
        input=b"".join(encode(r) for r in requests),
        capture_output=True,
        check=False,
    )
    assert done.returncode == 0
    replies = list(_frames(done.stdout))
    assert [r["id"] for r in replies] == [1, 2]


def _frames(data: bytes) -> list[dict[str, JsonValue]]:
    stream = io.BytesIO(data)
    out = []
    while (body := read_frame(stream)) is not None:
        value = decode(body)
        assert isinstance(value, dict)
        out.append(value)
    return out


# --- main() and run() in this process ---------------------------------------


def test_main_execs_binary_with_arguments(binary: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("os.execv", fake_execv)
    with pytest.raises(ExecCalledError) as caught:
        _cli.main(["serve", "--stdio"])
    assert caught.value.path == binary
    assert caught.value.argv == [str(binary), "serve", "--stdio"]


def test_main_defaults_to_sys_argv(binary: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("os.execv", fake_execv)
    monkeypatch.setattr("sys.argv", ["sloptopop", "-V"])
    with pytest.raises(ExecCalledError) as caught:
        _cli.main()
    assert caught.value.argv == [str(binary), "-V"]


def test_main_without_binary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("SLOPTOPOP_BIN")
    monkeypatch.setattr("sloptopop._binary._BUNDLED_DIR", tmp_path)
    monkeypatch.setenv("PATH", str(tmp_path))
    assert _cli.main(["--version"]) == 127
    assert capsys.readouterr().err.startswith("error: sloptopop binary not found")


def test_run_as_child_returns_exit_code(
    binary: Path, capfd: pytest.CaptureFixture[str], server_version: str
) -> None:
    assert _cli.run(binary, ["--version"], replace_process=False) == 0
    assert capfd.readouterr().out == f"sloptopop {server_version} (protocol 1)\n"
    assert _cli.run(binary, ["bogus"], replace_process=False) == 2
    assert capfd.readouterr().err.startswith("error: ")


@pytest.mark.parametrize("replace_process", [True, False])
def test_run_reports_unrunnable_binary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], *, replace_process: bool
) -> None:
    path = tmp_path / "not-executable"
    path.write_text("")
    assert _cli.run(path, [], replace_process=replace_process) == 126
    assert capsys.readouterr().err.startswith(f"error: cannot run {path}: ")
