from __future__ import annotations

import os
import sysconfig
from pathlib import Path

import pytest

from sloptopop import TransportError, find_binary


def executable(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n")
    path.chmod(0o755)
    return path


@pytest.fixture
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """No SLOPTOPOP_BIN, an empty bundled dir and only our own scripts on PATH."""
    monkeypatch.delenv("SLOPTOPOP_BIN")
    monkeypatch.setattr("sloptopop._binary._BUNDLED_DIR", tmp_path / "bundled")
    monkeypatch.setenv("PATH", sysconfig.get_path("scripts"))
    return tmp_path


def test_own_console_script_is_on_path() -> None:
    # The PATH tests below rely on it to prove it is skipped.
    assert (Path(sysconfig.get_path("scripts")) / "sloptopop").is_file()


def test_explicit_path_wins(binary: Path, tmp_path: Path) -> None:
    other = executable(tmp_path / "other")
    assert find_binary(other) == other
    assert find_binary(str(other)) == other
    assert find_binary() == binary


def test_missing_explicit_path_does_not_fall_back(tmp_path: Path) -> None:
    with pytest.raises(TransportError, match=r"not found at .*missing \(explicit path\)"):
        find_binary(tmp_path / "missing")


def test_missing_environment_path_does_not_fall_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SLOPTOPOP_BIN", str(tmp_path))
    with pytest.raises(TransportError, match=r"\(SLOPTOPOP_BIN\)"):
        find_binary()


def test_bundled_binary(isolated: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bundled = executable(isolated / "bundled" / "sloptopop")
    executable(isolated / "path" / "sloptopop")
    monkeypatch.setenv("PATH", str(isolated / "path"))
    assert find_binary() == bundled


def test_empty_environment_variable_is_ignored(
    isolated: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SLOPTOPOP_BIN", "")
    bundled = executable(isolated / "bundled" / "sloptopop")
    assert find_binary() == bundled


def test_path_skips_own_console_script(isolated: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    on_path = executable(isolated / "path" / "sloptopop")
    dirs = ["", sysconfig.get_path("scripts"), str(isolated / "empty"), str(on_path.parent)]
    monkeypatch.setenv("PATH", os.pathsep.join(dirs))
    assert find_binary() == on_path


@pytest.mark.usefixtures("isolated")
def test_nothing_found() -> None:
    with pytest.raises(TransportError, match="sloptopop binary not found: pass a path"):
        find_binary()


@pytest.mark.usefixtures("isolated")
def test_no_path_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PATH")
    with pytest.raises(TransportError, match="not found"):
        find_binary()
