"""Fixtures: the real binary (``SLOPTOPOP_BIN``) and fake binaries."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

type MakeFake = Callable[[str], Path]

# Prepended to every fake binary: a tiny server written with this package's
# own codec, so each fake only scripts how it misbehaves.
FAKE_PRELUDE = """\
import os, sys, time
from sloptopop.framing import decode, encode, frame, read_frame

INIT = {"serverName": "fake", "serverVersion": "9", "protocolVersion": 1}


def recv():
    body = read_frame(sys.stdin.buffer)
    return None if body is None else decode(body)


def send_raw(data):
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()


def send(message):
    send_raw(encode(message))


def reply(request, **fields):
    send({"jsonrpc": "2.0", "id": request["id"], **fields})


def initialize():
    reply(recv(), result=INIT)

"""


def _required_file(variable: str) -> Path:
    value = os.environ.get(variable)
    if not value or not Path(value).is_file():
        pytest.fail(f"set {variable} to the sloptopop binary (got {value!r})")
    return Path(value)


@pytest.fixture(scope="session")
def binary() -> Path:
    """The real binary, from ``SLOPTOPOP_BIN``."""
    return _required_file("SLOPTOPOP_BIN")


@pytest.fixture(scope="session")
def server_version(binary: Path) -> str:
    """The real binary's version, from ``sloptopop --version``."""
    out = subprocess.run([binary, "--version"], capture_output=True, text=True, check=True).stdout
    match = re.fullmatch(r"sloptopop (\S+) \(protocol 1\)\n", out)
    assert match is not None, out
    return match.group(1)


@pytest.fixture
def make_fake(tmp_path: Path) -> MakeFake:
    """Return a function writing an executable fake binary running ``body``."""
    counter = iter(range(1_000_000))

    def make(body: str) -> Path:
        path = tmp_path / f"fake{next(counter)}"
        source = FAKE_PRELUDE + textwrap.dedent(body)
        path.write_text(f"#!{sys.executable}\n{source}")
        path.chmod(0o755)
        return path

    return make
