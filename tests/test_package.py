from __future__ import annotations

import importlib.metadata
import subprocess
import sys
import tomllib
from pathlib import Path

import sloptopop

ROOT = Path(__file__).resolve().parents[1]


def test_version_matches_pyproject() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert sloptopop.__version__ == pyproject["project"]["version"]
    assert sloptopop.__version__ == importlib.metadata.version("sloptopop")


def test_package_is_typed() -> None:
    assert (Path(sloptopop.__file__).parent / "py.typed").is_file()


def test_hello_example(server_version: str) -> None:
    done = subprocess.run(
        [sys.executable, ROOT / "examples" / "hello.py"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert (done.returncode, done.stdout, done.stderr) == (
        0,
        f"sloptopop {server_version} (protocol 1)\n",
        "",
    )
