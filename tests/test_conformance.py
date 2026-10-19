"""Runs every case in ``cli/conformance/cases`` through this package's codec.

Each case's input is framed with :func:`sloptopop.framing.encode` (or
:func:`~sloptopop.framing.frame` for ``$raw`` bodies), piped into
``sloptopop serve --stdio``, and stdout is decoded with
:func:`~sloptopop.framing.read_frame`; the matching rules are those of
``conformance/README.md``.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from sloptopop.framing import decode, encode, frame, read_frame

if TYPE_CHECKING:
    from sloptopop import JsonValue

CASES_DIR = Path(
    os.environ.get(
        "SLOPTOPOP_CONFORMANCE_DIR",
        Path(__file__).resolve().parents[2] / "cli" / "conformance" / "cases",
    )
)
CASES = sorted(CASES_DIR.glob("*.json"))


def matches(expected: JsonValue, actual: JsonValue, server_version: str) -> bool:
    """Compare JSON values with the suite's placeholders; types must agree."""
    if expected == "$SERVER_VERSION":
        return actual == server_version
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return False
        expected = dict(expected)
        if "messagePrefix" in expected:
            prefix = expected.pop("messagePrefix")
            message = actual.get("message")
            if not (
                isinstance(prefix, str) and isinstance(message, str) and message.startswith(prefix)
            ):
                return False
            actual = {k: v for k, v in actual.items() if k != "message"}
        return expected.keys() == actual.keys() and all(
            matches(value, actual[key], server_version) for key, value in expected.items()
        )
    if isinstance(expected, list):
        return (
            isinstance(actual, list)
            and len(expected) == len(actual)
            and all(matches(e, a, server_version) for e, a in zip(expected, actual, strict=True))
        )
    return type(expected) is type(actual) and expected == actual


def test_cases_exist() -> None:
    assert len(CASES) >= 14, f"no conformance cases found in {CASES_DIR}"


def test_matcher_is_strict() -> None:
    error: JsonValue = {"code": 1, "message": "parse error: x"}
    assert matches({"code": 1, "messagePrefix": "parse error: "}, error, "v")
    assert not matches({"code": 1, "messagePrefix": "other: "}, error, "v")
    assert not matches({"code": 1, "messagePrefix": "parse"}, {"code": 1}, "v")
    assert not matches({"code": 1, "message": "parse error: x"}, {"code": 1}, "v")
    assert not matches({"a": 1}, [1], "v")
    assert not matches([1], [1, 2], "v")
    assert not matches([1], {"a": 1}, "v")
    assert not matches(1, actual=True, server_version="v")
    assert not matches("$SERVER_VERSION", "w", "v")
    assert matches(["$SERVER_VERSION", None], ["v", None], "v")


@pytest.mark.parametrize("case_path", CASES, ids=[p.stem for p in CASES])
def test_case(case_path: Path, binary: Path, server_version: str) -> None:
    case = json.loads(case_path.read_text())
    stdin = b"".join(
        frame(m["$raw"].encode()) if isinstance(m, dict) and "$raw" in m else encode(m)
        for m in case["input"]
    )
    done = subprocess.run(
        [binary, "serve", "--stdio"], input=stdin, capture_output=True, check=False, timeout=30
    )
    stdout = io.BytesIO(done.stdout)
    replies: list[JsonValue] = []
    while (body := read_frame(stdout)) is not None:
        replies.append(decode(body))
    assert matches(case["output"], replies, server_version), (
        f"{case['description']}\nexpected {case['output']}\ngot      {replies}"
    )
    assert done.returncode == case["exitCode"], done.stderr
